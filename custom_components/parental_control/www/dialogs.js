// Fenêtre d'action des cartes (« Autoriser… », saisie du code) : un <dialog> natif dans le
// shadow DOM de la carte, affiché en surimpression (couche supérieure du navigateur).
import { esc, needsCode, bonusLabel, keypadInput } from "./lib.js";
import { callAction } from "./connection.js";

const DIALOG_CSS = `
  dialog {
    box-sizing: border-box; width: min(440px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow: auto;
    padding: 18px 20px; border-radius: 18px; color: #e8edf5;
    background: linear-gradient(135deg, rgba(255,255,255,.11), rgba(255,255,255,.03)), rgba(24,32,46,.96);
    border: 1px solid rgba(255,255,255,.18); box-shadow: 0 8px 32px rgba(0,0,0,.5);
    font-family: var(--ha-font-family-body, Roboto, sans-serif);
  }
  dialog::backdrop { background: rgba(0,0,0,.55); }
  .dlg-label { margin: 14px 0 8px; font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; color: rgba(232,237,245,.62); }
  .dlg-code {
    box-sizing: border-box; width: 100%; min-height: 48px; padding: 10px 12px; border-radius: 8px;
    font-size: 1.6rem; letter-spacing: .35em; text-align: center;
    background: rgba(0,0,0,.3); border: 1px solid rgba(255,255,255,.25);
  }
  /* pavé numérique tactile : pas de clavier natif qui recouvre la fenêtre sur la tablette */
  .keypad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px; }
  .keypad button {
    min-height: 56px; border-radius: 10px; font-size: 1.4rem; font-weight: 500; cursor: pointer;
    color: inherit; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.2);
    font-family: inherit; touch-action: manipulation; user-select: none;
  }
  .keypad button:active { background: rgba(255,255,255,.22); }
  .keypad button:disabled { opacity: .4; }
  .error { margin-top: 10px; min-height: 1.2em; }
  .dlg-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
`;

const pickPills = (name, items, selected) => items
  .map((it, i) => `<button type="button" class="pill bleu ${i === selected ? "selected" : ""}" data-pick="${name}" data-index="${i}">${esc(it.label)}</button>`)
  .join("");

// Ouvre la fenêtre dans `root` (shadow root de la carte) ; une seule à la fois.
// - choices / durations : listes `{value, label}` à choisir (« Quoi », « Pendant »), ou null pour omettre ;
// - needCode : affiche un pavé numérique tactile ; le code saisi est vidé après chaque appel ;
// - onSubmit({choice, duration, code}) -> Promise<{ok} | {ok:false, error}> : la fenêtre se ferme sur
//   succès, affiche l'erreur sinon.
// Renvoie `{close}`.
export function openActionDialog(root, { title, choices = null, durations = null, needCode = false, submitLabel = "Valider", onSubmit }) {
  root.querySelector("dialog.parental")?.close();
  const sel = { choice: choices ? 0 : null, duration: null };
  let busy = false;

  const dlg = document.createElement("dialog");
  dlg.className = "parental";
  dlg.innerHTML = `<style>${DIALOG_CSS}</style>
    <div class="title">${esc(title)}</div>
    ${choices ? `<div class="dlg-label">Quoi</div><div class="pills">${pickPills("choice", choices, sel.choice)}</div>` : ""}
    ${durations ? `<div class="dlg-label">Pendant</div><div class="pills">${pickPills("duration", durations, sel.duration)}</div>` : ""}
    ${needCode ? `<div class="dlg-label">Code parent</div>
      <div class="dlg-code" aria-label="Code parent saisi"></div>
      <div class="keypad">
        ${["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => `<button type="button" data-key="${d}">${d}</button>`).join("")}
        <button type="button" data-key="clear" aria-label="Effacer tout">C</button>
        <button type="button" data-key="0">0</button>
        <button type="button" data-key="back" aria-label="Effacer">⌫</button>
      </div>` : ""}
    <div class="error"></div>
    <div class="dlg-actions">
      <button type="button" class="pill" data-btn="cancel">Annuler</button>
      <button type="button" class="pill bleu" data-btn="ok">${esc(submitLabel)}</button>
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

  const refresh = () => {
    for (const b of dlg.querySelectorAll("[data-pick]")) {
      b.classList.toggle("selected", Number(b.dataset.index) === sel[b.dataset.pick]);
      b.disabled = busy;
    }
    const ready = (!durations || sel.duration !== null) && (!codeEl || code.length >= 4);
    okBtn.disabled = busy || !ready;
    dlg.querySelector('[data-btn="cancel"]').disabled = busy;
    for (const k of dlg.querySelectorAll("[data-key]")) k.disabled = busy;
  };

  const submit = async () => {
    if (okBtn.disabled) return;
    busy = true;
    errEl.textContent = "";
    refresh();
    let res;
    try {
      res = await onSubmit({
        choice: choices ? choices[sel.choice].value : null,
        duration: durations ? durations[sel.duration].value : null,
        code: codeEl ? code : null,
      });
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
    errEl.textContent = res?.error || "Action refusée";
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
    else submit();
  });
  // Clavier physique (ordinateur) : chiffres, retour arrière, Entrée.
  dlg.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      submit();
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
export function runBonus(root, hass, { resource_id, minutes, title, call }) {
  const data = { resource_id, minutes };
  if (!needsCode(hass, "bonus")) return call("ajouter_bonus", data);
  openActionDialog(root, {
    title: `${bonusLabel(minutes)} · ${title}`,
    needCode: true,
    submitLabel: "Ajouter",
    onSubmit: ({ code }) => callAction(hass, "ajouter_bonus", data, code),
  });
}
