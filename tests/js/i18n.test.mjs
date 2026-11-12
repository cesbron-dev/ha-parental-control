// Tests de la traduction des cartes (i18n.js et catalogues en / fr), sans DOM.
import test from "node:test";
import assert from "node:assert/strict";

process.env.TZ = "America/Toronto";
const { lang, t, tLang, hasKey, formatTime, formatDuration, formatPercent } = await import(
  "../../custom_components/parental_control/www/i18n.js"
);
const { default: en } = await import("../../custom_components/parental_control/www/i18n/en.js");
const { default: fr } = await import("../../custom_components/parental_control/www/i18n/fr.js");

const FR = { locale: { language: "fr" } };
const EN = { locale: { language: "en" } };

// Clés à points de toutes les feuilles d'un catalogue imbriqué.
function flatKeys(obj, prefix = "") {
  return Object.entries(obj).flatMap(([k, v]) => (
    v && typeof v === "object" ? flatKeys(v, `${prefix}${k}.`) : [`${prefix}${k}`]
  ));
}

test("langue de l'utilisateur", () => {
  assert.equal(lang({ locale: { language: "fr-CA" } }), "fr");
  assert.equal(lang({ locale: { language: "de" } }), "en");
  assert.equal(lang({ language: "fr" }), "fr");
  assert.equal(lang({ locale: { language: "en-GB" }, language: "fr" }), "en");
  assert.equal(lang({ locale: {}, language: "fr_BE" }), "fr");
  assert.equal(lang(undefined), "en");
  assert.equal(lang(null), "en");
});

test("paramètres et replis", () => {
  assert.equal(t({ locale: { language: "fr" } }, "no.such.key"), "no.such.key");
  assert.equal(t(FR, "common.loading"), "Chargement…");
  assert.equal(t(EN, "common.loading"), "Loading…");
  assert.equal(t({ locale: { language: "de" } }, "common.loading"), "Loading…");
  // un paramètre manquant reste visible plutôt que de lever
  assert.equal(t(EN, "request.expires_in"), "Expires in {minutes} min");
  assert.equal(t(FR, "common.loading.deeper"), "common.loading.deeper");
  assert.equal(t(FR, "common"), "common"); // un nœud n'est pas un texte
  assert.ok(hasKey("reason.blocked"));
  assert.ok(!hasKey("reason.nope"));
});

test("clé paramétrée en anglais et en français", () => {
  assert.equal(t(FR, "request.expires_in", { minutes: 12 }), "Expire dans 12 min");
  assert.equal(t(EN, "request.expires_in", { minutes: 12 }), "Expires in 12 min");
  assert.equal(t(FR, "reason.allowed_until", { until: "20:00" }), "Écrans autorisés jusqu'à 20:00");
  assert.equal(t(EN, "reason.allowed_until", { until: "20:00" }), "Screens allowed until 20:00");
  assert.equal(tLang("fr-CA", "cards.kid.name"), "Contrôle parental — Enfant");
  assert.equal(tLang("es", "cards.kid.name"), "Parental control — Child");
  assert.equal(tLang(undefined, "cards.kid.name"), "Parental control — Child");
});

test("mêmes clés en anglais et en français", () => {
  assert.deepEqual(flatKeys(en).sort(), flatKeys(fr).sort());
  for (const key of flatKeys(en)) {
    const leaf = key.split(".").reduce((o, k) => o[k], en);
    assert.equal(typeof leaf, "string", key);
  }
});

test("libellés des types de journée, segments et états", () => {
  for (const d of ["school", "weekend", "day_off", "holidays"]) assert.ok(hasKey(`daytype.${d}`), d);
  for (const s of ["free", "after_homework", "quota", "on_demand", "blocked"]) assert.ok(hasKey(`segment.${s}`), s);
  for (const s of ["allowed", "blocked", "waiting_homework", "waiting_timer", "quota_exhausted", "on_demand", "paused"]) {
    assert.ok(hasKey(`status.${s}`), s);
  }
});

test("raisons du moteur et erreurs des demandes au catalogue", () => {
  for (const code of ["allowed_until", "allowed_until_midnight", "open_for", "waiting_homework", "quota_exhausted",
    "waiting_timer", "on_demand", "blocked", "paused", "opened_manually", "closed_manually"]) {
    assert.ok(hasKey(`reason.${code}`), code);
  }
  for (const code of ["impossible", "unknown_choice"]) assert.ok(hasKey(`request.reason.${code}`), code);
  for (const code of ["code_required", "code_invalid", "not_configured", "unknown_kid", "unknown_resource",
    "invalid_target", "timer_active", "not_in_quota", "quota_exhausted", "code_locked", "nintendo_use_bonus",
    "requests_disabled", "request_pending", "too_many_requests", "invalid_request"]) {
    assert.ok(hasKey(`error.${code}`), code);
  }
  assert.equal(t(FR, "error.unknown_kid", { kid_id: "hugo" }), "Enfant inconnu : hugo.");
  assert.equal(t(EN, "error.code_locked", { seconds: "30" }), "Too many wrong parent codes. Try again in 30 s.");
});

