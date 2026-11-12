// Tests de la logique des éditeurs visuels de cartes (editor-lib.js), sans DOM.
import test from "node:test";
import assert from "node:assert/strict";

const { editorSchema, editorConfig, editorData } = await import("../../custom_components/parental_control/www/editor-lib.js");

const state = {
  kids: { gabin: { name: "Gabin" }, leo: { name: "Léo" } },
  resources: {
    tv: { name: "Télé salon", kind: "media_player", kinds: ["media_player"] },
    ipad: { name: "iPad", kind: "adguard_services", kinds: ["adguard_services"] },
    mixte: { name: "Télé chambre", kind: "media_player", kinds: ["adguard_services", "media_player"] },
    switch: { name: "Switch", kind: "nintendo" },
  },
};

const field = (schema, name) => schema.find((f) => f.name === name);

test("resource card: every resource is offered, plus name and icon", () => {
  const schema = editorSchema("resource", state, { resource: "tv" });
  const res = field(schema, "resource");
  assert.equal(res.required, true);
  assert.deepEqual(res.selector.select.options.map((o) => o.value), ["tv", "ipad", "mixte", "switch"]);
  const labels = res.selector.select.options.map((o) => o.label);
  assert.deepEqual(labels, ["Télé salon (Télé)", "iPad (AdGuard)", "Télé chambre", "Switch (Nintendo)"]);
  assert.ok(field(schema, "name").selector.text);
  assert.ok(field(schema, "icon").selector.icon);
});

test("switch card: only Nintendo resources, plus a title", () => {
  const schema = editorSchema("switch", state, {});
  assert.deepEqual(field(schema, "resource").selector.select.options.map((o) => o.value), ["switch"]);
  assert.ok(field(schema, "title").selector.text);
});

test("an unknown current resource stays selectable", () => {
  const schema = editorSchema("resource", state, { resource: "ancien" });
  const opts = field(schema, "resource").selector.select.options;
  assert.deepEqual(opts.at(-1), { value: "ancien", label: "ancien (introuvable)" });
});

test("without engine state the resource falls back to free text", () => {
  for (const s of [null, undefined, { resources: {} }]) {
    assert.deepEqual(field(editorSchema("resource", s, {}), "resource").selector, { text: {} });
  }
});

test("timeline card: kids as a multiple choice", () => {
  const sel = field(editorSchema("timeline", state, {}), "kids").selector.select;
  assert.equal(sel.multiple, true);
  assert.deepEqual(sel.options, [{ value: "gabin", label: "Gabin" }, { value: "leo", label: "Léo" }]);
  // Un enfant déjà choisi mais retiré des règles reste visible pour pouvoir le décocher.
  const kept = field(editorSchema("timeline", state, { kids: ["mael"] }), "kids").selector.select.options;
  assert.deepEqual(kept.at(-1), { value: "mael", label: "mael (introuvable)" });
});

test("editorConfig drops empty optional fields and keeps the rest", () => {
  assert.deepEqual(
    editorConfig({ type: "custom:parental-resource-card", resource: "tv", name: "Télé" }, { resource: "ipad", name: "", icon: undefined }),
    { type: "custom:parental-resource-card", resource: "ipad" },
  );
  assert.deepEqual(
    editorConfig({ type: "custom:parental-timeline-card", kids: ["gabin"] }, { kids: [] }),
    { type: "custom:parental-timeline-card" }, // aucun coché : tous les enfants
  );
  assert.deepEqual(editorConfig({ type: "t" }, { kids: ["leo"] }), { type: "t", kids: ["leo"] });
});

test("bonus minutes: chosen as text in the form, saved as sorted numbers", () => {
  for (const card of ["resource", "switch"]) {
    const sel = field(editorSchema(card, state, {}), "bonus_minutes").selector.select;
    assert.equal(sel.multiple, true);
    assert.equal(sel.custom_value, true);
    assert.ok(sel.options.some((o) => o.value === "15"));
  }
  assert.deepEqual(editorData({ resource: "switch", bonus_minutes: [15, 30] }, "switch"), { resource: "switch", bonus_minutes: ["15", "30"] });
  assert.deepEqual(editorConfig({ type: "t" }, { bonus_minutes: ["60", "10", "abc", "10", "0"] }), { type: "t", bonus_minutes: [10, 60] });
  assert.deepEqual(editorConfig({ type: "t", bonus_minutes: [15] }, { bonus_minutes: ["abc"] }), { type: "t" });
});

