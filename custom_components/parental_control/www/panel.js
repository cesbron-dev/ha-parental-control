// Panneau « Règles » (barre latérale, admins) : édite la configuration du moteur en brouillon,
// l'écrit avec `parental_control/config/set` ; le moteur valide et cite le chemin fautif.
import { esc } from "./lib.js";
import { subscribeState } from "./connection.js";
import * as L from "./panel-lib.js";

const CONFIRM_MS = 3000;
const NINTENDO_DOMAIN = "nintendo_parental_controls";
const ADGUARD_DOMAIN = "adguard_clients";
const TABS = [
  { id: "kids", label: "Enfants", icon: "mdi:account-child" },
  { id: "resources", label: "Appareils", icon: "mdi:devices" },
  { id: "general", label: "Général", icon: "mdi:tune-variant" },
  { id: "json", label: "JSON", icon: "mdi:code-json" },
];
// Icône déduite comme sur la carte appareil (Nintendo, sinon lecteur, sinon AdGuard).
const KIND_ICONS = { nintendo: "mdi:nintendo-switch", media_player: "mdi:television", adguard_services: "mdi:cellphone" };
const INTEGRATION_ICONS = { media_player: "mdi:play-box-outline", adguard_services: "mdi:shield-half-full", nintendo: "mdi:nintendo-switch" };
const SEGMENT_COLORS = { bloque: "#e05561", libre: "#3ddc84", apres_devoirs: "#ffb347", quota: "#4f8dff", sur_demande: "#9aa4b2" };

