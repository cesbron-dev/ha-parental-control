// Tests de la logique des éditeurs visuels de cartes (editor-lib.js), sans DOM.
import test from "node:test";
import assert from "node:assert/strict";

const { editorSchema, editorConfig, editorData } = await import("../../custom_components/parental_control/www/editor-lib.js");

const state = {
  kids: { gabin: { name: "Gabin" }, leo: { name: "Léo" } },
  resources: {
    tv: { name: "Télé salon", kind: "media_player" },
    ipad: { name: "iPad", kind: "adguard_services" },
    switch: { name: "Switch", kind: "nintendo" },
  },
};

const field = (schema, name) => schema.find((f) => f.name === name);

test("resource card: every resource is offered, plus name and icon", () => {
  const schema = editorSchema("resource", state, { resource: "tv" });
  const res = field(schema, "resource");
  assert.equal(res.required, true);
  assert.deepEqual(res.selector.select.options.map((o) => o.value), ["tv", "ipad", "switch"]);
  assert.equal(res.selector.select.options[0].label, "Télé salon (Télé)");
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
  assert.deepEqual(editorData({ resource: "switch", bonus_minutes: [15, 30] }), { resource: "switch", bonus_minutes: ["15", "30"] });
  assert.deepEqual(editorConfig({ type: "t" }, { bonus_minutes: ["60", "10", "abc", "10", "0"] }), { type: "t", bonus_minutes: [10, 60] });
  assert.deepEqual(editorConfig({ type: "t", bonus_minutes: [15] }, { bonus_minutes: ["abc"] }), { type: "t" });
});
