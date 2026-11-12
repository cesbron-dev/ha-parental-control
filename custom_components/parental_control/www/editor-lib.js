// Logique pure des éditeurs visuels de cartes : schéma `ha-form` construit à partir de l'état du
// moteur (appareils et enfants proposés en liste) et nettoyage de la config produite, sans DOM.

import { serviceLabel, serviceShownOnResource } from "./lib.js";
import { t, hasKey } from "./i18n.js";

const text = (name, label, helper) => ({ name, label, helper, selector: { text: {} } });

// Les choix d'un `select` sont des textes : les minutes bonus passent en texte dans le formulaire
// et reviennent en nombres dans la config (une valeur saisie à la main est acceptée).
const bonusField = (hass, helperKey = "editor.bonus_helper") => ({
  name: "bonus_minutes",
  label: t(hass, "editor.bonus_minutes"),
  helper: t(hass, helperKey),
  selector: {
    select: {
      multiple: true,
      custom_value: true,
      options: [5, 10, 15, 30, 45, 60, 90, 120].map((m) => ({ value: String(m), label: t(hass, "editor.minutes", { minutes: m }) })),
    },
  },
});

// Choix proposés : ceux du moteur, plus la valeur actuelle si elle n'y est plus (pour la voir et
// la changer plutôt qu'un champ vide).
function withCurrent(options, current, hass) {
  const values = Array.isArray(current) ? current : current ? [current] : [];
  const missing = values.filter((v) => !options.some((o) => o.value === v));
  return [...options, ...missing.map((v) => ({ value: v, label: t(hass, "editor.not_found", { value: v }) }))];
}

// Nom seul ; le type entre parenthèses seulement pour un appareil à un seul type (pas pour un mixte).
function resourceLabel(r, id, hass) {
  const name = r.name || id;
  const kinds = r.kinds ?? [r.kind];
  if (kinds.length !== 1) return name;
  const key = `editor.kind.${kinds[0]}`;
  return `${name} (${hasKey(key) ? t(hass, key) : kinds[0]})`;
}

function resourceField(state, current, kind, hass) {
  const options = Object.entries(state?.resources ?? {})
    .filter(([, r]) => !kind || r.kind === kind)
    .map(([id, r]) => ({ value: id, label: kind ? r.name || id : resourceLabel(r, id, hass) }));
  const field = { name: "resource", label: t(hass, "editor.device"), required: true };
  // Sans état du moteur (indisponible), l'id se saisit à la main.
  if (Object.keys(state?.resources ?? {}).length === 0) return { ...field, selector: { text: {} } };
  return { ...field, selector: { select: { mode: "dropdown", options: withCurrent(options, current, hass) } } };
}

// Services affichés sur la carte : les services sur demande de l'appareil ; aucun coché : tous.
function servicesField(state, config, hass) {
  const r = state?.resources?.[config?.resource];
  const ids = (r?.on_demand ?? []).filter((s) => serviceShownOnResource(state, r, s));
  return {
    name: "services",
    label: t(hass, "editor.services"),
    helper: t(hass, "editor.services_helper_device"),
    selector: { select: { multiple: true, mode: "list", options: withCurrent(ids.map((s) => ({ value: s, label: serviceLabel(s, state?.services) })), config?.services, hass) } },
  };
}

// Schéma `ha-form` de l'éditeur d'une carte : `card` vaut "resource", "switch", "timeline" ou "kid" ;
// libellés dans la langue de `hass`.
export function editorSchema(card, state, config, hass) {
  if (card === "resource") {
    return [
      resourceField(state, config?.resource, undefined, hass),
      text("name", t(hass, "editor.name"), t(hass, "editor.name_helper_device")),
      { name: "icon", label: t(hass, "editor.icon"), helper: t(hass, "editor.icon_helper"), selector: { icon: {} } },
      bonusField(hass, "editor.bonus_helper_switch"),
      { name: "show_services", label: t(hass, "editor.show_services"), helper: t(hass, "editor.show_services_helper_device"), selector: { boolean: {} } },
      servicesField(state, config, hass),
    ];
  }
  if (card === "switch") {
    return [
      resourceField(state, config?.resource, "nintendo", hass),
      text("title", t(hass, "editor.title"), t(hass, "editor.title_helper")),
      bonusField(hass),
    ];
  }
  const kids = Object.entries(state?.kids ?? {}).map(([id, k]) => ({ value: id, label: k.name || id }));
  if (card === "kid") {
    const kidField = { name: "kid", label: t(hass, "editor.kid"), required: true };
    // Services sur demande de l'enfant : ceux de ses appareils AdGuard qui concernent AdGuard,
    // plus ceux que ses interrupteurs par label visent.
    const kid = state?.kids?.[config?.kid];
    const kidOnDemand = [...new Set([
      ...Object.values(state?.resources ?? {})
        .filter((r) => (r.owners ?? []).includes(config?.kid) && (r.kinds ?? [r.kind]).includes("adguard_services"))
        .flatMap((r) => r.on_demand ?? [])
        .filter((s) => state?.services?.[s]?.adguard),
      ...(kid?.label_services ?? []).map((l) => l.service).filter((s) => (kid.on_demand ?? []).includes(s)),
    ])];
    return [
      kids.length ? { ...kidField, selector: { select: { mode: "dropdown", options: withCurrent(kids, config?.kid, hass) } } }
        : { ...kidField, selector: { text: {} } },
      text("name", t(hass, "editor.name"), t(hass, "editor.name_helper_kid")),
      { name: "show_timeline", label: t(hass, "editor.show_timeline"), selector: { boolean: {} } },
      { name: "show_services", label: t(hass, "editor.show_services"), helper: t(hass, "editor.show_services_helper_kid"), selector: { boolean: {} } },
      {
        name: "services", label: t(hass, "editor.services"), helper: t(hass, "editor.services_helper_kid"),
        selector: { select: { multiple: true, mode: "list", options: withCurrent(kidOnDemand.map((s) => ({ value: s, label: serviceLabel(s, state?.services) })), config?.services, hass) } },
      },
      { name: "show_bonus", label: t(hass, "editor.show_bonus"), helper: t(hass, "editor.show_bonus_helper"), selector: { boolean: {} } },
      bonusField(hass),
    ];
  }
  return [{
    name: "kids",
    label: t(hass, "editor.kids"),
    helper: t(hass, "editor.kids_helper"),
    selector: { select: { multiple: true, mode: "list", options: withCurrent(kids, config?.kids, hass) } },
  }];
}

const SHOWN_BY_DEFAULT = { resource: ["show_services"], kid: ["show_timeline", "show_services", "show_bonus"] };

// Données affichées par le formulaire (`card` : type de carte, comme pour editorSchema).
export function editorData(config, card = "resource") {
  const out = { ...config };
  if (Array.isArray(out.bonus_minutes)) out.bonus_minutes = out.bonus_minutes.map(String);
  // Sections affichées par défaut : la case est cochée tant que la config ne dit pas `false`.
  for (const key of SHOWN_BY_DEFAULT[card] ?? []) out[key] = out[key] !== false;
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
  for (const key of ["show_services", "show_timeline", "show_bonus"]) if (out[key] === true) delete out[key]; // par défaut
  for (const [key, v] of Object.entries(out)) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) delete out[key];
  }
  return out;
}
