// Logique pure des éditeurs visuels de cartes : schéma `ha-form` construit à partir de l'état du
// moteur (appareils et enfants proposés en liste) et nettoyage de la config produite, sans DOM.

const KIND_LABELS = { media_player: "Télé", adguard_services: "AdGuard", nintendo: "Nintendo" };

const text = (name, label, helper) => ({ name, label, helper, selector: { text: {} } });

// Les choix d'un `select` sont des textes : les minutes bonus passent en texte dans le formulaire
// et reviennent en nombres dans la config (une valeur saisie à la main est acceptée).
const BONUS_FIELD = {
  name: "bonus_minutes",
  label: "Minutes bonus proposées",
  helper: "Aucune : 15, 30 et 60 min",
  selector: {
    select: {
      multiple: true,
      custom_value: true,
      options: [5, 10, 15, 30, 45, 60, 90, 120].map((m) => ({ value: String(m), label: `${m} min` })),
    },
  },
};

// Choix proposés : ceux du moteur, plus la valeur actuelle si elle n'y est plus (pour la voir et
// la changer plutôt qu'un champ vide).
function withCurrent(options, current) {
  const values = Array.isArray(current) ? current : current ? [current] : [];
  const missing = values.filter((v) => !options.some((o) => o.value === v));
  return [...options, ...missing.map((v) => ({ value: v, label: `${v} (introuvable)` }))];
}

function resourceField(state, current, kind) {
  const options = Object.entries(state?.resources ?? {})
    .filter(([, r]) => !kind || r.kind === kind)
    .map(([id, r]) => ({ value: id, label: kind ? r.name || id : `${r.name || id} (${KIND_LABELS[r.kind] ?? r.kind})` }));
  const field = { name: "resource", label: "Appareil", required: true };
  // Sans état du moteur (indisponible), l'id se saisit à la main.
  if (Object.keys(state?.resources ?? {}).length === 0) return { ...field, selector: { text: {} } };
  return { ...field, selector: { select: { mode: "dropdown", options: withCurrent(options, current) } } };
}

// Schéma `ha-form` de l'éditeur d'une carte : `card` vaut "resource", "switch" ou "timeline".
export function editorSchema(card, state, config) {
  if (card === "resource") {
    return [
      resourceField(state, config?.resource),
      text("name", "Nom affiché", "Vide : le nom de l'appareil dans les règles"),
      { name: "icon", label: "Icône", helper: "Vide : selon le type d'appareil", selector: { icon: {} } },
      { ...BONUS_FIELD, helper: `${BONUS_FIELD.helper} (Switch seulement)` },
    ];
  }
  if (card === "switch") {
    return [
      resourceField(state, config?.resource, "nintendo"),
      text("title", "Titre", "Vide : Nintendo Switch"),
      BONUS_FIELD,
    ];
  }
  const kids = Object.entries(state?.kids ?? {}).map(([id, k]) => ({ value: id, label: k.name || id }));
  return [{
    name: "kids",
    label: "Enfants affichés",
    helper: "Aucun coché : tous les enfants",
    selector: { select: { multiple: true, mode: "list", options: withCurrent(kids, config?.kids) } },
  }];
}

// Données affichées par le formulaire.
export function editorData(config) {
  const out = { ...config };
  if (Array.isArray(out.bonus_minutes)) out.bonus_minutes = out.bonus_minutes.map(String);
  return out;
}

// Config de la carte après une saisie : champs vides retirés (valeur par défaut de la carte) ;
// une liste d'enfants vide veut dire « tous », donc retirée elle aussi.
export function editorConfig(config, value) {
  const out = { ...config, ...value };
  if (Array.isArray(out.bonus_minutes)) {
    const minutes = out.bonus_minutes.map(Number).filter((m) => Number.isInteger(m) && m > 0);
    out.bonus_minutes = [...new Set(minutes)].sort((a, b) => a - b);
  }
  for (const [key, v] of Object.entries(out)) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) delete out[key];
  }
  return out;
}
