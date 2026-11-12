// Style « verre » commun aux cartes, pilules et confirmation en deux appuis.
import { esc, needsCode, bonusLabel, requestsFor, requestLine } from "./lib.js";
import { t } from "./i18n.js";

export const CONFIRM_MS = 3000;
const ERROR_MS = 6000;

export const BASE_CSS = `
  /* Jetons de couleur : verre sombre par défaut, verre clair si HA est en thème clair (attribut
     « light » posé par applyTheme). */
  :host {
    display: block;
    --g-text: #e8edf5; --g-muted: rgba(232,237,245,.62); --g-faint: rgba(232,237,245,.45);
    --g-card: linear-gradient(135deg, rgba(255,255,255,.11), rgba(255,255,255,.03)), rgba(24,32,46,.78);
    --g-dialog: linear-gradient(135deg, rgba(255,255,255,.11), rgba(255,255,255,.03)), rgba(24,32,46,.96);
    --g-border: rgba(255,255,255,.18); --g-sep: rgba(255,255,255,.15);
    --g-shadow: 0 8px 32px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.12);
    --g-dialog-shadow: 0 8px 32px rgba(0,0,0,.5); --g-backdrop: rgba(0,0,0,.55);
    --g-soft: rgba(255,255,255,.06); --g-soft-hover: rgba(255,255,255,.12); --g-soft-strong: rgba(255,255,255,.22);
    --g-line: rgba(255,255,255,.2); --g-strong-line: #fff; --g-track: rgba(0,0,0,.35); --g-input: rgba(0,0,0,.3);
    --g-ondemand: rgba(255,255,255,.3); --g-ok: #3ddc84; --g-warn: #ffb347; --g-bad: #ff6b6b; --g-accent: #5fb3ff; --g-now: #fff;
    --g-green: #8ff0b5; --g-green-bg: rgba(61,220,132,.12); --g-green-line: rgba(61,220,132,.5);
    --g-violet: #d4a5ff; --g-violet-bg: rgba(160,90,240,.18); --g-violet-line: rgba(190,130,255,.55);
    --g-red: #ff7b7b; --g-red-bg: rgba(230,60,60,.16); --g-red-line: rgba(255,110,110,.55);
    --g-blue: #7cc0ff; --g-blue-bg: rgba(60,140,255,.12); --g-blue-line: rgba(110,170,255,.6);
    --g-blue-sel: rgba(60,140,255,.32); --g-blue-sel-text: #fff;
    --g-sim: #ffb347; --g-sim-bg: rgba(255,170,60,.16); --g-sim-line: rgba(255,170,60,.55);
  }
  :host([light]) {
    --g-text: #1c2533; --g-muted: rgba(28,37,51,.64); --g-faint: rgba(28,37,51,.5);
    --g-card: linear-gradient(135deg, rgba(255,255,255,.92), rgba(255,255,255,.72)), rgba(240,244,250,.85);
    --g-dialog: linear-gradient(135deg, rgba(255,255,255,.98), rgba(255,255,255,.92)), #f4f7fb;
    --g-border: rgba(20,40,70,.12); --g-sep: rgba(20,40,70,.12);
    --g-shadow: 0 6px 24px rgba(20,40,70,.12), inset 0 1px 0 rgba(255,255,255,.8);
    --g-dialog-shadow: 0 8px 32px rgba(20,40,70,.25); --g-backdrop: rgba(20,30,45,.35);
    --g-soft: rgba(20,40,70,.04); --g-soft-hover: rgba(20,40,70,.09); --g-soft-strong: rgba(20,40,70,.14);
    --g-line: rgba(20,40,70,.18); --g-strong-line: #1c2533; --g-track: rgba(20,40,70,.12); --g-input: rgba(20,40,70,.05);
    --g-ondemand: rgba(20,40,70,.32); --g-ok: #138a4c; --g-warn: #b86a00; --g-bad: #c83232; --g-accent: #1a6fc4; --g-now: #1c2533;
    --g-green: #137a43; --g-green-bg: rgba(30,170,95,.12); --g-green-line: rgba(30,150,85,.45);
    --g-violet: #7a3fc4; --g-violet-bg: rgba(140,80,220,.1); --g-violet-line: rgba(140,80,220,.4);
    --g-red: #c02e2e; --g-red-bg: rgba(220,50,50,.08); --g-red-line: rgba(200,50,50,.4);
    --g-blue: #1a62b0; --g-blue-bg: rgba(40,110,220,.08); --g-blue-line: rgba(40,110,220,.4);
    --g-blue-sel: #2f7fe0; --g-blue-sel-text: #fff;
    --g-sim: #9a5a00; --g-sim-bg: rgba(230,140,20,.14); --g-sim-line: rgba(200,120,10,.5);
  }
  ha-card {
    display: block; position: relative; overflow: hidden; height: 100%; box-sizing: border-box;
    padding: 18px 20px; border-radius: 18px; color: var(--g-text);
    background: var(--g-card); border: 1px solid var(--g-border); box-shadow: var(--g-shadow);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    font-family: var(--ha-font-family-body, Roboto, sans-serif);
  }
  .title { font-size: 1.15rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; margin: 0 0 4px; }
  .titlebar { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .titlebar .title { min-width: 0; margin: 0 0 4px; }
  .sim {
    flex: none; display: inline-block; vertical-align: middle; margin-bottom: 4px; padding: 2px 8px; border-radius: 6px;
    font-size: .65rem; font-weight: 700; letter-spacing: .08em; text-transform: none;
    color: var(--g-sim); background: var(--g-sim-bg); border: 1px solid var(--g-sim-line);
  }
  .muted { color: var(--g-muted); }
  .ok { color: var(--g-ok); } .warn { color: var(--g-warn); } .bad { color: var(--g-bad); }
  .badge { font-weight: 600; font-size: .8rem; letter-spacing: .04em; text-transform: uppercase; }
  .row { display: flex; align-items: center; gap: 12px; }
  .grow { flex: 1; min-width: 0; }
  .pills { display: flex; flex-wrap: wrap; gap: 10px; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px; cursor: pointer; user-select: none;
    padding: 6px 12px; border-radius: 8px; font-size: .9rem; font-weight: 500;
    background: var(--g-soft); border: 1px solid var(--g-line); color: inherit;
    font-family: inherit; transition: background .15s, transform .1s;
  }
  .pill:hover { background: var(--g-soft-hover); }
  .pill:active { transform: scale(.97); }
  .pill[disabled] { opacity: .4; pointer-events: none; }
  .pill.armed { background: var(--g-soft-strong); border-color: var(--g-strong-line); }
  .pill ha-icon { --mdc-icon-size: 18px; }
  .pill ha-icon.lock { --mdc-icon-size: 14px; opacity: .8; }
  .pill.vert { color: var(--g-green); background: var(--g-green-bg); border-color: var(--g-green-line); }
  .pill.violet { color: var(--g-violet); background: var(--g-violet-bg); border-color: var(--g-violet-line); }
  .pill.rouge { color: var(--g-red); background: var(--g-red-bg); border-color: var(--g-red-line); text-transform: uppercase; letter-spacing: .03em; }
  .pill.bleu { color: var(--g-blue); background: var(--g-blue-bg); border-color: var(--g-blue-line); min-width: 52px; justify-content: center; }
  .pill.selected { background: var(--g-blue-sel); border-color: var(--g-blue); color: var(--g-blue-sel-text); }
  .error { color: var(--g-red); font-size: .9rem; }
  .reqline { margin-top: 8px; font-size: .9rem; color: var(--g-muted); }
`;

