// Traduction des cartes et de l'écran « Demandes » : langue de l'utilisateur HA, catalogues en / fr,
// heures, durées et pourcentages. Sans DOM : importable depuis Node.
import en from "./i18n/en.js";
import fr from "./i18n/fr.js";

const CATALOGUES = { en, fr };
const FALLBACK = "en";

// « fr-CA », « fr_BE », « FR » -> « fr » ; une langue sans catalogue -> « en ».
function baseLanguage(code) {
  const base = String(code ?? "").split(/[-_]/)[0].toLowerCase();
  return Object.hasOwn(CATALOGUES, base) ? base : FALLBACK;
}

// Langue de l'utilisateur : `hass.locale.language`, sinon `hass.language`, sinon anglais.
export function lang(hass) {
  return baseLanguage(hass?.locale?.language || hass?.language);
}

// Texte d'une clé à points dans un catalogue, ou undefined (clé absente ou nœud non terminal).
function lookup(code, key) {
  let node = CATALOGUES[code];
  for (const part of String(key).split(".")) {
    if (node === null || typeof node !== "object" || !Object.hasOwn(node, part)) return undefined;
    node = node[part];
  }
  return typeof node === "string" ? node : undefined;
}

// Remplace `{name}` par le paramètre ; un paramètre absent reste visible tel quel.
function fill(template, params) {
  return template.replace(/\{(\w+)\}/g, (all, name) => (
    params && Object.hasOwn(params, name) && params[name] != null ? String(params[name]) : all
  ));
}

// La clé existe-t-elle (en anglais, catalogue de référence ; les deux ont les mêmes clés) ?
export function hasKey(key) {
  return lookup(FALLBACK, key) !== undefined;
}

// Texte de `key` dans la langue `code` (langue brute, ex. `navigator.language`) ; repli sur
// l'anglais, puis sur la clé elle-même.
export function tLang(code, key, params = {}) {
  const template = lookup(baseLanguage(code), key) ?? lookup(FALLBACK, key);
  return template === undefined ? key : fill(template, params);
}

// Texte de `key` dans la langue de l'utilisateur de `hass`.
export function t(hass, key, params = {}) {
  return tLang(lang(hass), key, params);
}

// Cycle horaire choisi dans le profil HA (`hass.locale.time_format`) ; sinon celui de la langue.
function hourCycle(hass) {
  const format = hass?.locale?.time_format;
  if (format === "12") return "h12";
  if (format === "24") return "h23";
  return undefined;
}

// Langue et options `Intl` d'une heure : cycle du profil, sinon celui de la langue ; sur 24 h,
// l'heure garde ses deux chiffres (« 07:05 »), sur 12 h, non (« 7:05 AM »).
function clockFormat(hass, extra = {}) {
  const code = lang(hass);
  const cycle = hourCycle(hass)
    ?? new Intl.DateTimeFormat(code, { hour: "numeric" }).resolvedOptions().hourCycle;
  const twelve = cycle === "h11" || cycle === "h12";
  return {
    twelve,
    format: new Intl.DateTimeFormat(code, { hour: twelve ? "numeric" : "2-digit", minute: "2-digit", hourCycle: cycle, ...extra }),
  };
}

// Heure locale d'une date ISO, au format de la langue : « 16:05 », « 07:05 », « 4:05 PM ».
export function formatTime(hass, iso) {
  return clockFormat(hass).format.format(new Date(iso));
}

// Heure murale « HH:MM » (sans date ni fuseau, ex. paramètre d'une raison du moteur) au format de
// la langue ; un texte qui n'est pas une heure est rendu tel quel.
export function formatClock(hass, hhmm) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm ?? ""));
  if (!m || Number(m[1]) > 23 || Number(m[2]) > 59) return String(hhmm ?? "");
  return clockFormat(hass, { timeZone: "UTC" }).format.format(new Date(Date.UTC(1970, 0, 1, Number(m[1]), Number(m[2]))));
}

// Repère d'heure entière de l'axe de la frise (0 à 24) : « 6h » sur 24 h, « 6 AM » sur 12 h.
export function formatHour(hass, hour) {
  if (!clockFormat(hass).twelve) return t(hass, "time.hour", { hour });
  return new Intl.DateTimeFormat(lang(hass), { hour: "numeric", hourCycle: hourCycle(hass), timeZone: "UTC" })
    .format(new Date(Date.UTC(1970, 0, 1, hour % 24)));
}

// Durée en minutes, comme le moteur : « 45 min », « 2 h », « 1 h 30 min » (fr : « 1 h 05 ») ;
// null -> « Jusqu'au prochain changement ».
export function formatDuration(hass, minutes) {
  if (minutes == null) return t(hass, "duration.until_next_change");
  const total = Math.max(0, Math.round(Number(minutes) || 0));
  return durationText(hass, "duration", total);
}

// Gabarits `<prefix>.minutes`, `.hours` et `.hours_minutes` ; `{mm}` : minutes sur deux chiffres.
export function durationText(hass, prefix, total) {
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  const params = { hours, minutes, mm: String(minutes).padStart(2, "0") };
  if (!hours) return t(hass, `${prefix}.minutes`, params);
  if (!minutes) return t(hass, `${prefix}.hours`, params);
  return t(hass, `${prefix}.hours_minutes`, params);
}

// Pourcentage entier : « 42% », « 42 % ».
export function formatPercent(hass, pct) {
  return new Intl.NumberFormat(lang(hass), { style: "percent", maximumFractionDigits: 0 }).format(pct / 100);
}
