// Style « verre » commun aux cartes, pilules et confirmation en deux appuis.
import { esc } from "./lib.js";

export const CONFIRM_MS = 3000;

export const BASE_CSS = `
  :host { display: block; }
  ha-card {
    display: block; position: relative; overflow: hidden; height: 100%; box-sizing: border-box;
    padding: 18px 20px; border-radius: 18px; color: #e8edf5;
    background: linear-gradient(135deg, rgba(255,255,255,.11), rgba(255,255,255,.03)), rgba(24,32,46,.78);
    border: 1px solid rgba(255,255,255,.18);
    box-shadow: 0 8px 32px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.12);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    font-family: var(--ha-font-family-body, Roboto, sans-serif);
  }
  .title { font-size: 1.15rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; margin: 0 0 4px; }
  .muted { color: rgba(232,237,245,.62); }
  .ok { color: #3ddc84; } .warn { color: #ffb347; } .bad { color: #ff6b6b; }
  .badge { font-weight: 600; font-size: .8rem; letter-spacing: .04em; text-transform: uppercase; }
  .row { display: flex; align-items: center; gap: 12px; }
  .grow { flex: 1; min-width: 0; }
  .pills { display: flex; flex-wrap: wrap; gap: 10px; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px; cursor: pointer; user-select: none;
    padding: 6px 12px; border-radius: 8px; font-size: .9rem; font-weight: 500;
    background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.2); color: inherit;
    font-family: inherit; transition: background .15s, transform .1s;
  }
  .pill:hover { background: rgba(255,255,255,.12); }
  .pill:active { transform: scale(.97); }
  .pill[disabled] { opacity: .4; pointer-events: none; }
  .pill.armed { background: rgba(255,255,255,.22); border-color: #fff; }
  .pill ha-icon { --mdc-icon-size: 18px; }
  .pill ha-icon.lock { --mdc-icon-size: 14px; opacity: .8; }
  .pill.vert { color: #8ff0b5; background: rgba(61,220,132,.12); border-color: rgba(61,220,132,.5); }
  .pill.violet { color: #d4a5ff; background: rgba(160,90,240,.18); border-color: rgba(190,130,255,.55); }
  .pill.rouge { color: #ff7b7b; background: rgba(230,60,60,.16); border-color: rgba(255,110,110,.55); text-transform: uppercase; letter-spacing: .03em; }
  .pill.bleu { color: #7cc0ff; background: rgba(60,140,255,.12); border-color: rgba(110,170,255,.6); min-width: 52px; justify-content: center; }
  .pill.selected { background: rgba(60,140,255,.32); border-color: #7cc0ff; color: #fff; }
  .error { color: #ff7b7b; font-size: .9rem; }
`;

// Pilule cliquable ; `label` est échappé ici. Armée, elle affiche « Confirmer ? ».
// `trailing` : icône en fin de pilule (✕) ; `lock` : petit cadenas (code parent demandé).
export function pill({ action, icon, label, cls = "", confirm = false, armed = false, disabled = false, lock = false, trailing = null }) {
  return `<div class="pill ${cls} ${armed ? "armed" : ""}" data-action="${esc(action)}"${confirm ? " data-confirm" : ""}${disabled ? " disabled" : ""}>`
    + `<ha-icon icon="${armed ? "mdi:check" : icon}"></ha-icon>${armed ? "Confirmer ?" : esc(label)}`
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
