// Carte `parental-timeline-card` : frise de la journée de chaque enfant (segments du moteur,
// trait « maintenant », exceptions ouvertes en hachuré bleu).
import {
  esc, shouldSubscribe, timelineGeometry, exceptionsForKid, exceptionSpans, dayTypeLabel, segmentClass, statusClass, nextStepLabel, simulationBadge,
  reasonText, statusEntity,
} from "./lib.js";
import { subscribeState } from "./connection.js";
import { BASE_CSS, TIMELINE_CSS, applyTheme } from "./style.js";
import { createEditor } from "./editor.js";
import { t, lang, formatTime, formatHour } from "./i18n.js";

// Légende : segments de la frise (libellés `segment.*`), puis les exceptions hachurées.
const LEGEND = ["free", "after_homework", "quota", "on_demand", "blocked"];

const CSS = `
  ${BASE_CSS}
  .head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  .kid { margin-top: 12px; }
  .kid .name { font-weight: 500; }
  .kid .status { font-size: .85rem; }
  ${TIMELINE_CSS}
  .leg { margin-top: 10px; font-size: .8rem; }
  .leg i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin: 0 4px 0 12px; vertical-align: middle; }
  .leg i:first-child { margin-left: 0; }
`;

class ParentalTimelineCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = undefined; // undefined : pas encore reçu ; null : souscription impossible
    this._unsub = null;
    this._subConn = null;
    this._failedConn = null; // connexion sur laquelle la souscription vient d'échouer
    this._tick = null;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  setConfig(config) {
    if (config?.kids !== undefined && !Array.isArray(config.kids)) {
      throw new Error(t(this._hass, "card.timeline.kids_list"));
    }
    this._config = { ...config };
    this._render();
  }

  static getConfigElement() {
    return createEditor("timeline");
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 4;
  }

  getGridOptions() {
    return { columns: 12 };
  }

  set hass(hass) {
    const relang = lang(hass) !== lang(this._hass);
    this._hass = hass;
    applyTheme(this, hass);
    if (this.isConnected) this._subscribe();
    if (relang) this._render(); // la langue de l'utilisateur a changé
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass) this._subscribe();
    // Heure et trait « maintenant » rafraîchis chaque minute.
    clearInterval(this._tick);
    this._tick = setInterval(() => {
      if (!this._unsub && !this._subConn && this.isConnected) {
        this._failedConn = null;
        this._subscribe();
      }
      this._render();
    }, 60000);
    this._render();
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    this._tick = null;
    this._unsubscribe();
  }

  _subscribe() {
    const conn = this._hass?.connection;
    if (!shouldSubscribe(conn, this._subConn, this._failedConn)) return;
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
        // Échec (ex. `not_loaded` juste après un redémarrage de HA) : le tick de 60 s réessaiera.
        this._failedConn = this._subConn;
        this._subConn = null;
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
    const hass = this._hass;
    if (this._state === undefined) return `<div class="muted">${esc(t(hass, "common.loading"))}</div>`;
    const kids = this._state?.kids ?? {};
    const ids = (this._config.kids ?? Object.keys(kids)).filter((k) => kids[k]);
    if (this._state === null || Object.keys(kids).length === 0) {
      return `<div class="muted">${esc(t(hass, "common.unavailable"))}</div>`;
    }

    if (ids.length === 0) return `<div class="muted">${esc(t(hass, "card.timeline.no_kid"))}</div>`;

    const now = new Date();
    const hh = formatTime(hass, now);
    const dayType = dayTypeLabel(kids[ids[0]]?.day_type, hass);

    const rows = ids.map((id) => this._kidRow(id, kids[id], now)).join("");
    const hours = [0, 6, 12, 18, 24].map((h) => `<span style="left:${(h / 24) * 100}%">${esc(formatHour(hass, h))}</span>`).join("");
    const legend = LEGEND.map((cls) => `<i class="${cls}"></i>${esc(t(hass, `segment.${cls}`))}`).join("")
      + `<i class="exc"></i>${esc(t(hass, "segment.exception"))}`;

    return `
      <div class="head"><div class="titlebar"><div class="title">${esc(t(hass, "card.timeline.today"))}</div>${simulationBadge(this._state, hass)}</div>
        <div class="muted">${[dayType, hh].filter(Boolean).map(esc).join(" · ")}</div></div>
      ${rows}
      <div class="hours">${hours}</div>
      <div class="leg muted">${legend}</div>`;
  }

  _kidRow(id, kid, now) {
    const { bars, nowPct } = timelineGeometry(kid.timeline, now);
    const spans = exceptionSpans(exceptionsForKid(this._state, id), now);
    const step = nextStepLabel(kid, this._hass);
    const tap = statusEntity(kid, this._hass) !== null;
    const segs = bars
      .map((b) => `<div class="${segmentClass(b.type)}" style="left:${b.left}%;width:${b.width}%"></div>`)
      .join("");
    const excs = spans.map((s) => `<div class="exc" style="left:${s.left}%;width:${s.width}%"></div>`).join("");
    const name = `${kid.emoji ? `${esc(kid.emoji)} ` : ""}${esc(kid.name || id)}`;
    return `
      <div class="kid">
        <div><span class="name">${name}</span>
          <span class="status badge ${statusClass(kid.status)}">· ${esc(reasonText(kid, this._hass))}</span>
          ${step ? `<span class="muted status">— ${esc(step)}</span>` : ""}</div>
        <div class="tl${tap ? " tap" : ""}" data-kid="${esc(id)}">${segs}${excs}<div class="now" style="left:${nowPct}%"></div></div>
      </div>`;
  }

  // Toucher la barre ouvre le détail natif de HA du statut de l'enfant, s'il existe.
  _onClick(ev) {
    const el = ev.target.closest("[data-kid]");
    if (!el) return;
    const entityId = statusEntity(this._state?.kids?.[el.dataset.kid], this._hass);
    if (!entityId) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }
}

if (!customElements.get("parental-timeline-card")) {
  customElements.define("parental-timeline-card", ParentalTimelineCard);
}
