// Carte appareil `parental-resource-card` : état d'une ressource du moteur, autorisations en cours,
// « Autoriser… », « Arrêter » ou, pour une Switch, pilules bonus.
import {
  esc, needsCode, resourceView, exceptionsForResource, formatPill, serviceLabel,
  reasonLine, stateBadge, quotaBar, bonusMinutes,
} from "./lib.js";
import { callAction } from "./connection.js";
import { StateCard } from "./card-base.js";
import { BASE_CSS, pill, ConfirmState, ErrorNotice, bonusPills } from "./style.js";
import { openActionDialog, runBonus } from "./dialogs.js";
import { createEditor } from "./editor.js";

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

class ParentalResourceCard extends StateCard {
  constructor() {
    super();
    this._error = new ErrorNotice(() => this._render());
    this._admin = undefined;
    this._confirm = new ConfirmState(() => this._render());
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  setConfig(config) {
    if (!config?.resource) throw new Error("« resource » est obligatoire (id de la ressource du moteur)");
    this._config = { ...config };
    this._render();
  }

  static getConfigElement() {
    return createEditor("resource");
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

  _hassChanged(hass) {
    // `hass` change souvent : on ne redessine que si le droit admin (cadenas) change.
    const admin = !!hass?.user?.is_admin;
    if (admin !== this._admin) {
      this._admin = admin;
      this._render();
    }
  }

  _cleanup() {
    this._error.clear();
    this._confirm.clear();
    this.shadowRoot.querySelector("dialog.parental")?.close();
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
      pills.push(...bonusPills(this._hass, bonusMinutes(this._config), armed));
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
      ${this._error.text ? `<div class="error">${esc(this._error.text)}</div>` : ""}`;
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
      const title = this._config.name || this._view().name || resource_id;
      return runBonus(this.shadowRoot, this._hass, {
        resource_id, minutes: Number(action.slice(6)), title, call: (s, d) => this._call(s, d),
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
    this._error.set(res.ok ? "" : res.error || "Action refusée");
    this._render();
  }
}

if (!customElements.get("parental-resource-card")) {
  customElements.define("parental-resource-card", ParentalResourceCard);
}
