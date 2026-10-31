// Carte `parental-timeline-card` : frise de la journée de chaque enfant (segments du moteur,
// trait « maintenant », exceptions ouvertes en hachuré bleu).
import {
  esc, timelineGeometry, exceptionsForKid, exceptionSpans, dayTypeLabel, segmentClass, statusClass, nextStepLabel,
} from "./lib.js";
import { subscribeState } from "./connection.js";
import { BASE_CSS } from "./style.js";

const LEGEND = [
  ["libre", "libre"],
  ["apres_devoirs", "après devoirs"],
  ["quota", "quota"],
  ["sur_demande", "sur demande"],
  ["bloque", "bloqué"],
];

const CSS = `
  ${BASE_CSS}
  .head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
  .kid { margin-top: 12px; }
  .kid .name { font-weight: 500; }
  .kid .status { font-size: .85rem; }
  .tl { position: relative; height: 16px; border-radius: 8px; overflow: hidden; margin: 6px 0 2px; background: rgba(0,0,0,.35); }
  .tl.tap { cursor: pointer; }
  .tl div { position: absolute; top: 0; bottom: 0; }
  .libre { background: linear-gradient(90deg, #2fbf71, #3ddc84); }
  .apres_devoirs { background: linear-gradient(90deg, #ff9a3c, #ffb347); }
  .quota { background: linear-gradient(90deg, #2f7fe0, #5fb3ff); }
  .sur_demande { background: rgba(255,255,255,.3); }
  .bloque { background: linear-gradient(90deg, #c0392b, #ff5f6d); }
  .exc { background: repeating-linear-gradient(45deg, rgba(124,192,255,.9) 0 4px, rgba(124,192,255,.4) 4px 8px); }
  .tl .now { width: 3px; background: #fff; box-shadow: 0 0 6px #fff; }
  .hours { position: relative; height: 1em; margin-top: 10px; font-size: .7rem; color: rgba(232,237,245,.45); }
  .hours span { position: absolute; transform: translateX(-50%); }
  .hours span:first-child { transform: none; }
  .hours span:last-child { transform: translateX(-100%); }
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
    this._tick = null;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  setConfig(config) {
    if (config?.kids !== undefined && !Array.isArray(config.kids)) {
      throw new Error("« kids » doit être une liste d'identifiants d'enfants");
    }
    this._config = { ...config };
    this._render();
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
    this._hass = hass;
    if (this.isConnected) this._subscribe();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass) this._subscribe();
    // Heure et trait « maintenant » rafraîchis chaque minute.
    clearInterval(this._tick);
    this._tick = setInterval(() => this._render(), 60000);
    this._render();
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    this._tick = null;
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
    if (this._state === undefined) return '<div class="muted">Chargement…</div>';
    const kids = this._state?.kids ?? {};
    const ids = (this._config.kids ?? Object.keys(kids)).filter((k) => kids[k]);
    if (this._state === null || Object.keys(kids).length === 0) {
      return '<div class="muted">Contrôle parental indisponible</div>';
    }

    const now = new Date();
    const hh = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const dayType = dayTypeLabel(kids[ids[0]]?.day_type);

    const rows = ids.map((id) => this._kidRow(id, kids[id], now)).join("");
    const hours = [0, 6, 12, 18, 24].map((h) => `<span style="left:${(h / 24) * 100}%">${h}h</span>`).join("");
    const legend = LEGEND.map(([cls, label]) => `<i class="${cls}"></i>${label}`).join("")
      + '<i class="exc"></i>exception';

    return `
      <div class="head"><div class="title">Aujourd'hui</div>
        <div class="muted">${[dayType, hh].filter(Boolean).map(esc).join(" · ")}</div></div>
      ${rows}
      <div class="hours">${hours}</div>
      <div class="leg muted">${legend}</div>`;
  }

  _kidRow(id, kid, now) {
    const { bars, nowPct } = timelineGeometry(kid.timeline, now);
    const spans = exceptionSpans(exceptionsForKid(this._state, id), now);
    const step = nextStepLabel(kid);
    const tap = !!this._hass?.states?.[`sensor.${id}_statut`];
    const segs = bars
      .map((b) => `<div class="${segmentClass(b.type)}" style="left:${b.left}%;width:${b.width}%"></div>`)
      .join("");
    const excs = spans.map((s) => `<div class="exc" style="left:${s.left}%;width:${s.width}%"></div>`).join("");
    const name = `${kid.emoji ? `${esc(kid.emoji)} ` : ""}${esc(kid.name || id)}`;
    return `
      <div class="kid">
        <div><span class="name">${name}</span>
          <span class="status badge ${statusClass(kid.status)}">· ${esc(kid.reason)}</span>
          ${step ? `<span class="muted status">— ${esc(step)}</span>` : ""}</div>
        <div class="tl${tap ? " tap" : ""}" data-kid="${esc(id)}">${segs}${excs}<div class="now" style="left:${nowPct}%"></div></div>
      </div>`;
  }

  // Toucher la barre ouvre le détail natif de HA du statut de l'enfant, s'il existe.
  _onClick(ev) {
    const el = ev.target.closest("[data-kid]");
    if (!el) return;
    const entityId = `sensor.${el.dataset.kid}_statut`;
    if (!this._hass?.states?.[entityId]) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }
}

if (!customElements.get("parental-timeline-card")) {
  customElements.define("parental-timeline-card", ParentalTimelineCard);
}