// Frise d'une journée (segments colorés, exceptions hachurées, trait « maintenant », heures),
// commune aux cartes frise et enfant.
export const TIMELINE_CSS = `
  .tl { position: relative; height: 16px; border-radius: 8px; overflow: hidden; margin: 6px 0 2px; background: var(--g-track); }
  .tl.tap { cursor: pointer; }
  .tl div { position: absolute; top: 0; bottom: 0; }
  .free { background: linear-gradient(90deg, #2fbf71, #3ddc84); }
  .after_homework { background: linear-gradient(90deg, #ff9a3c, #ffb347); }
  .quota { background: linear-gradient(90deg, #2f7fe0, #5fb3ff); }
  .on_demand { background: var(--g-ondemand); }
  .blocked { background: linear-gradient(90deg, #c0392b, #ff5f6d); }
  .exc { background: repeating-linear-gradient(45deg, rgba(124,192,255,.9) 0 4px, rgba(124,192,255,.4) 4px 8px); }
  .tl .now { width: 3px; background: var(--g-now); box-shadow: 0 0 6px var(--g-now); }
  .hours { position: relative; height: 1em; margin-top: 10px; font-size: .7rem; color: var(--g-faint); }
  .hours span { position: absolute; transform: translateX(-50%); }
  .hours span:first-child { transform: none; }
  .hours span:last-child { transform: translateX(-100%); }
`;

