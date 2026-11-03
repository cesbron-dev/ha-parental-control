// Panneau « Règles » (barre latérale, admins) : édite la configuration du moteur en brouillon,
// l'écrit avec `parental_control/config/set` ; le moteur valide et cite le chemin fautif.
import { esc } from "./lib.js";
import { subscribeState } from "./connection.js";
import * as L from "./panel-lib.js";
import { CSS, opt } from "./panel-style.js";
import { kidsView } from "./panel-kids.js";
import { devicesView } from "./panel-devices.js";

const CONFIRM_MS = 3000;
const TABS = [
  { id: "kids", label: "Enfants" },
  { id: "resources", label: "Appareils" },
  { id: "general", label: "Général" },
  { id: "json", label: "JSON" },
];
const COMMON_LISTS = {
  leisure: { title: "Loisirs par défaut", other: "Sur demande",
    help: "Bloqués sur les clients AdGuard en dehors des plages libres, pour tous les enfants (ajustable par enfant)." },
  on_demand: { title: "Services sur demande par défaut", other: "Loisirs",
    help: "Toujours bloqués, même quand l'appareil est ouvert : seule une autorisation explicite les ouvre (ajustable par enfant)." },
};

const clone = (v) => JSON.parse(JSON.stringify(v));
const getPath = (obj, path) => path.split(".").reduce((node, k) => node?.[k], obj);

class ParentalControlPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "kids";
    this._kid = 0;
    this._res = 0;
    this._original = null;
    this._draft = null;
    this._newIds = new Set(); // ids créés depuis le dernier enregistrement : encore modifiables
    this._devices = [];
    this._message = null; // {kind: "error" | "ok", text}
    this._saving = false;
    this._simulation = false;
    this._unsub = null;
    this._subConn = null;
    this._armed = null;
    this._armTimer = null;
    this._day = "ecole"; // journée affichée dans la carte « Journée type »
    this._adding = null; // "kid" | "res" | "dev" : petit formulaire d'ajout ouvert
    this._menu = null; // menu ⋮ ouvert ("res")
    this._edit = null; // intégration en cours d'édition ("j:k")
    this._drag = null; // poignée de frise en cours de glissement
    this._focus = null; // sélecteur du champ à refocaliser après le rendu
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
    this.shadowRoot.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && ev.target.dataset?.enter) this._act(ev.target.dataset.enter, ev.target);
      else if (ev.key === "Escape" && this._adding && ev.target.dataset?.enter) this._act("adding", ev.target);
      else if (ev.target.dataset?.handle) this._handleKey(ev);
    });
    this.shadowRoot.addEventListener("pointerdown", (ev) => this._dragStart(ev));
    this.shadowRoot.addEventListener("pointermove", (ev) => this._dragMove(ev));
    this.shadowRoot.addEventListener("pointerup", (ev) => this._dragEnd(ev));
    this.shadowRoot.addEventListener("pointercancel", (ev) => this._dragEnd(ev));
    // Capture perdue (frise redessinée, fenêtre quittée…) : le glissement s'arrête.
    this.shadowRoot.addEventListener("lostpointercapture", (ev) => this._dragEnd(ev));
    // Choix dans une liste proposée (datalist) d'une pastille « + Ajouter » : ajouté tout de suite.
    this.shadowRoot.addEventListener("input", (ev) => {
      const el = ev.target;
      if (el.classList?.contains("pill-in") && ev.inputType === "insertReplacementText") this._act(el.dataset.enter, el);
    });
    this._beforeUnload = (ev) => {
      if (this._dirty()) ev.preventDefault();
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      this._load();
    }
    this._subscribe();
  }

  connectedCallback() {
    window.addEventListener("beforeunload", this._beforeUnload);
    if (this._hass) this._subscribe();
  }

  disconnectedCallback() {
    window.removeEventListener("beforeunload", this._beforeUnload);
    clearTimeout(this._armTimer);
    this._unsubscribe();
  }

  // Suit seulement `simulation` ; le bandeau est mis à jour sur place pour ne pas effacer une saisie en cours.
  _subscribe() {
    const conn = this._hass?.connection;
    if (!this.isConnected || !conn || this._subConn === conn) return;
    this._unsubscribe();
    this._subConn = conn;
    const token = {};
    this._subToken = token;
    subscribeState(this._hass, (msg) => {
      if (this._subToken !== token) return;
      const sim = !!msg?.simulation;
      if (sim === this._simulation) return;
      this._simulation = sim;
      const el = this.shadowRoot.querySelector(".sim-slot");
      if (el) el.innerHTML = this._simBanner();
    }).then(
      (unsub) => {
        if (this._subToken !== token) unsub();
        else this._unsub = unsub;
      },
      () => {}, // état indisponible : pas de bandeau, le panneau reste utilisable
    );
  }

  _unsubscribe() {
    this._subToken = null;
    this._subConn = null;
    this._unsub?.();
    this._unsub = null;
    // Plus d'abonnement : pas de bandeau périmé.
    if (this._simulation) {
      this._simulation = false;
      const el = this.shadowRoot.querySelector(".sim-slot");
      if (el) el.innerHTML = "";
    }
  }

  _simBanner() {
    return this._simulation ? `<span class="sim">Simulation : aucun appareil n'est piloté</span>` : "";
  }

  _dirty() {
    return !!this._draft && L.isDirty(this._original, this._draft);
  }

  async _load() {
    this._message = null;
    try {
      const { config } = await this._hass.connection.sendMessagePromise({ type: "parental_control/config/get" });
      this._original = config ?? L.emptyConfig();
      this._draft = clone(this._original);
      this._newIds.clear();
    } catch (err) {
      this._message = { kind: "error", text: `Configuration illisible : ${err?.message ?? err}` };
    }
    try {
      this._devices = await this._hass.connection.sendMessagePromise({ type: "config/device_registry/list" });
    } catch {
      this._devices = [];
    }
    this._render();
  }

  async _save() {
    this._saving = true;
    this._message = null;
    this._render();
    try {
      const { config } = await this._hass.connection.sendMessagePromise({ type: "parental_control/config/set", config: this._draft });
      this._original = config;
      this._draft = clone(config);
      this._newIds.clear();
      this._message = { kind: "ok", text: "Règles enregistrées." };
    } catch (err) {
      this._message = { kind: "error", text: `Non enregistré : ${err?.message ?? err}` };
    }
    this._saving = false;
    this._render();
  }

  // Confirmation en deux appuis pour les actions destructrices.
  _confirm(key) {
    if (this._armed === key) {
      clearTimeout(this._armTimer);
      this._armed = null;
      return true;
    }
    this._armed = key;
    clearTimeout(this._armTimer);
    this._armTimer = setTimeout(() => {
      this._armed = null;
      this._render();
    }, CONFIRM_MS);
    this._render();
    return false;
  }

  _onClick(ev) {
    const el = ev.target.closest("[data-act]");
    if (!el || el.disabled) return;
    this._act(el.dataset.act, el);
  }

  _input(name) {
    const el = this.shadowRoot.querySelector(`[data-input="${name}"]`);
    const value = (el?.value ?? "").trim();
    if (el) el.value = "";
    return value;
  }

  _act(action, el) {
    const d = this._draft;
    const kid = d?.kids[this._kid];
    const res = d?.resources[this._res];
    const arg = el.dataset.arg;
    const list = el.dataset.list;
    switch (action) {
      case "tab": this._tab = arg; this._closeAll(); break;
      case "save": this._commitPending(); this._save(); return;
      case "revert": if (!this._confirm("revert")) return; this._load(); return;
      case "kid": this._kid = Number(arg); this._closeAll(); break;
      case "res": this._res = Number(arg); this._closeAll(); break;
      case "day": this._day = arg; break;
      case "adding": this._adding = arg || null; this._focus = arg ? "[autofocus]" : null; break;
      case "menu": this._menu = this._menu === arg ? null : arg; break;
      case "edit-integ": this._edit = this._edit === arg ? null : arg; break;
      case "add-kid": {
        const name = this._input("new-kid");
        if (!name) return;
        const k = L.addKid(d, name);
        this._newIds.add(`kid:${k.id}`);
        this._kid = d.kids.length - 1;
        this._adding = null;
        break;
      }
      case "del-kid": if (!this._confirm(`del-kid:${kid.id}`)) return; L.removeKid(d, this._kid); this._kid = 0; break;
      case "add-res": {
        const name = this._input("new-res");
        if (!name) return;
        const kind = this.shadowRoot.querySelector('[data-input="new-res-kind"]').value;
        const r = L.addResource(d, name);
        L.addIntegration(r.devices[0], kind);
        this._newIds.add(`res:${r.id}`);
        this._res = d.resources.length - 1;
        this._closeAll();
        this._edit = "0:0"; // intégration encore vide : ouverte pour choisir l'entité ou l'appareil
        break;
      }
      case "del-res": if (!this._confirm(`del-res:${res.id}`)) return; L.removeResource(d, this._res); this._res = 0; this._closeAll(); break;
      case "toggle-profile":
        if (kid.profiles[arg] && !this._confirm(`drop-profile:${kid.id}:${arg}`)) return;
        L.toggleProfile(kid, arg);
        break;
      case "add-seg": L.addSegment(kid.profiles[arg].segments); break;
      case "del-seg": {
        const [day, i] = arg.split(":");
        L.removeSegment(kid.profiles[day].segments, Number(i));
        break;
      }
      case "set-mode": L.setMode(kid, el.dataset.res, arg); break;
      case "kid-svc": L.toggleKidService(d, kid, list, arg); break;
      case "add-kid-svc": case "add-common": case "add-notify":
        if (!this._commitPill(el)) return;
        this._focus = `[data-input="${el.dataset.input}"]`; // pour en ajouter plusieurs d'affilée
        break;
      case "toggle-owner": L.toggleOwner(res, arg); break;
      case "add-dev": {
        const name = this._input("new-dev");
        if (!name) return;
        L.addDevice(res, name);
        this._adding = null;
        break;
      }
      case "del-dev": if (!this._confirm(`del-dev:${res.id}:${arg}`)) return; L.removeDevice(res, Number(arg)); this._edit = null; break;
      case "del-integ": {
        if (!this._confirm(`del-integ:${res.id}:${arg}`)) return;
        const [j, k] = arg.split(":").map(Number);
        L.removeIntegration(res.devices[j], k);
        this._edit = null;
        break;
      }
      case "del-common": L.removeCommonService(d, list, arg); break;
      case "move-common": L.moveCommonService(d, arg); break;
      case "add-cal": {
        const word = this._input("cal-word");
        if (word) d.calendar_map[word] = this.shadowRoot.querySelector('[data-input="cal-day"]').value;
        break;
      }
      case "del-cal": delete d.calendar_map[arg]; break;
      case "del-notify": L.toggleListValue(d.notify, arg); break;
      case "apply-json": {
        const text = this.shadowRoot.querySelector("textarea").value;
        try {
          this._draft = JSON.parse(text);
          this._message = { kind: "ok", text: "JSON appliqué au brouillon : enregistrez pour l'envoyer au moteur." };
        } catch (err) {
          this._message = { kind: "error", text: `JSON invalide : ${err.message}` };
        }
        break;
      }
      default: return;
    }
    this._render();
  }

  // Pastille « + Ajouter » : écrit la valeur saisie dans le brouillon et vide le champ ; faux si
  // rien à ajouter. Sert pour Entrée, la sortie du champ, un choix proposé et Enregistrer.
  _commitPill(el) {
    const d = this._draft;
    const value = (el.value ?? "").trim();
    if (!d || !value) return false;
    el.value = "";
    const list = el.dataset.list;
    switch (el.dataset.enter) {
      case "add-kid-svc": return !!d.kids[this._kid] && !!L.addKidService(d, d.kids[this._kid], list, value);
      case "add-common": return !!L.addCommonService(d, list, value);
      case "add-notify":
        if (!d.notify.includes(value)) d.notify.push(value);
        return true;
      default: return false;
    }
  }

  // Avant d'enregistrer : une saisie laissée dans une pastille « + Ajouter » compte.
  _commitPending() {
    for (const el of this.shadowRoot.querySelectorAll("input.pill-in")) this._commitPill(el);
  }

  // Redessine sur place les groupes de pastilles (le reste de la page, et le clic en cours, intacts).
  _refreshChips() {
    const kid = this._draft.kids[this._kid];
    for (const el of this.shadowRoot.querySelectorAll("[data-chips]")) {
      const [kind, list] = el.dataset.chips.split(":");
      if (kind === "kid" && kid) el.innerHTML = this._kidChips(kid, list);
      else if (kind === "common") el.innerHTML = this._commonChips(list);
      else if (kind === "notify") el.innerHTML = this._notifyChips();
    }
  }

  // Changement d'enfant, d'appareil ou d'onglet : formulaires, menus et éditions repliés.
  _closeAll() {
    this._adding = null;
    this._menu = null;
    this._edit = null;
  }

  _onChange(ev) {
    const el = ev.target;
    if (el.classList.contains("pill-in")) {
      // Sortie du champ sans Entrée : la valeur est ajoutée, sans tout redessiner (le clic qui a fait
      // sortir du champ doit encore arriver sur son bouton).
      if (this._commitPill(el)) {
        this._refreshChips();
        this._renderHeader();
      }
      return;
    }
    if (/^resources\.\d+\.icon$/.test(el.dataset.path ?? "")) {
      // Icône : « jeu:nom » ou vide ; sinon champ signalé, rien d'enregistré, aperçu inchangé.
      const value = el.value.trim();
      const valid = !value || L.isIconName(value);
      if (!valid) {
        el.setAttribute("aria-invalid", "true");
        el.title = "Icône attendue sous la forme mdi:nom (ex. mdi:television)";
        return;
      }
      el.removeAttribute("aria-invalid");
      el.value = value;
    }
    if (el.dataset.calday !== undefined) {
      this._draft.calendar_map[el.dataset.calday] = el.value;
    } else if (el.dataset.move) {
      if (!el.value) return;
      this._move(Number(el.dataset.move), Number(el.value));
      this._edit = null;
    } else if (el.dataset.addInteg) {
      if (!el.value) return;
      const j = Number(el.dataset.addInteg);
      const device = this._draft.resources[this._res].devices[j];
      L.addIntegration(device, el.value);
      this._edit = `${j}:${device.integrations.length - 1}`; // vide : ouverte pour la compléter
    } else if (el.dataset.rename) {
      this._rename(el.dataset.rename, el.value);
    } else if (el.dataset.path) {
      const kind = el.dataset.type;
      let value = el.value;
      if (kind === "int") value = el.value === "" ? null : Math.max(0, Math.round(Number(el.value)));
      if (kind === "bool") value = el.checked;
      L.setPath(this._draft, el.dataset.path, value);
      this._refreshAround(el.dataset.path);
    } else {
      return;
    }
    // Un champ de saisie ne redessine que l'en-tête : redessiner tout volerait le focus (heure en
    // cours de frappe) et perdrait le clic qui a provoqué la perte de focus.
    if (el.tagName === "INPUT" && !el.dataset.rename && el.type !== "checkbox") this._renderHeader();
    else this._render();
  }

  // Après une saisie : met à jour sur place ce qui la reflète (frise, entrée de la liste, icône).
  _refreshAround(path) {
    const seg = /^(kids\.\d+\.profiles\.\w+)\.segments\.\d+\.start$/.exec(path);
    if (seg) this._refreshTimeline(seg[1]);
    const item = /^(kids|resources)\.(\d+)\.(name|emoji|icon)$/.exec(path);
    if (!item) return;
    const i = Number(item[2]);
    const el = this.shadowRoot.querySelector(`[data-item="${item[1]}.${i}"]`);
    if (el) el.outerHTML = item[1] === "kids" ? this._kidItem(i) : this._resItem(i);
    if (item[1] === "resources") {
      const res = this._draft.resources[i];
      for (const icon of this.shadowRoot.querySelectorAll(`[data-icon-of="resources.${i}"]`)) {
        icon.setAttribute("icon", res.icon || this._resIcon(res));
      }
    }
  }

  // Redessine la frise `pp` (chemin du profil) sans toucher aux champs voisins.
  _refreshTimeline(pp, index = null) {
    const prof = getPath(this._draft, pp);
    const tl = this.shadowRoot.querySelector(`.tl[data-tl="${pp}"]`);
    if (!prof || !tl) return;
    tl.innerHTML = this._timeline(prof.segments, pp);
    if (index !== null) {
      const input = this.shadowRoot.querySelector(`input[data-path="${pp}.segments.${index}.start"]`);
      if (input) input.value = prof.segments[index].start;
    }
    this._renderHeader();
  }

  // Poignées de la frise : glisser (pas de 5 min, bornées par les voisines ; logique dans panel-lib).
  _dragStart(ev) {
    const h = ev.target.closest?.(".h[data-handle]");
    if (!h || h.classList.contains("fixed") || ev.button > 0) return;
    const tl = h.closest(".tl");
    ev.preventDefault();
    h.focus?.();
    this._drag = { pp: h.dataset.pp, index: Number(h.dataset.handle), tl, pointer: ev.pointerId, x: ev.clientX, moved: false };
    try {
      tl.setPointerCapture(ev.pointerId); // suit le pointeur même hors de la frise
    } catch {
      // pointeur déjà relâché : le glissement s'arrêtera au prochain pointerup
    }
    tl.classList.add("dragging");
  }

  _dragMove(ev) {
    const drag = this._drag;
    if (!drag || ev.pointerId !== drag.pointer) return;
    if (!drag.tl.isConnected) {
      this._drag = null; // frise redessinée entre-temps : glissement abandonné
      return;
    }
    // Un simple clic ne change pas l'heure : il faut avoir glissé de quelques pixels.
    if (!drag.moved && Math.abs(ev.clientX - drag.x) < 3) return;
    drag.moved = true;
    const segments = getPath(this._draft, drag.pp)?.segments;
    const rect = drag.tl.getBoundingClientRect();
    if (!segments || !rect.width) return;
    const before = segments[drag.index].start;
    L.setSegmentStart(segments, drag.index, L.fractionToMinutes((ev.clientX - rect.left) / rect.width));
    if (segments[drag.index].start !== before) this._refreshTimeline(drag.pp, drag.index);
  }

  _dragEnd(ev) {
    const drag = this._drag;
    if (!drag || ev.pointerId !== drag.pointer) return;
    this._drag = null;
    drag.tl.classList.remove("dragging");
    if (drag.moved && drag.tl.isConnected) this._render();
  }

  // Clavier sur une poignée : flèches = ±5 min, Début/Fin = bornes permises par les voisines.
  _handleKey(ev) {
    const h = ev.target;
    const pp = h.dataset.pp;
    const index = Number(h.dataset.handle);
    const segments = getPath(this._draft, pp)?.segments;
    const bounds = segments && L.segmentBounds(segments, index);
    if (!bounds) return;
    const [hh, mm] = segments[index].start.split(":").map(Number);
    const now = hh * 60 + mm;
    const target = {
      ArrowLeft: now - L.SNAP_MINUTES, ArrowDown: now - L.SNAP_MINUTES,
      ArrowRight: now + L.SNAP_MINUTES, ArrowUp: now + L.SNAP_MINUTES,
      Home: bounds.min, End: bounds.max,
    }[ev.key];
    if (target === undefined) return;
    ev.preventDefault();
    L.setSegmentStart(segments, index, target);
    this._refreshTimeline(pp, index);
    this.shadowRoot.querySelector(`.tl[data-tl="${pp}"] [data-handle="${index}"]`)?.focus();
  }

  // Si la ressource source se vide, elle disparaît : la sélection suit l'appareil vers sa cible.
  _move(deviceIndex, toIndex) {
    const d = this._draft;
    const target = d.resources[toIndex];
    const removed = L.moveDevice(d, this._res, deviceIndex, toIndex);
    if (!removed) return;
    this._newIds.delete(`res:${removed}`);
    this._res = d.resources.indexOf(target);
  }

  // Identifiant d'un élément pas encore enregistré : modifiable, mentions mises à jour.
  _rename(target, value) {
    const d = this._draft;
    const [kind, oldId] = target.split(":");
    const id = L.slugify(value);
    const taken = (kind === "kid" ? d.kids : d.resources).map((x) => x.id);
    if (!id || id === oldId || taken.includes(id)) return;
    if (kind === "kid") {
      d.kids.find((k) => k.id === oldId).id = id;
      for (const r of d.resources) r.owners = r.owners.map((o) => (o === oldId ? id : o));
    } else {
      d.resources.find((r) => r.id === oldId).id = id;
      for (const k of d.kids) {
        if (oldId in k.resource_modes) {
          k.resource_modes[id] = k.resource_modes[oldId];
          delete k.resource_modes[oldId];
        }
      }
    }
    this._newIds.delete(target);
    this._newIds.add(`${kind}:${id}`);
  }

  _btn(act, label, { arg = "", cls = "", icon = "", title = "", disabled = false, confirmKey = null } = {}) {
    const armed = confirmKey && this._armed === confirmKey;
    return `<button type="button" class="${cls} ${armed ? "armed" : ""}" data-act="${act}" data-arg="${esc(arg)}" ${title ? `title="${esc(title)}"` : ""} ${disabled ? "disabled" : ""}>
      ${icon ? `<ha-icon icon="${armed ? "mdi:check" : icon}"></ha-icon>` : ""}${armed ? "Confirmer ?" : esc(label)}</button>`;
  }

  _header() {
    const dirty = this._dirty();
    const msg = this._message;
    const tabs = this._draft
      ? `<nav class="tabs">${TABS.map((t) => `<button type="button" class="${t.id === this._tab ? "on" : ""}" data-act="tab" data-arg="${t.id}">${t.label}</button>`).join("")}</nav>`
      : "";
    return `<h1>Règles</h1><span class="sim-slot">${this._simBanner()}</span>${tabs}<span class="sp"></span>
      ${dirty ? `<span class="dirty">Modifications non enregistrées</span>` : msg?.kind === "ok" ? `<span class="ok">${esc(msg.text)}</span>` : ""}
      ${this._btn("revert", "Annuler", { cls: "btn", title: "Annuler les modifications", disabled: !dirty || this._saving, confirmKey: "revert" })}
      ${this._btn("save", this._saving ? "Enregistrement…" : "Enregistrer", { cls: "btn primary", disabled: !dirty || this._saving })}`;
  }

  _renderHeader() {
    const header = this.shadowRoot.querySelector("header");
    if (header) header.innerHTML = this._header();
  }

  _render() {
    const d = this._draft;
    const msg = this._message;
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <div class="wrap">
        <header>${this._header()}</header>
        ${this._removedNotice()}
        ${msg?.kind === "error" ? `<div class="error">${esc(msg.text)}</div>` : ""}
        ${d ? this._body() : `<div class="card mut">Chargement…</div>`}
      </div>`;
    if (this._focus) {
      this.shadowRoot.querySelector(this._focus)?.focus();
      this._focus = null;
    }
  }

  // Appareils enregistrés absents du brouillon (supprimés, ou vidés par « Déplacer vers… »).
  _removedNotice() {
    const kept = new Set((this._draft?.resources ?? []).map((r) => r.id));
    return (this._original?.resources ?? []).filter((r) => !kept.has(r.id))
      .map((r) => `<div class="notice">« ${esc(r.name)} » sera supprimé à l'enregistrement : ses autorisations en cours et son temps du jour sont perdus.</div>`)
      .join("");
  }

  _body() {
    switch (this._tab) {
      case "resources": return this._resources();
      case "general": return this._general();
      case "json": return this._json();
      default: return this._kids();
    }
  }

  _datalist(id, values) {
    return `<datalist id="${id}">${values.map((v) => `<option value="${esc(v)}"></option>`).join("")}</datalist>`;
  }

  _entities(prefix, deviceId = null) {
    const states = Object.keys(this._hass?.states ?? {});
    const byDevice = deviceId
      ? new Set(Object.values(this._hass?.entities ?? {}).filter((e) => e.device_id === deviceId).map((e) => e.entity_id))
      : null;
    return states.filter((id) => (!prefix || id.startsWith(prefix)) && (!byDevice || byDevice.has(id))).sort();
  }

  _devicesOf(domain) {
    return this._devices
      .filter((dev) => (dev.identifiers ?? []).some(([dom]) => dom === domain))
      .map((dev) => ({ id: dev.id, name: dev.name_by_user || dev.name || dev.id }));
  }

  // Liste commune (loisirs ou sur demande) : ✕ retire, ⇄ passe dans l'autre liste.
  _commonList(list) {
    const spec = COMMON_LISTS[list];
    return `<div class="card"><h2>${spec.title}</h2>
      <div class="lz" data-chips="common:${list}">${this._commonChips(list)}</div>
      <div class="mut help">${spec.help}</div></div>`;
  }

  _commonChips(list) {
    const spec = COMMON_LISTS[list];
    const chips = (this._draft[L.SERVICE_LISTS[list].common] ?? []).map((s) => `<span class="pill split">${esc(s)}
        <button type="button" data-act="move-common" data-arg="${esc(s)}" title="Passer dans « ${spec.other} »">⇄</button>
        <button type="button" data-act="del-common" data-list="${list}" data-arg="${esc(s)}" title="Retirer">✕</button></span>`).join("");
    return `${chips}<input class="pill-in" data-input="common-${list}" data-enter="add-common" data-list="${list}" placeholder="+ Ajouter" title="Service AdGuard (ex. youtube)">`;
  }

  _notifyChips() {
    const chips = (this._draft.notify ?? []).map((s) => `<button type="button" class="pill own" data-act="del-notify" data-arg="${esc(s)}" title="Retirer">${esc(s)}<span class="x">✕</span></button>`).join("");
    return `${chips}<input class="pill-in" style="width:220px" data-input="notify" data-enter="add-notify" list="notifs" placeholder="+ notify.mobile_app_…" title="Service de notification">`;
  }

  _general() {
    const d = this._draft;
    const notifyServices = Object.keys(this._hass?.services?.notify ?? {}).map((s) => `notify.${s}`);
    const cal = Object.entries(d.calendar_map ?? {});
    return `<div class="general">
      <div>${this._commonList("leisure")}<div style="height:16px"></div>${this._commonList("on_demand")}</div>
      <div>
        <div class="card"><h2>Correspondance calendrier</h2>
          <div class="mut">Un événement du calendrier dont le titre contient ce mot donne ce type de jour.</div>
          ${cal.length ? `<div class="cal">${cal.map(([word, day]) => `<span>${esc(word)}</span>
            <select data-calday="${esc(word)}">${L.DAY_TYPES.map((t) => opt(t.value, t.label, day)).join("")}</select>
            ${this._btn("del-cal", "", { arg: word, icon: "mdi:close", cls: "icon-btn", title: "Retirer" })}`).join("")}</div>` : ""}
          <div class="row" style="margin-top:10px">
            <input data-input="cal-word" data-enter="add-cal" placeholder="mot (ex. pédagogique)" style="flex:1 1 160px">
            <select data-input="cal-day">${L.DAY_TYPES.map((t) => opt(t.value, t.label, "conge_peda")).join("")}</select>
            ${this._btn("add-cal", "Ajouter", { cls: "btn" })}
          </div>
        </div>
        <div style="height:16px"></div>
        <div class="card"><h2>Notifications</h2>
          <div class="lz" data-chips="notify">${this._notifyChips()}</div>
          ${this._datalist("notifs", notifyServices)}
          <div class="mut help">Services prévenus des avertissements (fin de plage, etc.).</div>
        </div>
      </div>
    </div>`;
  }

  _json() {
    return `<div class="card"><h2>Configuration brute</h2>
      <div class="mut">Pour copier, coller ou corriger à la main. « Appliquer » met à jour le brouillon ; « Enregistrer » l'envoie au moteur, qui la valide.</div>
      <textarea spellcheck="false">${esc(JSON.stringify(this._draft, null, 2))}</textarea>
      <div class="row">${this._btn("apply-json", "Appliquer au brouillon", { cls: "btn", icon: "mdi:check" })}</div>
    </div>`;
  }
}

Object.assign(ParentalControlPanel.prototype, kidsView, devicesView);

if (!customElements.get("parental-control-panel")) {
  customElements.define("parental-control-panel", ParentalControlPanel);
}