const CSS = `
  :host { display: block; min-height: 100%; color: #e8edf5; font-family: var(--ha-font-family-body, Roboto, sans-serif);
    background: linear-gradient(160deg, #1a2331 0%, #2b3a4e 50%, #18202c 100%); }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
  header { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 14px; }
  header h1 { font-size: 1.3rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; margin: 0; flex: 1; }
  .sim-banner { margin-bottom: 14px; padding: 10px 14px; border-radius: 12px; font-weight: 600; color: #ffb347;
    background: rgba(255,170,60,.16); border: 1px solid rgba(255,170,60,.55); }
  .dirty { color: #ffb347; font-size: .9rem; }
  .ok { color: #3ddc84; font-size: .9rem; }
  .card { border-radius: 18px; padding: 16px 18px; margin-bottom: 14px; box-sizing: border-box;
    background: linear-gradient(135deg, rgba(255,255,255,.11), rgba(255,255,255,.03)), rgba(24,32,46,.78);
    border: 1px solid rgba(255,255,255,.18); box-shadow: 0 8px 32px rgba(0,0,0,.35); }
  h2 { font-size: 1rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; margin: 0 0 12px; }
  h3 { font-size: .85rem; letter-spacing: .06em; text-transform: uppercase; color: #5fb3ff; margin: 16px 0 8px; }
  .muted { color: rgba(232,237,245,.62); font-size: .85rem; }
  .tabs, .chips, .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .tabs { margin-bottom: 14px; }
  button { font: inherit; color: inherit; cursor: pointer; border-radius: 8px; padding: 7px 12px;
    background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.2); display: inline-flex; align-items: center; gap: 6px; }
  button:hover { background: rgba(255,255,255,.12); }
  button:disabled { opacity: .45; cursor: default; }
  button.sel, button.primary { color: #7cc0ff; background: rgba(60,140,255,.16); border-color: rgba(110,170,255,.65); }
  button.danger { color: #ff7b7b; background: rgba(230,60,60,.14); border-color: rgba(255,110,110,.55); }
  button.armed { background: rgba(255,255,255,.22); border-color: #fff; color: #fff; }
  button.chip-off { opacity: .55; text-decoration: line-through; }
  button ha-icon { --mdc-icon-size: 18px; }
  input, select, textarea { font: inherit; color: inherit; background: rgba(0,0,0,.3); border: 1px solid rgba(255,255,255,.25);
    border-radius: 8px; padding: 7px 9px; box-sizing: border-box; min-width: 0; }
  input:focus, select:focus, textarea:focus { outline: none; border-color: #7cc0ff; }
  input[readonly] { opacity: .6; }
  select option { color: #111; }
  label.f { display: flex; flex-direction: column; gap: 4px; font-size: .8rem; color: rgba(232,237,245,.75); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 10px 14px; }
  .layout { display: grid; grid-template-columns: 220px 1fr; gap: 14px; align-items: start; }
  .list { display: flex; flex-direction: column; gap: 6px; }
  .list button { justify-content: flex-start; }
  .day { border-top: 1px solid rgba(255,255,255,.12); padding-top: 10px; margin-top: 12px; }
  .day-head { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
  .day-head strong { min-width: 150px; }
  .bar { position: relative; height: 14px; border-radius: 7px; overflow: hidden; background: rgba(0,0,0,.35); margin: 8px 0; }
  .bar div { position: absolute; top: 0; bottom: 0; }
  table { border-collapse: collapse; width: 100%; }
  td { padding: 4px 6px 4px 0; vertical-align: middle; }
  td input[type=time] { width: 120px; }
  td input.num { width: 90px; }
  textarea { width: 100%; min-height: 420px; font-family: ui-monospace, Menlo, monospace; font-size: .85rem; }
  .notice { margin: 0 0 14px; padding: 10px 14px; border-radius: 10px; color: #ffb347;
    background: rgba(255,170,60,.12); border: 1px solid rgba(255,170,60,.45); }
  .tree { margin: 12px 0 0 16px; padding-left: 16px; border-left: 2px solid rgba(255,255,255,.15); }
  .node { position: relative; margin: 12px 0; }
  .node::before { content: ""; position: absolute; left: -16px; top: 18px; width: 12px; border-top: 2px solid rgba(255,255,255,.15); }
  .node-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .node-head .grow { flex: 1 1 160px; min-width: 0; }
  .node-head input.grow { font-weight: 600; }
  .ico { width: 36px; height: 36px; border-radius: 10px; flex: none; display: flex; align-items: center; justify-content: center;
    background: rgba(255,255,255,.08); }
  .ico ha-icon { --mdc-icon-size: 22px; }
  .leaf .ico { width: 28px; height: 28px; border-radius: 8px; }
  .leaf .ico ha-icon { --mdc-icon-size: 16px; }
  .leaf-body { margin: 8px 0 0 36px; }
  .name { font-weight: 600; }
  .tag { font-size: .78rem; padding: 3px 9px; border-radius: 10px; background: rgba(255,255,255,.1); white-space: nowrap; }
  .tag.found { color: #3ddc84; }
  .tag.missing { color: #ff7b7b; }
  .tree > .row input { flex: 0 1 260px; }
  button.link, select.link { color: #6fb1ff; background: none; border-color: transparent; padding: 5px 2px; }
  select.link { cursor: pointer; }
  .error { margin: 0 0 14px; padding: 10px 14px; border-radius: 10px; color: #ffb4b4; background: rgba(230,60,60,.16);
    border: 1px solid rgba(255,110,110,.5); white-space: pre-wrap; }
  @media (max-width: 760px) { .layout { grid-template-columns: 1fr; } .list { flex-direction: row; flex-wrap: wrap; } }
`;

