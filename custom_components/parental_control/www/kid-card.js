// Carte enfant `parental-kid-card` : la journée d'un enfant (statut, frise), devoirs à valider,
// minuteur, temps d'écran, services sur demande en bascules, autorisations en cours et bonus.
import {
  esc, needsCode, kidView, kidServiceToggles, kidExceptions, formatPill, timelineGeometry, exceptionsForKid,
  exceptionSpans, segmentClass, statusClass, nextStepLabel, dayTypeLabel, simulationBadge, fmtDuration,
  bonusLabel, bonusMinutes, canRequest, findRequest,
} from "./lib.js";
import { callAction } from "./connection.js";
import { StateCard } from "./card-base.js";
import { BASE_CSS, TIMELINE_CSS, pill, ConfirmState, ErrorNotice, requestLines } from "./style.js";
import { openActionDialog } from "./dialogs.js";
import { createEditor } from "./editor.js";

const TIMER_MINUTES = [15, 30, 60];

const DURATIONS = [
  { value: 15, label: "15 min" },
  { value: 30, label: "30 min" },
  { value: 60, label: "1 h" },
  { value: 120, label: "2 h" },
  { value: null, label: "Jusqu'au prochain changement" },
];

const CSS = `
  ${BASE_CSS}
  ${TIMELINE_CSS}
  .avatar {
    width: 44px; height: 44px; flex: none; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem; background: var(--g-soft); border: 2px solid var(--kid-color, var(--g-sep));
  }
  .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tl { margin-top: 14px; }
  .section { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--g-sep); }
  .section .label { font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 8px; }
  .section .pills { gap: 8px; }
  .big { font-size: 1.05rem; font-weight: 500; }
  .pill.hero { flex: 1 1 100%; justify-content: center; min-height: 48px; font-size: 1rem; }
  .pill.svc-off { color: var(--g-muted); }
  .pill.svc-off ha-icon:first-child { color: var(--g-bad); }
  .line { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
  .error { margin-top: 8px; }
`;

