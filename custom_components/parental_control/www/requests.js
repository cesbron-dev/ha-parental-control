// Écran « Demandes » (panneau hors barre latérale, ouvert en touchant la notification) : demandes
// de temps en attente et récentes. Les boutons ne s'affichent qu'aux parents ; le moteur revérifie.
// Tout l'écran, message et boutons de chaque demande compris, suit la langue de l'utilisateur : le
// serveur n'envoie que des champs sans langue (noms, durée proposée, choix).
import { esc, requestRemaining, requestOutcome, requestsScreen, requestMessage, choiceTitle } from "./lib.js";
import { BASE_CSS, applyTheme } from "./style.js";
import { t, lang, errorText } from "./i18n.js";

const CSS = `
  ${BASE_CSS}
  :host { min-height: 100vh; background: var(--primary-background-color); color: var(--g-text); }
  header {
    display: flex; align-items: center; gap: 4px; height: 56px; padding: 0 4px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, #fff);
    font-family: var(--ha-font-family-body, Roboto, sans-serif);
  }
  header h1 { margin: 0 0 0 12px; font-size: 1.25rem; font-weight: 400; }
  main { max-width: 640px; margin: 0 auto; padding: 16px; display: grid; gap: 14px; }
  h2 { margin: 10px 4px 0; font-size: .95rem; font-weight: 600; color: var(--g-muted); }
  .msg { font-size: 1.1rem; font-weight: 500; margin: 0 0 4px; }
  .when { font-size: .85rem; color: var(--g-muted); margin-bottom: 14px; }
  .note { font-size: .9rem; color: var(--g-muted); margin: 0 4px; }
  .empty { text-align: center; color: var(--g-muted); padding: 24px 0; }
  .recent { display: grid; gap: 10px; }
  .recent ha-card { padding: 12px 16px; }
  .recent .msg { font-size: .95rem; }
  .recent .when { margin: 0; }
`;

const REFRESH_MS = 30000; // compte à rebours de l'expiration

class ParentalControlRequests extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = undefined; // undefined : en chargement ; null : abonnement impossible
    this._busy = null; // id de la demande en cours de réponse
    this._error = null; // {id, text}
    this._unsub = null;
    this._subConn = null;
    this._timer = null;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  set hass(hass) {
    const relang = lang(hass) !== lang(this._hass);
    this._hass = hass;
    applyTheme(this, hass);
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.hass = hass;
    if (this.isConnected) {
      this._subscribe();
      // la langue de l'utilisateur a changé : titre compris, l'écran est redessiné
      if (relang && menu) {
        this.shadowRoot.querySelector("h1").textContent = t(hass, "requests.title");
        this._render();
      }
    }
  }

  set narrow(narrow) {
    this._narrow = narrow;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = narrow;
  }

  connectedCallback() {
    if (this._hass) this._subscribe();
    clearInterval(this._timer);
    this._timer = setInterval(() => {
      // Abonnement en échec (ex. `not_loaded` juste après un redémarrage) : on réessaie.
      if (!this._subConn) this._subscribe();
      this._render();
    }, REFRESH_MS);
    this._render();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
    this._unsubscribe();
  }

  _subscribe() {
    const conn = this._hass?.connection;
    if (!conn || this._subConn === conn) return;
    this._unsubscribe();
    this._subConn = conn;
    const token = {};
    this._subToken = token;
    conn.subscribeMessage(
      (msg) => {
        if (this._subToken !== token) return;
        this._data = msg;
        this._render();
      },
      { type: "parental_control/requests/subscribe" },
    ).then(
      (unsub) => {
        if (this._subToken !== token) unsub();
        else this._unsub = unsub;
      },
      () => {
        if (this._subToken !== token) return;
        this._subConn = null;
        this._data = null;
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

  async _onClick(ev) {
    const btn = ev.target.closest("[data-choice]");
    if (!btn || this._busy) return;
    const id = btn.dataset.request;
    this._busy = id;
    this._error = null;
    this._render();
    try {
      await this._hass.callWS({ type: "parental_control/requests/answer", request_id: id, choice: btn.dataset.choice });
    } catch (err) {
      this._error = { id, text: errorText(this._hass, err) };
    }
    this._busy = null;
    this._render();
  }

  _pendingCard(req, canAnswer, now) {
    const busy = this._busy === req.id;
    const buttons = canAnswer
      ? `<div class="pills">${req.choices.map((c, i) => {
        const { choice } = c;
        const title = choiceTitle(c, this._hass);
        const cls = choice === "refuse" ? "rouge" : i === 0 ? "vert" : "bleu";
        const icon = choice === "refuse" ? "mdi:close" : "mdi:check";
        return `<button class="pill ${cls}" data-request="${esc(req.id)}" data-choice="${esc(choice)}"${this._busy ? " disabled" : ""}>`
          + `<ha-icon icon="${icon}"></ha-icon>${esc(title)}</button>`;
      }).join("")}</div>`
      : "";
    const error = this._error?.id === req.id ? `<div class="error">${esc(this._error.text)}</div>` : "";
    return `<ha-card><p class="msg">${esc(requestMessage(req, this._hass))}</p>`
      + `<div class="when">${esc(busy ? t(this._hass, "requests.sending") : requestRemaining(req.expires, now, this._hass))}</div>`
      + `${buttons}${error}</ha-card>`;
  }

  _recentCard(req) {
    const cls = req.status === "accepted" ? "ok" : req.status === "refused" ? "bad" : "muted";
    return `<ha-card><p class="msg">${esc(requestMessage(req, this._hass))}</p><div class="when ${cls}">${esc(requestOutcome(req, this._hass))}</div></ha-card>`;
  }

  _body() {
    const hass = this._hass;
    if (this._data === undefined) return `<p class="empty">${esc(t(hass, "common.loading"))}</p>`;
    if (this._data === null) return `<p class="empty">${esc(t(hass, "requests.unavailable"))}</p>`;
    const { pending, recent } = requestsScreen(this._data.requests);
    const now = new Date();
    const canAnswer = !!this._data.can_answer;
    let html = pending.length
      ? pending.map((r) => this._pendingCard(r, canAnswer, now)).join("")
      : `<p class="empty">${esc(t(hass, "requests.none_pending"))}</p>`;
    if (pending.length && !canAnswer) {
      html += `<p class="note">${esc(t(hass, "requests.only_parents"))}</p>`;
    }
    if (recent.length) {
      html += `<h2>${esc(t(hass, "requests.recent"))}</h2><div class="recent">${recent.map((r) => this._recentCard(r)).join("")}</div>`;
    }
    return html;
  }

  _render() {
    // Le bouton de menu est gardé d'un rendu à l'autre (il porte hass et narrow).
    if (!this.shadowRoot.querySelector("main")) {
      this.shadowRoot.innerHTML = `<style>${CSS}</style>`
        + `<header><ha-menu-button></ha-menu-button><h1>${esc(t(this._hass, "requests.title"))}</h1></header><main></main>`;
      const menu = this.shadowRoot.querySelector("ha-menu-button");
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
    this.shadowRoot.querySelector("main").innerHTML = this._body();
  }
}

if (!customElements.get("parental-control-requests")) {
  customElements.define("parental-control-requests", ParentalControlRequests);
}
