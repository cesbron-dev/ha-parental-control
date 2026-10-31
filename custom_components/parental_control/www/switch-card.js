// Carte Switch `parental-switch-card` : temps de jeu de la console Nintendo (jauge en arc), état de
// la règle du moteur et pilules bonus. Complète l'intégration Nintendo officielle.
import { esc, resourceView, reasonLine, stateBadge, fmtDuration, bonusMinutes, switchGauge } from "./lib.js";
import { callAction } from "./connection.js";
import { StateCard } from "./card-base.js";
import { BASE_CSS, ConfirmState, ErrorNotice, bonusPills } from "./style.js";
import { runBonus } from "./dialogs.js";

const CSS = `
  ${BASE_CSS}
  .logo { position: absolute; top: 14px; right: 16px; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; }
  .logo ha-icon { --mdc-icon-size: 40px; color: #e60012; }
  /* seule la ligne de titre laisse la place au logo */
  .title, .rule { padding-right: 50px; }
  .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rule { margin-bottom: 10px; font-size: .9rem; }
  .main { display: flex; flex-wrap: wrap; align-items: stretch; gap: 16px; }
  .gauge { text-align: center; flex: none; }
  .arc { position: relative; width: 140px; height: 80px; }
  .arc svg { display: block; }
  .pct { position: absolute; left: 0; right: 0; bottom: 6px; font-size: 1.6rem; font-weight: 600; }
  .sub { font-size: .85rem; }
  .play { flex: 1; min-width: 120px; align-self: center; }
  .play h4 { margin: 0 0 6px; font-size: .8rem; letter-spacing: .08em; text-transform: uppercase; color: #5fb3ff; }
  .play .big { font-size: 1.1rem; font-weight: 500; }
  /* temps utilisé et bonus sur une ligne pleine largeur, sous la jauge ; boutons côte à côte */
  .side { flex: 1 1 100%; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.15); display: flex; flex-direction: column; gap: 10px; }
  .side .pills { gap: 8px; }
  .side .pill { flex: 1 1 90px; justify-content: center; min-height: 44px; }
  .error { margin-top: 8px; }
`;

class ParentalSwitchCard extends StateCard {
  constructor() {
    super();
    this._key = "";
    this._error = new ErrorNotice(() => this._render());
    this._confirm = new ConfirmState(() => this._render());
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  setConfig(config) {
    if (!config?.resource) throw new Error("« resource » est obligatoire (id de la ressource Nintendo du moteur)");
    this._config = { ...config };
    this._key = "";
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

  _hassChanged(hass) {
    // `hass` change souvent : on ne redessine que si le temps lu ou le droit admin (cadenas) change.
    if (!this._config) return;
    const g = switchGauge(hass, this._view());
    const key = `${g.used}|${g.remaining}|${!!hass?.user?.is_admin}`;
    if (key !== this._key) {
      this._key = key;
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
    if (v.kind !== "nintendo") return `<div class="muted">Cette carte attend une ressource Nintendo : ${esc(id)}</div>`;

    const g = switchGauge(this._hass, v);
    const pct = Math.round(g.pct);
    const badge = stateBadge(v);
    const reason = reasonLine(v);
    const title = this._config.title || "Nintendo Switch";
    const play = g.granted > 0
      ? `<div class="big">${fmtDuration(g.remaining)} restants</div><div class="muted">${fmtDuration(g.granted)} accordés aujourd’hui</div>`
      : `<div class="big">Aucun temps accordé</div><div class="muted">Temps sur demande</div>`;

    return `
      <div class="logo"><ha-icon icon="mdi:nintendo-switch"></ha-icon></div>
      <div class="title">${esc(title)}</div>
      <div class="rule muted"><span class="badge ${badge.cls}">${badge.label}</span>${reason ? ` · ${esc(reason)}` : ""}</div>
      <div class="main">
        <div class="gauge">
          <div class="arc">
            <svg width="140" height="80" viewBox="-10 0 140 80" aria-hidden="true">
              <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" stop-color="#ff4d4d"/><stop offset=".35" stop-color="#ffb02e"/>
                <stop offset=".6" stop-color="#e8e337"/><stop offset="1" stop-color="#3ddc84"/>
              </linearGradient></defs>
              <path d="M12 62 A48 48 0 0 1 108 62" pathLength="100" fill="none" stroke="rgba(0,0,0,.4)" stroke-width="12" stroke-linecap="round"/>
              ${pct > 0 ? `<path d="M12 62 A48 48 0 0 1 108 62" pathLength="100" fill="none" stroke="url(#g)" stroke-width="12" stroke-linecap="round" stroke-dasharray="${pct} 100"/>` : ""}
            </svg>
            <div class="pct">${pct} %</div>
          </div>
          <div class="sub muted">${fmtDuration(g.remaining)} / ${fmtDuration(g.granted)}</div>
        </div>
        <div class="play"><h4>Temps de jeu</h4>${play}</div>
        <div class="side">
          <div class="muted">Temps utilisé : ${fmtDuration(g.used)}</div>
          <div class="pills">${bonusPills(this._hass, bonusMinutes(this._config), this._confirm.armed).join("")}</div>
        </div>
      </div>
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
    if (!action.startsWith("bonus:")) return;
    const resource_id = this._config.resource;
    runBonus(this.shadowRoot, this._hass, {
      resource_id,
      minutes: Number(action.slice(6)),
      title: this._config.title || this._view().name || resource_id,
      call: (s, d) => this._call(s, d),
    });
  }

  // Bonus d'un admin (sans fenêtre) : l'erreur s'affiche sous la carte.
  async _call(service, data) {
    const res = await callAction(this._hass, service, data);
    this._error.set(res.ok ? "" : res.error || "Action refusée");
    this._render();
  }
}

if (!customElements.get("parental-switch-card")) {
  customElements.define("parental-switch-card", ParentalSwitchCard);
}