const clone = (v) => JSON.parse(JSON.stringify(v));
const opt = (value, label, current) => `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(label)}</option>`;

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
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
    // Sélecteur d'icône de HA (s'il est chargé) : ne redessine que l'en-tête, comme une saisie.
    this.shadowRoot.addEventListener("value-changed", (ev) => {
      const path = ev.target.dataset?.icon;
      if (!path) return;
      L.setPath(this._draft, path, ev.detail?.value ?? "");
      this._renderHeader();
    });
    this.shadowRoot.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && ev.target.dataset?.enter) this._act(ev.target.dataset.enter, ev.target);
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
    return this._simulation ? `<div class="sim-banner">Simulation — aucun appareil n'est piloté</div>` : "";
  }

  _dirty() {
    return !!this._draft && L.isDirty(this._original, this._draft);
  }

  async _load() {
    this._message = null;
    try {
      const { config } = await this._hass.connection.sendMessagePromise({ type: "parental_control/config/get" });
      this._original = config ?? { version: 1, default_leisure: [], calendar_map: {}, notify: [], kids: [], resources: [] };
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
    switch (action) {
      case "tab": this._tab = arg; break;
      case "save": this._save(); return;
      case "revert": if (!this._confirm("revert")) return; this._load(); return;
      case "kid": this._kid = Number(arg); break;
      case "res": this._res = Number(arg); break;
      case "add-kid": {
        const name = this._input("new-kid");
        if (!name) return;
        const k = L.addKid(d, name);
        this._newIds.add(`kid:${k.id}`);
        this._kid = d.kids.length - 1;
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
        break;
      }
      case "del-res": if (!this._confirm(`del-res:${res.id}`)) return; L.removeResource(d, this._res); this._res = 0; break;
      case "toggle-profile": L.toggleProfile(kid, arg); break;
      case "add-seg": L.addSegment(kid.profiles[arg].segments); break;
      case "del-seg": {
        const [day, i] = arg.split(":");
        L.removeSegment(kid.profiles[day].segments, Number(i));
        break;
      }
      case "toggle-kid-leisure": L.toggleListValue(kid.leisure_remove, arg); break;
      case "del-kid-leisure": L.toggleListValue(kid.leisure_add, arg); break;
      case "add-kid-leisure": {
        const v = this._input("kid-leisure");
        if (v && !kid.leisure_add.includes(v)) kid.leisure_add.push(v);
        break;
      }
      case "toggle-owner": L.toggleOwner(res, arg); break;
      case "add-dev": {
        const name = this._input("new-dev");
        if (!name) return;
        L.addDevice(res, name);
        break;
      }
      case "del-dev": if (!this._confirm(`del-dev:${res.id}:${arg}`)) return; L.removeDevice(res, Number(arg)); break;
      case "del-integ": {
        if (!this._confirm(`del-integ:${res.id}:${arg}`)) return;
        const [j, k] = arg.split(":").map(Number);
        L.removeIntegration(res.devices[j], k);
        break;
      }
      case "del-leisure": L.toggleListValue(d.default_leisure, arg); break;
      case "add-leisure": {
        const v = this._input("leisure");
        if (v && !d.default_leisure.includes(v)) d.default_leisure.push(v);
        break;
      }
      case "add-cal": {
        const word = this._input("cal-word");
        if (word) d.calendar_map[word] = this.shadowRoot.querySelector('[data-input="cal-day"]').value;
        break;
      }
      case "del-cal": delete d.calendar_map[arg]; break;
      case "add-notify": {
        const v = this._input("notify");
        if (v && !d.notify.includes(v)) d.notify.push(v);
        break;
      }
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

  _onChange(ev) {
    const el = ev.target;
    if (el.dataset.mode) {
      L.setMode(this._draft.kids[this._kid], el.dataset.mode, el.value);
    } else if (el.dataset.calday !== undefined) {
      this._draft.calendar_map[el.dataset.calday] = el.value;
    } else if (el.dataset.move) {
      if (!el.value) return;
      this._move(Number(el.dataset.move), Number(el.value));
    } else if (el.dataset.addInteg) {
      if (!el.value) return;
      L.addIntegration(this._draft.resources[this._res].devices[Number(el.dataset.addInteg)], el.value);
    } else if (el.dataset.rename) {
      this._rename(el.dataset.rename, el.value);
    } else if (el.dataset.path) {
      const kind = el.dataset.type;
      let value = el.value;
      if (kind === "int") value = el.value === "" ? null : Math.max(0, Math.round(Number(el.value)));
      L.setPath(this._draft, el.dataset.path, value);
      this._refreshDot(el.dataset.path);
    } else {
      return;
    }
    // Un champ de saisie ne redessine que l'en-tête : redessiner tout volerait le focus (heure en
    // cours de frappe) et perdrait le clic qui a provoqué la perte de focus.
    if (el.tagName === "INPUT" && !el.dataset.rename) this._renderHeader();
    else this._render();
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

  // La pastille d'une entité saisie au clavier se met à jour sans redessiner le reste.
  _refreshDot(path) {
    const m = /^(resources\.\d+\.devices\.\d+\.integrations\.\d+)\.entity_id$/.exec(path);
    const el = m && this.shadowRoot.querySelector(`[data-dot="${m[1]}"]`);
    if (!el) return;
    const [i, j, k] = m[1].match(/\d+/g).map(Number);
    el.outerHTML = this._dot(this._draft.resources[i].devices[j].integrations[k], m[1]);
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
    return `<h1>Règles du contrôle parental</h1>
      ${dirty ? `<span class="dirty">Modifications non enregistrées</span>` : msg?.kind === "ok" ? `<span class="ok">${esc(msg.text)}</span>` : ""}
      ${this._btn("revert", "Annuler les modifications", { icon: "mdi:undo", disabled: !dirty || this._saving, confirmKey: "revert" })}
      ${this._btn("save", this._saving ? "Enregistrement…" : "Enregistrer", { cls: "primary", icon: "mdi:content-save", disabled: !dirty || this._saving })}`;
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
        <div class="sim-slot">${this._simBanner()}</div>
        <header>${this._header()}</header>
        ${this._removedNotice()}
        ${msg?.kind === "error" ? `<div class="error">${esc(msg.text)}</div>` : ""}
        ${d ? `<div class="tabs">${TABS.map((t) => this._btn("tab", t.label, { arg: t.id, icon: t.icon, cls: t.id === this._tab ? "sel" : "" })).join("")}</div>
          ${this._body()}` : `<div class="card muted">Chargement…</div>`}
      </div>`;
    const res = d?.resources[this._res];
    for (const el of this.shadowRoot.querySelectorAll("ha-icon-picker[data-icon]")) {
      el.hass = this._hass;
      el.value = res?.icon ?? "";
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

  _idField(kind, id) {
    const editable = this._newIds.has(`${kind}:${id}`);
    return `<label class="f">Identifiant${editable ? "" : " (figé)"}
      <input value="${esc(id)}" ${editable ? `data-rename="${kind}:${esc(id)}"` : "readonly"}></label>`;
  }

  _kids() {
    const d = this._draft;
    const kid = d.kids[this._kid];
    const list = `<div class="card list">
      ${d.kids.map((k, i) => this._btn("kid", `${k.emoji ? `${k.emoji} ` : ""}${k.name}`, { arg: i, cls: i === this._kid ? "sel" : "" })).join("")}
      <input data-input="new-kid" data-enter="add-kid" placeholder="Prénom">
      ${this._btn("add-kid", "Ajouter un enfant", { icon: "mdi:plus" })}
    </div>`;
    if (!kid) return `<div class="layout">${list}<div class="card muted">Aucun enfant : ajoutez-en un.</div></div>`;
    const p = `kids.${this._kid}`;
    const calendars = this._entities("calendar.");
    const identity = `<div class="grid">
        <label class="f">Prénom<input data-path="${p}.name" value="${esc(kid.name)}"></label>
        ${this._idField("kid", kid.id)}
        <label class="f">Emoji<input data-path="${p}.emoji" value="${esc(kid.emoji ?? "")}" placeholder="🎧"></label>
        <label class="f">Couleur<input data-path="${p}.color" value="${esc(kid.color ?? "")}" placeholder="#4f8dff"></label>
        <label class="f">Calendrier scolaire<input data-path="${p}.calendar" value="${esc(kid.calendar ?? "")}" list="cals" placeholder="calendar.ecole"></label>
      </div>${this._datalist("cals", calendars)}`;
    const days = L.DAY_TYPES.map((day) => this._profile(kid, p, day)).join("");
    const removed = new Set(kid.leisure_remove);
    const leisure = `<div class="chips">
        ${d.default_leisure.map((s) => this._btn("toggle-kid-leisure", s, { arg: s, cls: removed.has(s) ? "chip-off" : "" })).join("")}
        ${kid.leisure_add.map((s) => this._btn("del-kid-leisure", `${s} ✕`, { arg: s, cls: "sel" })).join("")}
        <input data-input="kid-leisure" data-enter="add-kid-leisure" placeholder="service AdGuard (ex. fortnite)">
        ${this._btn("add-kid-leisure", "Ajouter", { icon: "mdi:plus" })}
      </div>
      <div class="muted">Toucher un service commun le retire pour cet enfant (barré) ; les services ajoutés sont en bleu.</div>`;
    const owned = d.resources.filter((r) => r.owners.includes(kid.id));
    const modes = owned.length
      ? `<table>${owned.map((r) => `<tr><td>${esc(r.name)}</td><td><select data-mode="${esc(r.id)}">
          ${L.MODES.map((m) => opt(m.value, m.label, kid.resource_modes[r.id] ?? "suit_frise")).join("")}</select></td></tr>`).join("")}</table>`
      : `<div class="muted">Aucun appareil : cochez cet enfant dans l'onglet Appareils.</div>`;
    return `<div class="layout">${list}<div>
      <div class="card"><h2>${esc(kid.name)}</h2>${identity}</div>
      <div class="card"><h2>Frises</h2>${days}</div>
      <div class="card"><h2>Loisirs</h2>${leisure}</div>
      <div class="card"><h2>Mode par appareil</h2>${modes}
        <h3>Zone sensible</h3>${this._btn("del-kid", "Supprimer cet enfant", { cls: "danger", icon: "mdi:delete", confirmKey: `del-kid:${kid.id}` })}</div>
    </div></div>`;
  }

  _profile(kid, p, day) {
    const prof = kid.profiles[day.value];
    const head = `<div class="day-head"><strong>${esc(day.label)}</strong>
      ${day.required ? "" : this._btn("toggle-profile", prof ? "Retirer ce profil" : "Profil propre", { arg: day.value, icon: prof ? "mdi:close" : "mdi:plus" })}
      ${!prof ? `<span class="muted">Suit la fin de semaine.</span>` : ""}
    </div>`;
    if (!prof) return `<div class="day">${head}</div>`;
    const pp = `${p}.profiles.${day.value}`;
    const bar = L.profileGeometry(prof.segments)
      .map((g) => `<div style="left:${g.left}%;width:${g.width}%;background:${SEGMENT_COLORS[g.type] ?? "#666"}"></div>`).join("");
    const rows = prof.segments.map((s, i) => `<tr>
      <td><input type="time" step="60" data-path="${pp}.segments.${i}.start" value="${esc(s.start)}" ${i === 0 ? "readonly" : ""}></td>
      <td><select data-path="${pp}.segments.${i}.type">${L.SEGMENT_TYPES.map((t) => opt(t.value, t.label, s.type)).join("")}</select></td>
      <td><input class="num" type="number" min="0" data-type="int" data-path="${pp}.segments.${i}.warn_minutes" value="${esc(s.warn_minutes ?? "")}" placeholder="5" title="Avertissement (minutes avant la fin)"></td>
      <td>${i === 0 ? "" : this._btn("del-seg", "✕", { arg: `${day.value}:${i}` })}</td>
    </tr>`).join("");
    return `<div class="day">${head}
      <div class="bar">${bar}</div>
      <div class="row"><label class="f">Quota du jour (min)<input class="num" type="number" min="0" data-type="int" data-path="${pp}.quota_minutes" value="${esc(prof.quota_minutes ?? "")}" placeholder="aucun"></label></div>
      <table><tr class="muted"><td>Début</td><td>Type</td><td>Avertir (min)</td><td></td></tr>${rows}</table>
      ${this._btn("add-seg", "Segment", { arg: day.value, icon: "mdi:plus" })}
    </div>`;
  }

  _resources() {
    const d = this._draft;
    const res = d.resources[this._res];
    const list = `<div class="card list">
      ${d.resources.map((r, i) => this._btn("res", r.name, { arg: i, cls: i === this._res ? "sel" : "" })).join("")}
      <input data-input="new-res" data-enter="add-res" placeholder="Nom de l'appareil">
      <select data-input="new-res-kind">${L.KINDS.map((k) => opt(k.value, k.label, "adguard_services")).join("")}</select>
      ${this._btn("add-res", "Ajouter un appareil", { icon: "mdi:plus" })}
    </div>`;
    if (!res) return `<div class="layout">${list}<div class="card muted">Aucun appareil : ajoutez-en un.</div></div>`;
    const p = `resources.${this._res}`;
    const owners = `<div class="chips">${d.kids.map((k) => this._btn("toggle-owner", k.name, { arg: k.id, cls: res.owners.includes(k.id) ? "sel" : "chip-off" })).join("")}</div>`;
    const icon = customElements.get("ha-icon-picker")
      ? `<ha-icon-picker data-icon="${p}.icon"></ha-icon-picker>`
      : `<input data-path="${p}.icon" value="${esc(res.icon ?? "")}" placeholder="${esc(this._resIcon(res))}">`;
    const quotas = `<div class="grid">${L.DAY_TYPES.map((day) => `<label class="f">${esc(day.label)} (min)
      <input type="number" min="0" data-type="int" data-path="${p}.quota_minutes.${day.value}" value="${esc(res.quota_minutes?.[day.value] ?? "")}" placeholder="aucun"></label>`).join("")}</div>`;
    return `<div class="layout">${list}<div>
      ${this._tree(res, p)}
      <div class="card"><h2>Réglages</h2>
        <div class="grid">
          <label class="f">Nom<input data-path="${p}.name" value="${esc(res.name)}"></label>
          ${this._idField("res", res.id)}
          <label class="f">Icône${icon}</label>
        </div>
        <h3>Enfants concernés</h3>${owners}
      </div>
      <div class="card"><h2>Quota par type de jour</h2>${quotas}
        <div class="muted">Vide : pas de quota propre à l'appareil.</div></div>
      <div class="card"><h3>Zone sensible</h3>${this._btn("del-res", "Supprimer cet appareil", { cls: "danger", icon: "mdi:delete", confirmKey: `del-res:${res.id}` })}</div>
    </div></div>`;
  }

  _resIcon(res) {
    const kinds = res.devices.flatMap((dev) => dev.integrations.map((i) => i.kind));
    const kind = ["nintendo", "media_player", "adguard_services"].find((k) => kinds.includes(k));
    return KIND_ICONS[kind] ?? "mdi:shield-account";
  }

  // Arbre de la ressource : appareils physiques, puis leurs intégrations.
  _tree(res, p) {
    const d = this._draft;
    const count = res.devices.reduce((n, dev) => n + dev.integrations.length, 0);
    const kids = res.owners.map((id) => d.kids.find((k) => k.id === id)?.name ?? id).join(" · ");
    const allowed = L.integrationKindsAllowed(res);
    const devices = res.devices.map((dev, j) => this._physical(res, dev, j, `${p}.devices.${j}`, allowed)).join("");
    const addDevice = allowed.length ? `<div class="row">
        <input data-input="new-dev" data-enter="add-dev" placeholder="Nom de l'appareil physique">
        ${this._btn("add-dev", "Ajouter un appareil physique", { cls: "link", icon: "mdi:plus" })}
      </div>` : "";
    return `<div class="card">
      <div class="node-head">
        <div class="ico"><ha-icon icon="${esc(res.icon || this._resIcon(res))}"></ha-icon></div>
        <div class="grow"><div class="name">${esc(res.name)}</div><div class="muted">${esc(kids || "Aucun enfant")}</div></div>
        <span class="tag">${count} intégration${count > 1 ? "s" : ""}</span>
      </div>
      <div class="tree">${devices}${addDevice}</div>
      ${this._datalist("mps", this._entities("media_player."))}
    </div>`;
  }

  _physical(res, dev, j, p, allowed) {
    const targets = L.moveTargets(this._draft, this._res, j);
    const move = targets.length ? `<select data-move="${j}" title="Déplacer vers un autre appareil">
        <option value="" selected>Déplacer vers…</option>
        ${targets.map((i) => opt(String(i), this._draft.resources[i].name, null)).join("")}
      </select>` : "";
    const integrations = dev.integrations.map((integ, k) => this._integration(res, integ, j, k, `${p}.integrations.${k}`)).join("");
    const add = allowed.length ? `<select class="link" data-add-integ="${j}">
        <option value="" selected>+ Ajouter une intégration</option>
        ${allowed.map((kind) => opt(kind, L.KINDS.find((k) => k.value === kind).label, null)).join("")}
      </select>` : "";
    return `<div class="node">
      <div class="node-head">
        <div class="ico"><ha-icon icon="mdi:monitor-cellphone"></ha-icon></div>
        <input class="grow" data-path="${p}.name" value="${esc(dev.name)}" title="Nom de l'appareil physique">
        ${move}
        ${this._btn("del-dev", "", { arg: j, icon: "mdi:delete", title: "Supprimer cet appareil physique", confirmKey: `del-dev:${res.id}:${j}` })}
      </div>
      <div class="tree">
        ${integrations || `<div class="muted">Aucune intégration : cet appareil physique ne pilote rien.</div>`}
        ${add}
      </div>
    </div>`;
  }

  _integration(res, integ, j, k, p) {
    const kind = L.KINDS.find((x) => x.value === integ.kind);
    return `<div class="node leaf">
      <div class="node-head">
        <div class="ico"><ha-icon icon="${INTEGRATION_ICONS[integ.kind] ?? "mdi:puzzle"}"></ha-icon></div>
        <div class="grow">${esc(kind?.label ?? integ.kind)}</div>
        ${this._dot(integ, p)}
        ${this._btn("del-integ", "", { arg: `${j}:${k}`, icon: "mdi:close", title: "Retirer cette intégration", confirmKey: `del-integ:${res.id}:${j}:${k}` })}
      </div>
      <div class="leaf-body">${this._kindOptions(integ, p, `${j}-${k}`)}</div>
    </div>`;
  }

  // Pastille : l'entité (lecteur) ou l'appareil (AdGuard, Nintendo) existe-t-il dans HA ?
  _dot(integ, p) {
    const found = integ.kind === "media_player"
      ? !!integ.entity_id && integ.entity_id in (this._hass?.states ?? {})
      : !!integ.device_id && this._devices.some((dev) => dev.id === integ.device_id);
    return `<span class="tag ${found ? "found" : "missing"}" data-dot="${p}">● ${found ? "trouvé" : "introuvable"}</span>`;
  }

  _deviceSelect(path, domain, current) {
    const devices = this._devicesOf(domain);
    const known = devices.some((dev) => dev.id === current);
    return `<select data-path="${path}">
      <option value="" ${current ? "" : "selected"}>— choisir —</option>
      ${!known && current ? opt(current, `${current} (introuvable)`, current) : ""}
      ${devices.map((dev) => opt(dev.id, dev.name, current)).join("")}
    </select>`;
  }

  _kindOptions(integ, p, key) {
    if (integ.kind === "media_player") {
      return `<label class="f">Entité télé<input data-path="${p}.entity_id" value="${esc(integ.entity_id ?? "")}" list="mps" placeholder="media_player.tv_salon"></label>`;
    }
    if (integ.kind === "adguard_services") {
      return `<label class="f">Client AdGuard${this._deviceSelect(`${p}.device_id`, ADGUARD_DOMAIN, integ.device_id)}</label>`;
    }
    const ents = this._entities("", integ.device_id || null);
    return `<div class="grid">
      <label class="f">Console Nintendo${this._deviceSelect(`${p}.device_id`, NINTENDO_DOMAIN, integ.device_id)}</label>
      <label class="f">Limite du jour<input data-path="${p}.limit_entity" value="${esc(integ.limit_entity ?? "")}" list="nent-${key}" placeholder="number.…"></label>
      <label class="f">Temps restant<input data-path="${p}.remaining_entity" value="${esc(integ.remaining_entity ?? "")}" list="nent-${key}" placeholder="sensor.…"></label>
      <label class="f">Temps utilisé<input data-path="${p}.used_entity" value="${esc(integ.used_entity ?? "")}" list="nent-${key}" placeholder="sensor.…"></label>
    </div>${this._datalist(`nent-${key}`, ents)}`;
  }

  _general() {
    const d = this._draft;
    const notifyServices = Object.keys(this._hass?.services?.notify ?? {}).map((s) => `notify.${s}`);
    const cal = Object.entries(d.calendar_map);
    return `
      <div class="card"><h2>Loisirs par défaut</h2>
        <div class="chips">
          ${d.default_leisure.map((s) => this._btn("del-leisure", `${s} ✕`, { arg: s, cls: "sel" })).join("")}
          <input data-input="leisure" data-enter="add-leisure" placeholder="service AdGuard (ex. youtube)">
          ${this._btn("add-leisure", "Ajouter", { icon: "mdi:plus" })}
        </div>
        <div class="muted">Services bloqués sur les clients AdGuard en dehors des plages libres, pour tous les enfants (ajustable par enfant).</div>
      </div>
      <div class="card"><h2>Calendrier scolaire</h2>
        <div class="muted">Un événement du calendrier dont le titre contient ce mot donne ce type de jour.</div>
        <table>${cal.map(([word, day]) => `<tr><td>${esc(word)}</td>
          <td><select data-calday="${esc(word)}">${L.DAY_TYPES.map((t) => opt(t.value, t.label, day)).join("")}</select></td>
          <td>${this._btn("del-cal", "✕", { arg: word })}</td></tr>`).join("")}</table>
        <div class="row" style="margin-top:8px">
          <input data-input="cal-word" data-enter="add-cal" placeholder="mot (ex. pédagogique)">
          <select data-input="cal-day">${L.DAY_TYPES.map((t) => opt(t.value, t.label, "conge_peda")).join("")}</select>
          ${this._btn("add-cal", "Ajouter", { icon: "mdi:plus" })}
        </div>
      </div>
      <div class="card"><h2>Notifications</h2>
        <div class="chips">
          ${d.notify.map((s) => this._btn("del-notify", `${s} ✕`, { arg: s, cls: "sel" })).join("")}
          <input data-input="notify" data-enter="add-notify" list="notifs" placeholder="notify.mobile_app_…">
          ${this._btn("add-notify", "Ajouter", { icon: "mdi:plus" })}
        </div>${this._datalist("notifs", notifyServices)}
        <div class="muted">Services prévenus des avertissements (fin de plage, etc.).</div>
      </div>`;
  }

  _json() {
    return `<div class="card"><h2>Configuration brute</h2>
      <div class="muted">Pour copier, coller ou corriger à la main. « Appliquer » met à jour le brouillon ; « Enregistrer » l'envoie au moteur, qui la valide.</div>
      <textarea spellcheck="false">${esc(JSON.stringify(this._draft, null, 2))}</textarea>
      <div class="row" style="margin-top:8px">${this._btn("apply-json", "Appliquer au brouillon", { icon: "mdi:check" })}</div>
    </div>`;
  }
}

customElements.define("parental-control-panel", ParentalControlPanel);