// Thème des cartes : verre clair quand HA est en thème clair (`hass.themes.darkMode` faux).
export function applyTheme(el, hass) {
  const dark = hass?.themes?.darkMode;
  if (dark === undefined) return;
  el.toggleAttribute("light", !dark);
}

// Pilule cliquable ; `label` est échappé ici. Armée, elle affiche « Confirmer ? » dans la langue de
// `hass`. `trailing` : icône en fin de pilule (✕) ; `lock` : petit cadenas (code parent demandé).
export function pill({ action, icon, label, cls = "", confirm = false, armed = false, disabled = false, lock = false, trailing = null, hass = null }) {
  return `<div class="pill ${cls} ${armed ? "armed" : ""}" data-action="${esc(action)}"${confirm ? " data-confirm" : ""}${disabled ? " disabled" : ""}>`
    + `<ha-icon icon="${armed ? "mdi:check" : icon}"></ha-icon>${esc(armed ? t(hass, "pill.confirm") : label)}`
    + `${trailing && !armed ? `<ha-icon icon="${trailing}"></ha-icon>` : ""}`
    + `${lock && !armed ? '<ha-icon class="lock" icon="mdi:lock"></ha-icon>' : ""}</div>`;
}

// Confirmation en deux appuis : le 1er appui arme la pilule, le 2e dans les CONFIRM_MS exécute ;
// sinon désarmement automatique. `onChange` est appelé à chaque changement pour redessiner.
export class ConfirmState {
  constructor(onChange) {
    this.armed = null;
    this._timer = null;
    this._onChange = onChange;
  }

  // Renvoie vrai si l'action doit s'exécuter (2e appui sur la même pilule).
  press(id) {
    if (this.armed === id) {
      this._set(null);
      return true;
    }
    this._set(id);
    return false;
  }

  clear() {
    if (this.armed !== null) this._set(null);
    else clearTimeout(this._timer);
  }

  _set(id) {
    clearTimeout(this._timer);
    this.armed = id;
    if (id !== null) this._timer = setTimeout(() => this._set(null), CONFIRM_MS);
    this._onChange?.();
  }
}

// Pilules bonus (+15m…) : avec code, la fenêtre de saisie sert de confirmation ; sinon deux appuis.
export function bonusPills(hass, minutes, armed, parent = false) {
  const lock = needsCode(hass, "bonus", parent);
  return minutes.map((m) => {
    const action = `bonus:${m}`;
    return pill({ action, icon: "mdi:plus", label: bonusLabel(m), cls: "bleu", confirm: !lock, armed: armed === action, lock, hass });
  });
}

// Message d'erreur d'une action sans fenêtre, effacé seul après ERROR_MS.
export class ErrorNotice {
  constructor(onChange) {
    this.text = "";
    this._timer = null;
    this._onChange = onChange;
  }

  set(text) {
    clearTimeout(this._timer);
    this.text = text;
    if (text) {
      this._timer = setTimeout(() => {
        this.text = "";
        this._onChange?.();
      }, ERROR_MS);
    }
  }

  clear() {
    clearTimeout(this._timer);
  }
}

// Lignes d'état des demandes de temps d'une carte (sous les pastilles, comme la ligne d'erreur).
export function requestLines(state, target, hass) {
  return requestsFor(state, target).map((r) => `<div class="reqline">${esc(requestLine(r, hass))}</div>`).join("");
}
