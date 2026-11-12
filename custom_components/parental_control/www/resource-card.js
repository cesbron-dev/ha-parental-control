// Carte appareil `parental-resource-card` : état d'une ressource du moteur, autorisations en cours,
// « Autoriser… », « Arrêter » ou, pour une Switch, pilules bonus.
import {
  esc, needsCode, resourceView, exceptionsForResource, formatPill, allowChoices,
  reasonLine, stateBadge, quotaBar, bonusMinutes, simulationBadge, serviceToggles,
  canRequest, findRequest, ownerChoices,
} from "./lib.js";
import { callAction } from "./connection.js";
import { StateCard } from "./card-base.js";
import { BASE_CSS, pill, ConfirmState, ErrorNotice, bonusPills, requestLines } from "./style.js";
import { openActionDialog, runBonus, bonusRequest } from "./dialogs.js";
import { createEditor } from "./editor.js";

const KIND_ICONS = {
  media_player: "mdi:television",
  switch: "mdi:power-socket-eu",
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
    background: var(--g-soft); border: 1px solid var(--g-sep);
  }
  .ico ha-icon { --mdc-icon-size: 22px; }
  .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .reason { margin-top: 8px; }
  .quota { margin-top: 10px; }
  .bar { height: 8px; border-radius: 4px; overflow: hidden; background: var(--g-track); margin-bottom: 4px; }
  .bar div { height: 100%; background: linear-gradient(90deg, #2fbf71, #3ddc84); }
  .bar div.over { background: linear-gradient(90deg, #c0392b, #ff5f6d); }
  .quota .muted { font-size: .85rem; }
  .pills { margin-top: 12px; }
  .svcs { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--g-sep); }
  .svcs .label { font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 8px; }
  .svcs .pills { margin-top: 0; gap: 8px; }
  .pill.svc-off { color: var(--g-muted); }
  .pill.svc-off ha-icon:first-child { color: var(--g-bad); }
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
    const icon = this._config.icon || v.icon || KIND_ICONS[v.kind] || "mdi:shield-account";
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
      pills.push(...bonusPills(this._hass, bonusMinutes(this._config), armed, this._parent));
    } else {
      pills.push(pill({ action: "allow", icon: "mdi:plus", label: "Autoriser…", cls: "bleu", lock: needsCode(this._hass, "open", this._parent) }));
      pills.push(pill({ action: "stop", icon: "mdi:power", label: "Arrêter", cls: "rouge", confirm: true, armed: armed === "stop" }));
    }

    return `
      <div class="row">
        <div class="ico"><ha-icon icon="${esc(icon)}"></ha-icon></div>
        <div class="grow"><div class="titlebar"><div class="title">${esc(name)}</div>${simulationBadge(this._state)}</div><div class="muted">${esc(owners)}</div></div>
        <span class="badge ${badge.cls}">${badge.label}</span>
      </div>
      ${reason ? `<div class="muted reason">${esc(reason)}</div>` : ""}
      ${quota ? `<div class="quota"><div class="bar"><div class="${quota.over ? "over" : ""}" style="width:${quota.pct}%"></div></div>
        <div class="muted">Utilisé ${quota.text}</div></div>` : ""}
      <div class="pills">${pills.join("")}</div>
      ${this._servicesBlock()}
      ${requestLines(this._state, { resource_id: id })}
      ${this._error.text ? `<div class="error">${esc(this._error.text)}</div>` : ""}`;
  }

  // Services sur demande de l'appareil en pastilles à bascule : vert débloqué, gris bloqué.
  _servicesBlock() {
    if (this._config.show_services === false) return "";
    const toggles = serviceToggles(this._state, this._config.resource, this._config.services);
    if (!toggles.length) return "";
    const lock = needsCode(this._hass, "open", this._parent);
    const pills = toggles.map((t) => {
      const action = `svc:${t.service}`;
      return `<div class="pill ${t.open ? "vert" : "svc-off"}" data-action="${esc(action)}" role="switch" aria-checked="${t.open}"
        title="${esc(t.open ? `${t.label} débloqué : toucher pour bloquer` : `${t.label} bloqué : toucher pour autoriser`)}">`
        + `<ha-icon icon="${esc(t.icon ?? (t.open ? "mdi:check-circle" : "mdi:cancel"))}"></ha-icon>${esc(t.label)}`
        + `${!t.open && lock ? '<ha-icon class="lock" icon="mdi:lock"></ha-icon>' : ""}</div>`;
    });
    return `<div class="svcs"><div class="label muted">Services sur demande</div><div class="pills">${pills.join("")}</div></div>`;
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
    if (action.startsWith("svc:")) return this._toggleService(action.slice(4));
    if (action.startsWith("cancel:")) return this._call("annuler_exception", { exception_id: action.slice(7) });
    if (action.startsWith("bonus:")) {
      const title = this._config.name || this._view().name || resource_id;
      const minutes = Number(action.slice(6));
      return runBonus(this.shadowRoot, this._hass, {
        resource_id, minutes, title, call: (s, d) => this._call(s, d),
        request: bonusRequest(this._hass, this._state, this._config, resource_id, minutes, this._parent),
        parent: this._parent,
      });
    }
  }

  _openAllow() {
    const v = this._view();
    const resource_id = this._config.resource;
    const choices = allowChoices(this._state, resource_id);
    openActionDialog(this.shadowRoot, {
      title: `Autoriser · ${this._config.name || v.name || resource_id}`,
      choices,
      durations: DURATIONS,
      needCode: needsCode(this._hass, "open", this._parent),
      submitLabel: "Autoriser",
      // Choix libre : pas d'état « en attente » ; le moteur refuse un doublon et la fenêtre l'affiche.
      request: this._request(v.owners, (kid, { choice, duration }) => {
        const data = { kind: "open", kid_id: kid, resource_id, options: DURATIONS.map((d) => d.value) };
        if (choice) data.service = choice;
        if (duration) data.minutes = duration;
        return data;
      }),
      onSubmit: ({ choice, duration, code }) => {
        const data = { resource_id, open: true };
        if (choice) data.service = choice;
        if (duration) data.minutes = duration;
        return callAction(this._hass, "exception", data, code);
      },
    });
  }

  // Bascule d'un service : autoriser, dans une fenêtre qui demande la durée (ou jusqu'au prochain
  // changement de plage) et le code pour un compte non admin ; ou bloquer, sans fenêtre. Les exceptions de ce service sur l'appareil
  // sont d'abord annulées, pour ne pas s'empiler.
  async _toggleService(service) {
    const resource_id = this._config.resource;
    const t = serviceToggles(this._state, resource_id).find((x) => x.service === service);
    if (!t) return;
    const replace = async (code, open, minutes) => {
      for (const exception_id of t.exceptions) {
        const res = await callAction(this._hass, "annuler_exception", { exception_id }, code);
        if (!res.ok) return res;
      }
      if (!open && !t.openedElsewhere) return { ok: true };
      const data = { resource_id, service, open };
      if (minutes) data.minutes = minutes;
      return callAction(this._hass, "exception", data, code);
    };
    if (t.open) {
      const res = await replace(undefined, false);
      this._error.set(res.ok ? "" : res.error || "Action refusée");
      return this._render();
    }
    const owners = this._view().owners;
    openActionDialog(this.shadowRoot, {
      title: `Autoriser · ${t.label}`,
      durations: DURATIONS,
      needCode: needsCode(this._hass, "open", this._parent),
      submitLabel: "Autoriser",
      request: this._request(owners, (kid, { duration }) => {
        const data = {
          kind: "open", kid_id: kid, resource_id, service,
          options: DURATIONS.map((d) => d.value), replace: t.exceptions,
        };
        if (duration) data.minutes = duration;
        return data;
      }, owners.length === 1 && findRequest(this._state, { kind: "open", kid_id: owners[0], resource_id, service })?.status === "pending"),
      onSubmit: ({ duration, code }) => replace(code, true, duration),
    });
  }

  // Option « Demander » d'une fenêtre (compte non admin) : au nom d'un propriétaire de l'appareil.
  // `build(kid, {choice, duration})` donne les données du service `demander`.
  _request(owners, build, pending = false) {
    if (!canRequest(this._hass, this._state, this._parent)) return null;
    return {
      kids: ownerChoices(this._state, owners),
      pending,
      onRequest: (picked) => callAction(this._hass, "demander", build(picked.kid, picked)),
    };
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
