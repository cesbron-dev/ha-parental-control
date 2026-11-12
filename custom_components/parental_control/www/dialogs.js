// Fenêtre d'action des cartes (« Autoriser… », saisie du code) : un <dialog> natif dans le
// shadow DOM de la carte, affiché en surimpression (couche supérieure du navigateur).
import {
  esc, needsCode, bonusLabel, keypadInput, canRequest, findRequest, ownerChoices, bonusMinutes,
} from "./lib.js";
import { callAction } from "./connection.js";
import { t } from "./i18n.js";

const DIALOG_CSS = `
  dialog {
    box-sizing: border-box; width: min(440px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow: auto;
    padding: 18px 20px; border-radius: 18px; color: var(--g-text);
    background: var(--g-dialog); border: 1px solid var(--g-border); box-shadow: var(--g-dialog-shadow);
    font-family: var(--ha-font-family-body, Roboto, sans-serif);
  }
  dialog::backdrop { background: var(--g-backdrop); }
  .dlg-label { margin: 14px 0 8px; font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; color: var(--g-muted); }
  .dlg-code {
    box-sizing: border-box; width: 100%; min-height: 48px; padding: 10px 12px; border-radius: 8px;
    font-size: 1.6rem; letter-spacing: .35em; text-align: center;
    background: var(--g-input); border: 1px solid var(--g-line);
  }
  /* pavé numérique tactile : pas de clavier natif qui recouvre la fenêtre sur la tablette */
  .keypad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px; }
  .keypad button {
    min-height: 56px; border-radius: 10px; font-size: 1.4rem; font-weight: 500; cursor: pointer;
    color: inherit; background: var(--g-soft); border: 1px solid var(--g-line);
    font-family: inherit; touch-action: manipulation; user-select: none;
  }
  .keypad button:active { background: var(--g-soft-strong); }
  .keypad button:disabled { opacity: .4; }
  .error { margin-top: 10px; min-height: 1.2em; }
  .dlg-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
`;

const pickPills = (name, items, selected) => items
  .map((it, i) => `<button type="button" class="pill bleu ${i === selected ? "selected" : ""}" data-pick="${name}" data-index="${i}">${esc(it.label)}</button>`)
  .join("");

