// Carte `parental-timeline-card` : frise de la journée de chaque enfant (segments du moteur,
// trait « maintenant », exceptions ouvertes en hachuré bleu). ‹ › parcourt les `days_ahead` jours
// suivants : frise prévue par le moteur (`parental_control/timeline/preview`), sans statut en direct.
import {
  esc, shouldSubscribe, timelineGeometry, exceptionsForKid, exceptionSpans, dayExceptionSpans, dayTypeLabel, segmentClass,
  statusClass, nextStepLabel, simulationBadge, reasonText, statusEntity, haToday, addDays, daysAhead,
} from "./lib.js";
import { subscribeState } from "./connection.js";
import { BASE_CSS, TIMELINE_CSS, applyTheme } from "./style.js";
import { createEditor } from "./editor.js";
import { t, lang, formatTime, formatHour, formatDay, formatDuration, errorText } from "./i18n.js";

const PREVIEW_TTL_MS = 60000; // prévision relue au plus une fois par minute (bonus, calendrier)

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
  .titlebar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .nav { display: inline-flex; align-items: center; gap: 2px; }
  .nav button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer; padding: 2px 6px;
    border-radius: 8px; line-height: 1; --mdc-icon-size: 20px; display: inline-flex; align-items: center; }
  .nav button:hover:not([disabled]) { background: var(--g-track); }
  .nav button[disabled] { opacity: .3; cursor: default; }
  .nav .today { font-size: .8rem; padding: 3px 8px; }
  .forecast { font-size: .72rem; padding: 2px 8px; border-radius: 10px; background: var(--g-track); }
  .day .title::first-letter { text-transform: uppercase; }
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
    this._offset = 0; // jours après aujourd'hui (0 : frise en direct)
    this._previews = new Map(); // jour « AAAA-MM-JJ » -> {at, data, error}
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  setConfig(config) {
    if (config?.kids !== undefined && !Array.isArray(config.kids)) {
      throw new Error(t(this._hass, "card.timeline.kids_list"));
    }
    this._config = { ...config };
    this._offset = Math.min(this._offset, daysAhead(this._config));
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
    if (this._offset > 0) return this._forecastBody(kids, ids);

    const now = new Date();
    const hh = formatTime(hass, now);
    const dayType = dayTypeLabel(kids[ids[0]]?.day_type, hass);

    const rows = ids.map((id) => this._kidRow(id, kids[id], now)).join("");

    return `
      <div class="head"><div class="titlebar">${this._nav()}<div class="title">${esc(t(hass, "card.timeline.today"))}</div>${simulationBadge(this._state, hass)}</div>
        <div class="muted">${[dayType, hh].filter(Boolean).map(esc).join(" · ")}</div></div>
      ${rows}
      ${this._footer()}`;
  }

  _footer() {
    const hass = this._hass;
    const hours = [0, 6, 12, 18, 24].map((h) => `<span style="left:${(h / 24) * 100}%">${esc(formatHour(hass, h))}</span>`).join("");
    const legend = LEGEND.map((cls) => `<i class="${cls}"></i>${esc(t(hass, `segment.${cls}`))}`).join("")
      + `<i class="exc"></i>${esc(t(hass, "segment.exception"))}`;
    return `<div class="hours">${hours}</div><div class="leg muted">${legend}</div>`;
  }

  // ‹ › (et « Aujourd'hui » hors du jour courant) ; rien si `days_ahead` vaut 0.
  _nav() {
    const max = daysAhead(this._config);
    if (!max) return "";
    const hass = this._hass;
    const btn = (act, icon, label, disabled) => `<button type="button" data-nav="${act}" title="${esc(label)}" aria-label="${esc(label)}" ${disabled ? "disabled" : ""}><ha-icon icon="${icon}"></ha-icon></button>`;
    // Flèches avant le titre : elles ne bougent pas quand la date remplace « Aujourd'hui ».
    return `<span class="nav">${btn("prev", "mdi:chevron-left", t(hass, "card.timeline.previous_day"), this._offset === 0)}${btn("next", "mdi:chevron-right", t(hass, "card.timeline.next_day"), this._offset >= max)}</span>`;
  }

  _todayButton() {
    return `<span class="nav"><button type="button" class="today" data-nav="today" title="${esc(t(this._hass, "card.timeline.back_today"))}">${esc(t(this._hass, "card.timeline.today"))}</button></span>`;
  }

  _day() {
    return addDays(haToday(this._state), this._offset);
  }

  // Prévision du jour affiché : relue si absente ou plus vieille que PREVIEW_TTL_MS.
  _loadPreview(day) {
    const cached = this._previews.get(day);
    if (cached && (cached.loading || Date.now() - cached.at < PREVIEW_TTL_MS)) return cached;
    const entry = { at: Date.now(), loading: true, data: cached?.data ?? null, error: null };
    this._previews.set(day, entry);
    this._hass.connection.sendMessagePromise({ type: "parental_control/timeline/preview", date: day }).then(
      (data) => Object.assign(entry, { data, error: null }),
      (err) => Object.assign(entry, { error: err }),
    ).finally(() => {
      entry.loading = false;
      entry.at = Date.now();
      if (this._previews.get(day) === entry && this._day() === day) this._render();
    });
    return entry;
  }

  _forecastBody(kids, ids) {
    const hass = this._hass;
    const day = this._day();
    const preview = this._loadPreview(day);
    const data = preview.data?.date === day ? preview.data : null;
    const first = data?.kids?.[ids[0]];
    const head = `
      <div class="head day"><div class="titlebar">${this._nav()}<div class="title">${esc(formatDay(hass, day))}</div>
          ${this._todayButton()}<span class="forecast">${esc(t(hass, "card.timeline.forecast"))}</span>${simulationBadge(this._state, hass)}</div>
        <div class="muted">${esc(dayTypeLabel(first?.day_type, hass))}</div></div>`;
    if (!data) {
      const msg = preview.error
        ? t(hass, "card.timeline.load_failed", { error: errorText(hass, preview.error) })
        : t(hass, "common.loading");
      return `${head}<div class="muted">${esc(msg)}</div>`;
    }
    const rows = ids.map((id) => this._forecastRow(id, kids[id], data.kids?.[id])).join("");
    return `${head}${rows}${this._footer()}`;
  }

  _forecastRow(id, kid, preview) {
    const hass = this._hass;
    const name = `${kid.emoji ? `${esc(kid.emoji)} ` : ""}${esc(kid.name || id)}`;
    if (!preview) return `<div class="kid"><div><span class="name">${name}</span></div></div>`;
    const dayStart = new Date(preview.timeline?.[0]?.start ?? Date.now());
    const { bars } = timelineGeometry(preview.timeline, dayStart);
    const spans = dayExceptionSpans(exceptionsForKid(this._state, id), dayStart);
    const segs = bars.map((b) => `<div class="${segmentClass(b.type)}" style="left:${b.left}%;width:${b.width}%"></div>`).join("");
    const excs = spans.map((s) => `<div class="exc" style="left:${s.left}%;width:${s.width}%"></div>`).join("");
    const quota = preview.quota_minutes == null
      ? t(hass, "card.timeline.no_quota")
      : preview.bonus_minutes
        ? t(hass, "card.timeline.quota_bonus", { duration: formatDuration(hass, preview.quota_minutes), bonus: formatDuration(hass, preview.bonus_minutes) })
        : t(hass, "card.timeline.quota", { duration: formatDuration(hass, preview.quota_minutes) });
    const why = preview.calendar_error
      ? t(hass, "card.timeline.calendar_error")
      : preview.day_type_event ? t(hass, "card.timeline.event", { summary: preview.day_type_event }) : "";
    const details = [dayTypeLabel(preview.day_type, hass), why, quota].filter(Boolean).join(" · ");
    return `
      <div class="kid">
        <div><span class="name">${name}</span> <span class="muted status">— ${esc(details)}</span></div>
        <div class="tl">${segs}${excs}</div>
      </div>`;
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
    const nav = ev.target.closest("[data-nav]");
    if (nav) {
      if (nav.disabled) return;
      const max = daysAhead(this._config);
      const act = nav.dataset.nav;
      this._offset = act === "today" ? 0 : Math.min(max, Math.max(0, this._offset + (act === "next" ? 1 : -1)));
      this._render();
      return;
    }
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
