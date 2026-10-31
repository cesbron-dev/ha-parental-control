// Carte appareil `parental-resource-card` : état d'une ressource du moteur, autorisations en cours,
// « Autoriser… », « Arrêter » ou, pour une Switch, pilules bonus.
import {
  esc, needsCode, resourceView, exceptionsForResource, formatPill, serviceLabel,
  reasonLine, stateBadge, bonusLabel, quotaBar,
} from "./lib.js";
import { subscribeState, callAction } from "./connection.js";
import { BASE_CSS, pill, ConfirmState } from "./style.js";
import { openActionDialog } from "./dialogs.js";

const KIND_ICONS = {
  media_player: "mdi:television",
  adguard_services: "mdi:cellphone",
  nintendo: "mdi:nintendo-switch",
};

const DURATIONS = [
  { value: 15, label: "15 min" },
  { value: 30, label: "30 min" },
  { value: 60, label: "1 h" },
  { value: 120, label: "2 h" },
  { value: null, label: "Jusqu'au prochain changement" },
];

const DEFAULT_BONUS = [15, 30, 60];
const ERROR_MS = 6000;

const CSS = `
  ${BASE_CSS}
  .ico {
    width: 40px; height: 40px; flex: none; border-radius: 12px; display: flex; align-items: center; justify-content: center;
    background: rgba(255,255,255,.07); border: 1px solid rgba(255,255,255,.15);
  }
  .ico ha-icon { --mdc-icon-size: 22px; }
  .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .reason { margin-top: 8px; }
  .quota { margin-top: 10px; }
  .bar { height: 8px; border-radius: 4px; overflow: hidden; background: rgba(0,0,0,.35); margin-bottom: 4px; }
  .bar div { height: 100%; background: linear-gradient(90deg, #2fbf71, #3ddc84); }
  .bar div.over { background: linear-gradient(90deg, #c0392b, #ff5f6d); }
  .quota .muted { font-size: .85rem; }
  .pills { margin-top: 12px; }
  .error { margin-top: 8px; }
`;

class ParentalResourceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = undefined; // undefined : pas encore reçu ; null : souscription impossible
    this._unsub = null;
    this._subConn = null;
    this._tick = null;
    this._error = "";
    this._errorTimer = null;
    this._admin = undefined;
    this._confirm = new ConfirmState(() => this._render());
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  setConfig(config) {
    if (!config?.resource) throw new Error("« resource » est obligatoire (id de la ressource du moteur)");
    this._config = { ...config };
    this._render();
  }

  static getStubConfig() {
    return { resource: "" };
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  set hass(hass) {
    this._hass = hass;
    if (this.isConnected) this._subscribe();
    // `hass` change souvent : on ne redessine que si le droit admin (cadenas) change.
    const admin = !!hass?.user?.is_admin;
    if (admin !== this._admin) {
      this._admin = admin;
      this._render();
    }
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass) this._subscribe();
    // Compte à rebours des pilules rafraîchi chaque minute.
    clearInterval(this._tick);
    this._tick = setInterval(() => this._render(), 60000);
    this._render();
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    this._tick = null;
    clearTimeout(this._errorTimer);
    this._confirm.clear();
    this.shadowRoot.querySelector("dialog.parental")?.close();
    this._unsubscribe();
  }

  _subscribe() {
    const conn = this._hass?.connection;
    if (!conn || this._subConn === conn) return;
    this._unsubscribe();
    this._subConn = conn;
    const token = {};
    this._subToken = token;
    subscribeState(this._hass, (msg) => {
      if (this._subToken !== token) return;
      this._state = msg;
      this._render();
    }).then(
      (unsub) => {
        // Déconnectée entre-temps : on relâche tout de suite la souscription.
        if (this._subToken !== token) unsub();
        else this._unsub = unsub;
      },
      () => {
        if (this._subToken !== token) return;
        this._state = null;
        this._render();
      },
    );
  }

  _unsubscribe() {
    this._subToken = null;
    this._subConn = null;
    this._unsub?.();
    this._unsub = null;
  }

  _view() {
    return resourceView(this._state, this._config.resource);
  }

  _render() {
    if (!this._config) return;
    const root = this.shadowRoot;
    let card = root.querySelector("ha-card");
    if (!card) {
      root.innerHTML = `<style>${CSS}</style><ha-card></ha-card>`;
      card = root.querySelector("ha-card");
    }
    card.innerHTML = this._body();
  }

  _body() {
    const id = this._config.resource;
    if (this._state === undefined) return '<div class="muted">Chargement…</div>';
    const v = this._view();
    if (v.status === "unavailable") return '<div class="muted">Contrôle parental indisponible</div>';
    if (v.status === "unknown") return `<div class="muted">Ressource inconnue : ${esc(id)}</div>`;

    const kids = this._state.kids ?? {};
    const owners = v.owners.map((k) => kids[k]?.name ?? k).join(" · ");
    const badge = stateBadge(v);
    const icon = this._config.icon || KIND_ICONS[v.kind] || "mdi:shield-account";
    const name = this._config.name || v.name || id;
    const reason = reasonLine(v);
    const quota = quotaBar(v);
    const armed = this._confirm.armed;
    const now = new Date();

    const pills = exceptionsForResource(this._state, id).map((e) => {
      // ✕ en fin de pilule : toute la pilule annule l'exception (après confirmation).
      const action = `cancel:${e.id}`;
      return pill({ action, icon: "mdi:check", label: formatPill(e, now), cls: "vert", confirm: true, armed: armed === action, trailing: "mdi:close" });
    });

    if (v.kind === "nintendo") {
      const lock = needsCode(this._hass, "bonus");
      for (const m of this._bonusMinutes()) {
        const action = `bonus:${m}`;
        // Avec code, la fenêtre de saisie sert de confirmation ; sinon deux appuis.
        pills.push(pill({ action, icon: "mdi:plus", label: bonusLabel(m), cls: "bleu", confirm: !lock, armed: armed === action, lock }));
      }
    } else {
      pills.push(pill({ action: "allow", icon: "mdi:plus", label: "Autoriser…", cls: "bleu", lock: needsCode(this._hass, "open") }));
      pills.push(pill({ action: "stop", icon: "mdi:power", label: "Arrêter", cls: "rouge", confirm: true, armed: armed === "stop" }));
    }

    return `
      <div class="row">
        <div class="ico"><ha-icon icon="${esc(icon)}"></ha-icon></div>
        <div class="grow"><div class="title">${esc(name)}</div><div class="muted">${esc(owners)}</div></div>
        <span class="badge ${badge.cls}">${badge.label}</span>
      </div>
      ${reason ? `<div class="muted reason">${esc(reason)}</div>` : ""}
      ${quota ? `<div class="quota"><div class="bar"><div class="${quota.over ? "over" : ""}" style="width:${quota.pct}%"></div></div>
        <div class="muted">Utilisé ${quota.text}</div></div>` : ""}
      <div class="pills">${pills.join("")}</div>
      ${this._error ? `<div class="error">${esc(this._error)}</div>` : ""}`;
  }

  _bonusMinutes() {
    const list = this._config.bonus_minutes;
    if (!Array.isArray(list)) return DEFAULT_BONUS;
    const valid = list.map(Number).filter((m) => Number.isInteger(m) && m > 0);
    return valid.length ? valid : DEFAULT_BONUS;
  }

  _onClick(ev) {
    const el = ev.target.closest("[data-action]");
    if (!el || el.hasAttribute("disabled")) return;
    const action = el.dataset.action;
    if (el.hasAttribute("data-confirm")) {
      if (!this._confirm.press(action)) return;
    } else {
      this._confirm.clear();
    }
    this._run(action);
  }

  _run(action) {
    const resource_id = this._config.resource;
    if (action === "allow") return this._openAllow();
    if (action === "stop") return this._call("exception", { resource_id, open: false });
    if (action.startsWith("cancel:")) return this._call("annuler_exception", { exception_id: action.slice(7) });
    if (action.startsWith("bonus:")) {
      const minutes = Number(action.slice(6));
      const data = { resource_id, minutes };
      if (!needsCode(this._hass, "bonus")) return this._call("ajouter_bonus", data);
      openActionDialog(this.shadowRoot, {
        title: `${bonusLabel(minutes)} · ${this._config.name || this._view().name || resource_id}`,
        needCode: true,
        submitLabel: "Ajouter",
        onSubmit: ({ code }) => callAction(this._hass, "ajouter_bonus", data, code),
      });
    }
  }

  _openAllow() {
    const v = this._view();
    const resource_id = this._config.resource;
    const choices = [{ value: null, label: "Tout l'appareil" }];
    if (v.kind === "adguard_services") {
      for (const s of v.leisure) choices.push({ value: s, label: serviceLabel(s) });
    }
    openActionDialog(this.shadowRoot, {
      title: `Autoriser · ${this._config.name || v.name || resource_id}`,
      choices,
      durations: DURATIONS,
      needCode: needsCode(this._hass, "open"),
      submitLabel: "Autoriser",
      onSubmit: ({ choice, duration, code }) => {
        const data = { resource_id, open: true };
        if (choice) data.service = choice;
        if (duration) data.minutes = duration;
        return callAction(this._hass, "exception", data, code);
      },
    });
  }

  // Actions sans fenêtre (Arrêter, ✕, bonus admin) : l'erreur s'affiche sous les pilules.
  async _call(service, data) {
    const res = await callAction(this._hass, service, data);
    clearTimeout(this._errorTimer);
    this._error = res.ok ? "" : res.error || "Action refusée";
    if (this._error) {
      this._errorTimer = setTimeout(() => {
        this._error = "";
        this._render();
      }, ERROR_MS);
    }
    this._render();
  }
}

if (!customElements.get("parental-resource-card")) {
  customElements.define("parental-resource-card", ParentalResourceCard);
}