// Ouvre la fenêtre dans `root` (shadow root de la carte) ; une seule à la fois. Textes dans la
// langue de `hass`.
// - choices / durations : listes `{value, label}` à choisir (« Quoi », « Pendant »), ou null pour omettre ;
// - needCode : affiche un pavé numérique tactile ; le code saisi est vidé après chaque appel ;
// - onSubmit({choice, duration, code}) -> Promise<{ok} | {ok:false, error}> : la fenêtre se ferme sur
//   succès, affiche l'erreur sinon ;
// - request : `{kids, pending, onRequest({choice, duration, kid})}` ou null. Ajoute « Demander »
//   (compte non admin), sans code : `kids` ([{value, label}], ou null) ajoute « Qui demande ? » ;
//   `pending` désactive le bouton (« En attente… »). Même retour que `onSubmit`.
// Renvoie `{close}`.
export function openActionDialog(root, { hass, title, choices = null, durations = null, needCode = false, submitLabel = null, request = null, onSubmit }) {
  root.querySelector("dialog.parental")?.close();
  const sel = { choice: choices ? 0 : null, duration: null, kid: request?.kids?.length === 1 ? 0 : null };
  let busy = false;

  const dlg = document.createElement("dialog");
  dlg.className = "parental";
  dlg.innerHTML = `<style>${DIALOG_CSS}</style>
    <div class="title">${esc(title)}</div>
    ${choices ? `<div class="dlg-label">${esc(t(hass, "dialog.what"))}</div><div class="pills">${pickPills("choice", choices, sel.choice)}</div>` : ""}
    ${durations ? `<div class="dlg-label">${esc(t(hass, "dialog.for"))}</div><div class="pills">${pickPills("duration", durations, sel.duration)}</div>` : ""}
    ${request?.kids ? `<div class="dlg-label">${esc(t(hass, "dialog.who"))}</div><div class="pills">${pickPills("kid", request.kids, sel.kid)}</div>` : ""}
    ${needCode ? `<div class="dlg-label">${esc(t(hass, "dialog.code"))}</div>
      <div class="dlg-code" aria-label="${esc(t(hass, "dialog.code_entered"))}"></div>
      <div class="keypad">
        ${["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => `<button type="button" data-key="${d}">${d}</button>`).join("")}
        <button type="button" data-key="clear" aria-label="${esc(t(hass, "dialog.clear_all"))}">C</button>
        <button type="button" data-key="0">0</button>
        <button type="button" data-key="back" aria-label="${esc(t(hass, "dialog.erase"))}">⌫</button>
      </div>` : ""}
    <div class="error"></div>
    <div class="dlg-actions">
      ${request ? `<button type="button" class="pill" data-btn="request">${esc(t(hass, request.pending ? "dialog.waiting" : "dialog.request"))}</button>` : ""}
      <button type="button" class="pill" data-btn="cancel">${esc(t(hass, "dialog.cancel"))}</button>
      <button type="button" class="pill bleu" data-btn="ok">${esc(submitLabel ?? t(hass, "dialog.ok"))}</button>
    </div>`;

  // Le code ne vit que dans cette variable, le temps de la fenêtre ; l'écran n'en montre que des points.
  const codeEl = dlg.querySelector(".dlg-code");
  let code = "";
  const setCode = (value) => {
    if (value !== code) errEl.textContent = ""; // nouvelle saisie : l'erreur précédente s'efface
    code = value;
    if (codeEl) codeEl.textContent = "•".repeat(code.length);
  };
  const okBtn = dlg.querySelector('[data-btn="ok"]');
  const errEl = dlg.querySelector(".error");
  const requestBtn = dlg.querySelector('[data-btn="request"]');

  const refresh = () => {
    for (const b of dlg.querySelectorAll("[data-pick]")) {
      b.classList.toggle("selected", Number(b.dataset.index) === sel[b.dataset.pick]);
      b.disabled = busy;
    }
    const ready = (!durations || sel.duration !== null) && (!codeEl || code.length >= 4);
    okBtn.disabled = busy || !ready;
    if (requestBtn) {
      // la demande n'attend pas le code : il suffit d'avoir choisi la durée et l'enfant
      requestBtn.disabled = busy || request.pending || (durations && sel.duration === null) || (request.kids && sel.kid === null);
    }
    dlg.querySelector('[data-btn="cancel"]').disabled = busy;
    for (const k of dlg.querySelectorAll("[data-key]")) k.disabled = busy;
  };

  const pickedChoice = () => (choices ? choices[sel.choice].value : null);
  const pickedDuration = () => (durations ? durations[sel.duration].value : null);
  const sendSubmit = () => onSubmit({ choice: pickedChoice(), duration: pickedDuration(), code: codeEl ? code : null });
  const sendRequest = () => request.onRequest({
    choice: pickedChoice(), duration: pickedDuration(), kid: request.kids ? request.kids[sel.kid].value : null,
  });

  const submit = async (btn, run) => {
    if (btn.disabled) return;
    busy = true;
    errEl.textContent = "";
    refresh();
    let res;
    try {
      res = await run();
    } finally {
      // Le code n'est jamais gardé : vidé dès la réponse du moteur.
      setCode("");
      busy = false;
      refresh(); // assurance si `onSubmit` a levé : les boutons ne restent pas désactivés
    }
    if (res?.ok) {
      dlg.close();
      return;
    }
    errEl.textContent = res?.error || t(hass, "common.action_refused");
    refresh();
  };

  dlg.addEventListener("click", (ev) => {
    const pick = ev.target.closest("[data-pick]");
    if (pick && !busy) {
      sel[pick.dataset.pick] = Number(pick.dataset.index);
      refresh();
      return;
    }
    const key = ev.target.closest("[data-key]");
    if (key && !busy) {
      setCode(keypadInput(code, key.dataset.key));
      refresh();
      return;
    }
    const btn = ev.target.closest("[data-btn]");
    if (!btn || btn.disabled) return;
    if (btn.dataset.btn === "cancel") dlg.close();
    else if (btn.dataset.btn === "request") submit(requestBtn, sendRequest);
    else submit(okBtn, sendSubmit);
  });
  // Clavier physique (ordinateur) : chiffres, retour arrière, Entrée.
  dlg.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      submit(okBtn, sendSubmit);
      return;
    }
    if (!codeEl || busy) return;
    const k = ev.key === "Backspace" ? "back" : ev.key;
    if (k === "back" || /^\d$/.test(k)) {
      ev.preventDefault();
      setCode(keypadInput(code, k));
      refresh();
    }
  });
  // Échap (événement cancel) ou fermeture : la fenêtre disparaît du DOM avec son champ de code.
  dlg.addEventListener("close", () => {
    setCode("");
    dlg.remove();
  });

  root.appendChild(dlg);
  refresh();
  dlg.showModal();
  return { close: () => dlg.open && dlg.close() };
}

// Bonus nintendo : admin -> `call` direct (déjà confirmé par deux appuis) ; sinon fenêtre de saisie du code.
export function runBonus(root, hass, { resource_id, minutes, title, call, request = null, parent = false }) {
  const data = { resource_id, minutes };
  if (!needsCode(hass, "bonus", parent)) return call("add_bonus", data);
  openActionDialog(root, {
    hass,
    title: `${bonusLabel(minutes)} · ${title}`,
    needCode: true,
    submitLabel: t(hass, "dialog.add"),
    request,
    onSubmit: ({ code }) => callAction(hass, "add_bonus", data, code),
  });
}

// Option `request` d'un bonus sur une ressource (cartes appareil et Switch) : « Demander » pour un
// compte non admin, au nom d'un des propriétaires ; null sinon. L'état « en attente » n'est connu
// que s'il n'y a qu'un propriétaire (sinon l'enfant n'est pas encore choisi).
export function bonusRequest(hass, state, config, resource_id, minutes, parent = false) {
  if (!canRequest(hass, state, parent)) return null;
  const owners = state.resources?.[resource_id]?.owners ?? [];
  const pending = owners.length === 1
    && findRequest(state, { kind: "bonus", kid_id: owners[0], resource_id })?.status === "pending";
  return {
    kids: ownerChoices(state, owners),
    pending,
    onRequest: ({ kid }) => callAction(hass, "request", {
      kind: "bonus", kid_id: kid, resource_id, minutes, options: bonusMinutes(config),
    }),
  };
}