test("resource card: on-demand services toggles, shown by default, list from the device", () => {
  const st = { services: {youtube:{name:"YouTube",adguard:true},netflix:{name:"Netflix",adguard:true},tiktok:{name:"TikTok",adguard:true}}, resources: { tv: { name: "Télé", kind: "media_player", kinds: ["adguard_services", "media_player"], on_demand: ["youtube", "netflix"], leisure: ["tiktok"] } } };
  const schema = editorSchema("resource", st, { resource: "tv" });
  assert.ok(field(schema, "show_services").selector.boolean);
  assert.deepEqual(field(schema, "services").selector.select.options, [
    { value: "youtube", label: "YouTube" }, { value: "netflix", label: "Netflix" },
  ]);
  assert.equal(editorData({ resource: "tv" }).show_services, true);
  assert.equal(editorData({ resource: "tv", show_services: false }).show_services, false);
  assert.deepEqual(editorConfig({ type: "t", resource: "tv" }, { show_services: true, services: [] }), { type: "t", resource: "tv" });
  assert.deepEqual(editorConfig({ type: "t", resource: "tv" }, { show_services: false }), { type: "t", resource: "tv", show_services: false });
});

test("kid card: kid choice, sections shown by default, the kid's on-demand services", () => {
  const st = {
    services: { youtube: { name: "YouTube", adguard: true }, tiktok: { name: "TikTok", adguard: true } },
    kids: { mael: { name: "Maël" }, leo: { name: "Léo" } },
    resources: {
      tv: { kinds: ["adguard_services", "media_player"], owners: ["mael", "leo"], on_demand: ["youtube"] },
      ipad: { kinds: ["adguard_services"], owners: ["leo"], on_demand: ["tiktok"] },
    },
  };
  const schema = editorSchema("kid", st, { kid: "mael" });
  assert.deepEqual(field(schema, "kid").selector.select.options, [{ value: "mael", label: "Maël" }, { value: "leo", label: "Léo" }]);
  assert.deepEqual(field(schema, "services").selector.select.options, [{ value: "youtube", label: "YouTube" }]);
  for (const key of ["show_timeline", "show_services", "show_bonus"]) assert.ok(field(schema, key).selector.boolean);
  assert.deepEqual(field(editorSchema("kid", null, {}), "kid").selector, { text: {} });
  const data = editorData({ kid: "mael", show_bonus: false }, "kid");
  assert.deepEqual([data.show_timeline, data.show_services, data.show_bonus], [true, true, false]);
  assert.deepEqual(editorConfig({ type: "t", kid: "mael" }, { show_timeline: true, show_services: true, show_bonus: false }),
    { type: "t", kid: "mael", show_bonus: false });
});

test("services fields: noms du parent, filtre AdGuard / labels", () => {
  const s = {
    services: {
      internet: { name: "Internet", adguard: false, labels: true },
      jeux: { name: "Jeux vidéo", adguard: true, labels: true },
    },
    kids: { mael: { name: "Maël", on_demand: ["internet"], label_services: [{ service: "internet", blocked: false }] } },
    resources: { ipad: { name: "iPad", owners: ["mael"], kind: "adguard_services", kinds: ["adguard_services"], on_demand: ["internet", "jeux"], label_services: [] } },
  };
  const opts = (schema) => schema.find((f) => f.name === "services").selector.select.options;
  // Appareil AdGuard : « internet » (labels seuls, non ciblé) est masqué.
  assert.deepEqual(opts(editorSchema("resource", s, { resource: "ipad" })), [{ value: "jeux", label: "Jeux vidéo" }]);
  // Enfant : AdGuard (jeux) + service que ses interrupteurs visent (internet).
  assert.deepEqual(opts(editorSchema("kid", s, { kid: "mael" })), [
    { value: "jeux", label: "Jeux vidéo" }, { value: "internet", label: "Internet" },
  ]);
});
