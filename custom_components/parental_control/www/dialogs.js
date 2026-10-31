// Fenêtre d'action des cartes (« Autoriser… », saisie du code) : un <dialog> natif dans le
// shadow DOM de la carte, affiché en surimpression (couche supérieure du navigateur).
import { esc, needsCode, bonusLabel } from "./lib.js";
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
    box-sizing: border-box; width: 100%; padding: 10px 12px; border-radius: 8px; font-size: 1.1rem; letter-spacing: .2em;
    color: inherit; background: rgba(0,0,0,.3); border: 1px solid rgba(255,255,255,.25); font-family: inherit;
  }
  .dlg-code:focus { outline: none; border-color: #7cc0ff; }
  .error { margin-top: 10px; min-height: 1.2em; }
  .dlg-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px; }
`;

const pickPills = (name, items, selected) => items
  .map((it, i) => `<button type="button" class="pill bleu ${i === selected ? "selected" : ""}" data-pick="${name}" data-index="${i}">${esc(it.label)}</button>`)
  .join("");

// Ouvre la fenêtre dans `root` (shadow root de la carte) ; une seule à la fois.
// - choices / durations : listes `{value, label}` à choisir (« Quoi », « Pendant »), ou null pour omettre ;
// - needCode : affiche un champ mot de passe, vidé après chaque appel ;
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
      <input class="dlg-code" type="password" inputmode="numeric" autocomplete="off" name="parental-code">` : ""}
    <div class="error"></div>
    <div class="dlg-actions">
      <button type="button" class="pill" data-btn="cancel">Annuler</button>
      <button type="button" class="pill bleu" data-btn="ok">${esc(submitLabel)}</button>
    </div>`;

  const input = dlg.querySelector(".dlg-code");
  const okBtn = dlg.querySelector('[data-btn="ok"]');
  const errEl = dlg.querySelector(".error");

  const refresh = () => {
    for (const b of dlg.querySelectorAll("[data-pick]")) {
      b.classList.toggle("selected", Number(b.dataset.index) === sel[b.dataset.pick]);
      b.disabled = busy;
    }
    const ready = (!durations || sel.duration !== null) && (!input || input.value !== "");
    okBtn.disabled = busy || !ready;
    dlg.querySelector('[data-btn="cancel"]').disabled = busy;
    if (input) input.disabled = busy;
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
        code: input ? input.value : null,
      });
    } finally {
      // Le code n'est jamais gardé : vidé dès la réponse du moteur.
      if (input) input.value = "";
      busy = false;
      refresh(); // assurance si `onSubmit` a levé : les boutons ne restent pas désactivés
    }
    if (res?.ok) {
      dlg.close();
      return;
    }
    errEl.textContent = res?.error || "Action refusée";
    refresh();
    input?.focus();
  };

  dlg.addEventListener("click", (ev) => {
    const pick = ev.target.closest("[data-pick]");
    if (pick && !busy) {
      sel[pick.dataset.pick] = Number(pick.dataset.index);
      refresh();
      return;
    }
    const btn = ev.target.closest("[data-btn]");
    if (!btn || btn.disabled) return;
    if (btn.dataset.btn === "cancel") dlg.close();
    else submit();
  });
  input?.addEventListener("input", refresh);
  input?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") submit();
  });
  // Échap (événement cancel) ou fermeture : la fenêtre disparaît du DOM avec son champ de code.
  dlg.addEventListener("close", () => {
    if (input) input.value = "";
    dlg.remove();
  });

  root.appendChild(dlg);
  refresh();
  dlg.showModal();
  input?.focus();
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