test("heures selon la langue et le format choisi", () => {
  const iso = "2026-10-30T16:05:00-04:00";
  assert.equal(formatTime(FR, iso), "16:05");
  assert.equal(formatTime(FR, "2026-10-30T07:05:00-04:00"), "07:05");
  assert.match(formatTime(EN, iso), /^4:05\sPM$/);
  assert.match(formatTime(EN, "2026-10-30T07:05:00-04:00"), /^7:05\sAM$/);
  assert.equal(formatTime({ locale: { language: "en", time_format: "24" } }, iso), "16:05");
  assert.equal(formatTime({ locale: { language: "en", time_format: "24" } }, "2026-10-30T07:05:00-04:00"), "07:05");
  assert.match(formatTime({ locale: { language: "fr", time_format: "12" } }, iso), /^4:05/);
});

test("durées : style du moteur en anglais, inchangé en français", () => {
  assert.equal(formatDuration(EN, 45), "45 min");
  assert.equal(formatDuration(EN, 120), "2 h");
  assert.equal(formatDuration(EN, 90), "1 h 30 min");
  assert.equal(formatDuration(EN, 65), "1 h 5 min");
  assert.equal(formatDuration(FR, 45), "45 min");
  assert.equal(formatDuration(FR, 120), "2 h");
  assert.equal(formatDuration(FR, 65), "1 h 05");
  assert.equal(formatDuration(FR, null), "Jusqu'au prochain changement");
  assert.equal(formatDuration(EN, null), "Until the next change");
});

test("pourcentage selon la langue", () => {
  assert.equal(formatPercent(EN, 42), "42%");
  assert.match(formatPercent(FR, 42), /^42\s%$/);
});

test("erreurs des actions identiques aux traductions du serveur", async () => {
  const { readFile } = await import("node:fs/promises");
  for (const [code, catalogue] of [["en", en], ["fr", fr]]) {
    const url = new URL(`../../custom_components/parental_control/translations/${code}.json`, import.meta.url);
    const { exceptions } = JSON.parse(await readFile(url, "utf8"));
    const server = Object.fromEntries(Object.entries(exceptions)
      .filter(([key]) => !key.startsWith("config_"))
      .map(([key, { message }]) => [key, message]));
    assert.deepEqual(catalogue.error, server, code);
  }
});

test("raisons du moteur et raisons d'échec identiques au catalogue du serveur", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("../../custom_components/parental_control/core/i18n.py", import.meta.url), "utf8");
  const [, enPart, frPart] = source.split(/^ {4}"(?:en|fr)": \{$/m);
  const server = (part, prefix) => Object.fromEntries([...part.matchAll(/^ {8}"([\w.]+)": "(.*)",$/gm)]
    .filter(([, key]) => key.startsWith(prefix))
    .map(([, key, text]) => [key.slice(prefix.length), text]));
  for (const [catalogue, part] of [[en, enPart], [fr, frPart]]) {
    assert.deepEqual(catalogue.reason, server(part, "reason."));
    assert.deepEqual(catalogue.request.reason, server(part, "request.reason."));
  }
});

test("heure murale « HH:MM » du moteur au format de l'utilisateur", async () => {
  const { formatClock } = await import("../../custom_components/parental_control/www/i18n.js");
  assert.match(formatClock(EN, "20:00"), /^8:00\sPM$/);
  assert.match(formatClock(EN, "07:05"), /^7:05\sAM$/);
  assert.equal(formatClock({ locale: { language: "en", time_format: "24" } }, "07:05"), "07:05");
  assert.equal(formatClock(FR, "20:00"), "20:00");
  assert.equal(formatClock(FR, "07:05"), "07:05");
  assert.equal(formatClock(FR, "minuit"), "minuit");
  assert.equal(formatClock(FR, undefined), "");
});

test("repères d'heure de la frise", async () => {
  const { formatHour } = await import("../../custom_components/parental_control/www/i18n.js");
  assert.deepEqual([0, 6, 12, 18, 24].map((h) => formatHour(FR, h)), ["0h", "6h", "12h", "18h", "24h"]);
  assert.deepEqual([0, 6, 12, 18, 24].map((h) => formatHour(EN, h).replace(/\s/, " ")), ["12 AM", "6 AM", "12 PM", "6 PM", "12 AM"]);
  assert.equal(formatHour({ locale: { language: "en", time_format: "24" } }, 18), "18h");
});