class ParentalKidCard extends StateCard {
  constructor() {
    super();
    this._error = new ErrorNotice(() => this._render());
    this._admin = undefined;
    this._confirm = new ConfirmState(() => this._render());
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  setConfig(config) {
    if (!config?.kid) throw new Error("« kid » est obligatoire (id de l'enfant dans les règles)");
    this._config = { ...config };
    this._render();
  }

  static getConfigElement() {
    return createEditor("kid");
  }

  static getStubConfig() {
    return { kid: "" };
  }

  getCardSize() {
    return 5;
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
    const id = this._config.kid;
    if (this._state === undefined) return '<div class="muted">Chargement…</div>';
    const v = kidView(this._state, id);
    if (v.status === "unavailable") return '<div class="muted">Contrôle parental indisponible</div>';
    if (v.status === "unknown") return `<div class="muted">Enfant inconnu : ${esc(id)}</div>`;

    const kid = v.kid;
    const now = new Date();
    const step = nextStepLabel(kid);
    const sub = [dayTypeLabel(kid.day_type), step].filter(Boolean).join(" · ");
    const color = /^#[0-9a-f]{3,8}$/i.test(kid.color ?? "") ? ` style="--kid-color:${kid.color}"` : "";

    return `
      <div class="row">
        <div class="avatar"${color}>${kid.emoji ? esc(kid.emoji) : esc(v.name.charAt(0))}</div>
        <div class="grow"><div class="titlebar"><div class="title">${esc(this._config.name || v.name)}</div>${simulationBadge(this._state)}</div>
          <div class="muted">${esc(sub)}</div></div>
        <span class="badge ${statusClass(kid.status)}">${esc(kid.reason)}</span>
      </div>
      ${this._config.show_timeline === false ? "" : this._timeline(kid, now)}
      ${this._homework(v)}
      ${this._timer(v, now)}
      ${this._services()}
      ${this._exceptions(now)}
      ${this._bonus(v)}
      ${requestLines(this._state, { kid_id: id })}
      ${this._error.text ? `<div class="error">${esc(this._error.text)}</div>` : ""}`;
  }

  _timeline(kid, now) {
    const { bars, nowPct } = timelineGeometry(kid.timeline, now);
    const spans = exceptionSpans(exceptionsForKid(this._state, this._config.kid), now);
    const segs = bars.map((b) => `<div class="${segmentClass(b.type)}" style="left:${b.left}%;width:${b.width}%"></div>`).join("");
    const excs = spans.map((s) => `<div class="exc" style="left:${s.left}%;width:${s.width}%"></div>`).join("");
    const hours = [0, 6, 12, 18, 24].map((h) => `<span style="left:${(h / 24) * 100}%">${h}h</span>`).join("");
    return `<div class="tl">${segs}${excs}<div class="now" style="left:${nowPct}%"></div></div><div class="hours">${hours}</div>`;
  }

  // Devoirs : seulement pendant une plage « après devoirs ».
  _homework(v) {
    if (!v.homework) return "";
    if (v.homework === "done") {
      return `<div class="section"><div class="label muted">Devoirs</div><div class="ok big">✓ Devoirs validés</div></div>`;
    }
    const action = "homework";
    const lock = needsCode(this._hass, "homework", this._parent);
    return `<div class="section"><div class="label muted">Devoirs</div><div class="pills">
      ${pill({ action, icon: "mdi:book-check", label: "Devoirs terminés", cls: "vert hero", confirm: !lock, armed: this._confirm.armed === action, lock })}
      </div></div>`;
  }

  // Minuteur : seulement pendant une plage « quota » ; le temps restant du quota l'accompagne.
  _timer(v, now) {
    const remaining = v.remaining != null ? `<span class="muted">Temps d'écran restant : ${fmtDuration(v.remaining)}</span>` : "";
    if (!v.timer) return remaining ? `<div class="section">${remaining}</div>` : "";
    const armed = this._confirm.armed;
    let body;
    if (v.timer.running) {
      const left = Math.max(0, Math.ceil((new Date(v.timer.end) - now) / 60000));
      body = `<div class="line"><span class="big">Minuteur · ${left} min restantes</span>
        ${pill({ action: "timer-stop", icon: "mdi:stop", label: "Arrêter", cls: "rouge", confirm: true, armed: armed === "timer-stop" })}</div>`;
    } else if (v.timer.canStart) {
      const lock = needsCode(this._hass, "timer", this._parent);
      body = `<div class="pills">${TIMER_MINUTES.map((m) => {
        const action = `timer:${m}`;
        return pill({ action, icon: "mdi:timer-play", label: `${m} min`, cls: "bleu", confirm: !lock, armed: armed === action, lock });
      }).join("")}</div>`;
    } else {
      body = '<div class="muted">Plus de temps d\'écran aujourd\'hui</div>';
    }
    return `<div class="section"><div class="label muted">Minuteur</div>${body}${remaining ? `<div style="margin-top:8px">${remaining}</div>` : ""}</div>`;
  }

  // Services sur demande de l'enfant, sur tous ses appareils AdGuard : vert débloqué, gris bloqué.
  _services() {
    if (this._config.show_services === false) return "";
    const toggles = kidServiceToggles(this._state, this._config.kid, this._config.services);
    if (!toggles.length) return "";
    const lock = needsCode(this._hass, "open", this._parent);
    const pills = toggles.map((t) => `<div class="pill ${t.open ? "vert" : "svc-off"}" data-action="${esc(`svc:${t.service}`)}" role="switch" aria-checked="${t.open}"
        title="${esc(t.open ? `${t.label} débloqué : toucher pour bloquer` : `${t.label} bloqué : toucher pour autoriser`)}">`
      + `<ha-icon icon="${t.open ? "mdi:check-circle" : "mdi:cancel"}"></ha-icon>${esc(t.label)}`
      + `${!t.open && lock ? '<ha-icon class="lock" icon="mdi:lock"></ha-icon>' : ""}</div>`);
    return `<div class="section"><div class="label muted">Services sur demande</div><div class="pills">${pills.join("")}</div></div>`;
  }

  // Autorisations en cours (✕ : annuler, après confirmation).
  _exceptions(now) {
    const list = kidExceptions(this._state, this._config.kid);
    if (!list.length) return "";
    const armed = this._confirm.armed;
    const pills = list.map((e) => {
      const action = `cancel:${e.id}`;
      return pill({ action, icon: "mdi:check", label: formatPill(e, now), cls: "vert", confirm: true, armed: armed === action, trailing: "mdi:close" });
    });
    return `<div class="section"><div class="label muted">Autorisations en cours</div><div class="pills">${pills.join("")}</div></div>`;
  }

  // Bonus de temps d'écran : seulement pour un enfant qui a un quota aujourd'hui.
  _bonus(v) {
    if (this._config.show_bonus === false || v.remaining == null) return "";
    const lock = needsCode(this._hass, "bonus", this._parent);
    const armed = this._confirm.armed;
    const pills = bonusMinutes(this._config).map((m) => {
      const action = `bonus:${m}`;
      return pill({ action, icon: "mdi:plus", label: bonusLabel(m), cls: "bleu", confirm: !lock, armed: armed === action, lock });
    });
    return `<div class="section"><div class="label muted">Bonus de temps d'écran</div><div class="pills">${pills.join("")}</div></div>`;
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
    const kid_id = this._config.kid;
    const name = this._config.name || kidView(this._state, kid_id).name || kid_id;
    if (action === "homework") {
      return this._withCode("homework", `Devoirs terminés · ${name}`, "Valider", "homework_done", { kid_id });
    }
    if (action === "timer-stop") return this._call("stop_timer", { kid_id });
    if (action.startsWith("timer:")) {
      const minutes = Number(action.slice(6));
      return this._withCode("timer", `Minuteur ${minutes} min · ${name}`, "Démarrer", "start_timer", { kid_id, minutes });
    }
    if (action.startsWith("bonus:")) {
      const minutes = Number(action.slice(6));
      return this._withCode("bonus", `${bonusLabel(minutes)} · ${name}`, "Ajouter", "add_bonus", { kid_id, minutes });
    }
    if (action.startsWith("svc:")) return this._toggleService(action.slice(4), name);
    if (action.startsWith("cancel:")) return this._call("cancel_exception", { exception_id: action.slice(7) });
  }

  // Action protégée : directe pour un admin (déjà confirmée par deux appuis), sinon fenêtre du code.
  _withCode(kind, title, submitLabel, service, data) {
    if (!needsCode(this._hass, kind, this._parent)) return this._call(service, data);
    const kid_id = data.kid_id;
    let request = null;
    if (canRequest(this._hass, this._state, this._parent)) {
      // « Demander » : l'enfant de la carte, sans code ; le parent répond depuis la notification.
      const extra = kind === "timer" ? { minutes: data.minutes, options: TIMER_MINUTES }
        : kind === "bonus" ? { minutes: data.minutes, options: bonusMinutes(this._config) } : {};
      request = {
        kids: null,
        pending: findRequest(this._state, { kind, kid_id })?.status === "pending",
        onRequest: () => callAction(this._hass, "request", { kind, kid_id, ...extra }),
      };
    }
    openActionDialog(this.shadowRoot, {
      title, needCode: true, submitLabel, request,
      onSubmit: ({ code }) => callAction(this._hass, service, data, code),
    });
  }

  // Bascule d'un service pour l'enfant : autoriser (fenêtre de durée, code si non admin) ou
  // bloquer. Les exceptions de ce service visant l'enfant ou ses appareils sont d'abord annulées.
  async _toggleService(service, name) {
    const kid_id = this._config.kid;
    const t = kidServiceToggles(this._state, kid_id).find((x) => x.service === service);
    if (!t) return;
    const replace = async (code, open, minutes) => {
      for (const exception_id of t.exceptions) {
        const res = await callAction(this._hass, "cancel_exception", { exception_id }, code);
        if (!res.ok) return res;
      }
      if (!open && !t.openedElsewhere) return { ok: true };
      const data = { kid_id, service, open };
      if (minutes) data.minutes = minutes;
      return callAction(this._hass, "exception", data, code);
    };
    if (t.open) {
      const res = await replace(undefined, false);
      this._error.set(res.ok ? "" : res.error || "Action refusée");
      return this._render();
    }
    let request = null;
    if (canRequest(this._hass, this._state, this._parent)) {
      request = {
        kids: null,
        pending: findRequest(this._state, { kind: "open", kid_id, service })?.status === "pending",
        onRequest: ({ duration }) => {
          const data = { kind: "open", kid_id, service, options: DURATIONS.map((d) => d.value), replace: t.exceptions };
          if (duration) data.minutes = duration;
          return callAction(this._hass, "request", data);
        },
      };
    }
    openActionDialog(this.shadowRoot, {
      title: `Autoriser ${t.label} · ${name}`,
      durations: DURATIONS,
      needCode: needsCode(this._hass, "open", this._parent),
      submitLabel: "Autoriser",
      request,
      onSubmit: ({ duration, code }) => replace(code, true, duration),
    });
  }

  // Actions sans fenêtre : l'erreur s'affiche en bas de la carte.
  async _call(service, data) {
    const res = await callAction(this._hass, service, data);
    this._error.set(res.ok ? "" : res.error || "Action refusée");
    this._render();
  }
}

if (!customElements.get("parental-kid-card")) {
  customElements.define("parental-kid-card", ParentalKidCard);
}
