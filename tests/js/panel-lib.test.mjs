import test from "node:test";
import assert from "node:assert/strict";

const {
  slugify, uniqueId, setPath, addKid, removeKid, addResource, removeResource,
  addDevice, removeDevice, addIntegration, removeIntegration, integrationKindsAllowed, moveDevice,
  addSegment, removeSegment, setMode, toggleOwner, toggleProfile, toggleListValue,
  profileGeometry, isDirty,
} = await import("../../custom_components/parental_control/www/panel-lib.js");

const draft = () => ({
  version: 2,
  default_leisure: ["youtube", "roblox"],
  calendar_map: {},
  notify: [],
  kids: [
    {
      id: "hugo", name: "Hugo", emoji: null, color: null, calendar: null,
      leisure_add: [], leisure_remove: [], resource_modes: { switch: "sur_demande", tv_adguard: "bloque" },
      profiles: {
        ecole: { segments: [{ start: "00:00", type: "bloque" }, { start: "16:00", type: "libre" }] },
        fin_de_semaine: { quota_minutes: 120, segments: [{ start: "00:00", type: "quota" }] },
      },
    },
  ],
  resources: [
    { id: "tv", name: "Télé", owners: ["hugo"], quota_minutes: {},
      devices: [{ name: "Télé", integrations: [{ kind: "media_player", entity_id: "media_player.tv" }] }] },
    { id: "tv_adguard", name: "Télé AdGuard", owners: ["hugo"], quota_minutes: {},
      devices: [{ name: "Box", integrations: [{ kind: "adguard_services", device_id: "a" }] }] },
    { id: "switch", name: "Switch", owners: ["hugo"], quota_minutes: {},
      devices: [{ name: "Switch", integrations: [{ kind: "nintendo", device_id: "d", limit_entity: "number.l",
        remaining_entity: "sensor.r", used_entity: "sensor.u" }] }] },
  ],
});

test("slugify", () => {
  assert.equal(slugify("Alice"), "alice");
  assert.equal(slugify("  iPad des enfants! "), "ipad_des_enfants");
  assert.equal(slugify("Télé (AdGuard)"), "tele_adguard");
  assert.equal(slugify("!!!"), "");
});

test("uniqueId", () => {
  assert.equal(uniqueId("zoe", ["hugo"]), "zoe");
  assert.equal(uniqueId("tv", ["tv", "tv_2"]), "tv_3");
  assert.equal(uniqueId("", []), "element");
});

test("setPath sets nested values, empty optional text becomes null", () => {
  const d = draft();
  setPath(d, "kids.0.name", "Gaby");
  assert.equal(d.kids[0].name, "Gaby");
  setPath(d, "kids.0.profiles.ecole.segments.1.start", "15:30");
  assert.equal(d.kids[0].profiles.ecole.segments[1].start, "15:30");
  setPath(d, "kids.0.emoji", "");
  assert.equal(d.kids[0].emoji, null);
  setPath(d, "kids.0.profiles.fin_de_semaine.quota_minutes", null);
  assert.equal("quota_minutes" in d.kids[0].profiles.fin_de_semaine, false);
  setPath(d, "kids.0.profiles.ecole.segments.0.warn_minutes", 10);
  setPath(d, "kids.0.profiles.ecole.segments.0.warn_minutes", null);
  assert.equal("warn_minutes" in d.kids[0].profiles.ecole.segments[0], false);
  setPath(d, "resources.0.quota_minutes.ecole", 90);
  assert.deepEqual(d.resources[0].quota_minutes, { ecole: 90 });
  setPath(d, "resources.0.devices.0.integrations.0.entity_id", "media_player.autre");
  assert.equal(d.resources[0].devices[0].integrations[0].entity_id, "media_player.autre");
});

test("addKid copies the first kid's profiles and gets a unique id", () => {
  const d = draft();
  const kid = addKid(d, "Zoé");
  assert.equal(kid.id, "zoe");
  assert.equal(d.kids.length, 2);
  assert.deepEqual(kid.profiles, d.kids[0].profiles);
  assert.notEqual(kid.profiles, d.kids[0].profiles); // copie, pas la même référence
  const empty = { ...draft(), kids: [] };
  const first = addKid(empty, "Hugo");
  assert.deepEqual(Object.keys(first.profiles).sort(), ["ecole", "fin_de_semaine"]);
  assert.deepEqual(first.profiles.ecole.segments, [{ start: "00:00", type: "bloque" }]);
});

test("removeKid also removes it from owners", () => {
  const d = draft();
  removeKid(d, 0);
  assert.equal(d.kids.length, 0);
  assert.deepEqual(d.resources[0].owners, []);
});

test("addResource crée une ressource v2 avec un appareil vide", () => {
  const d = draft();
  const r = addResource(d, "iPad");
  assert.equal(r.id, "ipad");
  assert.deepEqual(r, { id: "ipad", name: "iPad", owners: [], quota_minutes: {}, devices: [{ name: "iPad", integrations: [] }] });
  assert.equal(d.resources.at(-1), r);
  assert.equal(addResource(d, "Switch").id, "switch_2");
});

test("removeResource retire aussi les modes", () => {
  const d = draft();
  removeResource(d, 2); // la Switch
  assert.equal("switch" in d.kids[0].resource_modes, false);
  assert.equal(d.resources.length, 2);
});

test("addDevice / removeDevice", () => {
  const r = draft().resources[0];
  const dev = addDevice(r, "Box");
  assert.deepEqual(dev, { name: "Box", integrations: [] });
  assert.equal(r.devices.length, 2);
  removeDevice(r, 0);
  assert.deepEqual(r.devices, [dev]);
  removeDevice(r, 5); // index hors bornes : sans effet
  assert.equal(r.devices.length, 1);
});

test("addIntegration / removeIntegration", () => {
  const dev = { name: "x", integrations: [] };
  assert.deepEqual(addIntegration(dev, "adguard_services"), { kind: "adguard_services", device_id: "" });
  assert.deepEqual(addIntegration(dev, "media_player"), { kind: "media_player", entity_id: "" });
  assert.deepEqual(addIntegration(dev, "nintendo"),
    { kind: "nintendo", device_id: "", limit_entity: "", remaining_entity: "", used_entity: "" });
  assert.equal(dev.integrations.length, 3);
  removeIntegration(dev, 0);
  assert.deepEqual(dev.integrations.map((i) => i.kind), ["media_player", "nintendo"]);
});

test("integrationKindsAllowed", () => {
  const d = draft();
  assert.deepEqual(integrationKindsAllowed(addResource(d, "Vide")), ["media_player", "adguard_services", "nintendo"]);
  assert.deepEqual(integrationKindsAllowed(d.resources[0]), ["media_player", "adguard_services"]);
  assert.deepEqual(integrationKindsAllowed(d.resources[2]), []);
});

test("moveDevice déplace l'appareil et retire la ressource source devenue vide", () => {
  const d = draft();
  const box = d.resources[1].devices[0];
  assert.equal(moveDevice(d, 1, 0, 0), "tv_adguard");
  assert.deepEqual(d.resources.map((r) => r.id), ["tv", "switch"]);
  assert.equal("tv_adguard" in d.kids[0].resource_modes, false);
  assert.deepEqual(d.resources[0].devices.map((x) => x.name), ["Télé", "Box"]); // ajouté à la fin
  assert.equal(d.resources[0].devices[1], box);
});

test("moveDevice garde la ressource source si elle a encore des appareils", () => {
  const d = draft();
  addDevice(d.resources[0], "Autre");
  assert.equal(moveDevice(d, 0, 0, 1), null);
  assert.equal(d.resources.length, 3);
  assert.deepEqual(d.resources[0].devices.map((x) => x.name), ["Autre"]);
  assert.deepEqual(d.resources[1].devices.map((x) => x.name), ["Box", "Télé"]);
});

test("addSegment / removeSegment", () => {
  const segs = [{ start: "00:00", type: "bloque" }, { start: "16:00", type: "libre" }];
  addSegment(segs);
  assert.deepEqual(segs[2], { start: "17:00", type: "bloque" });
  const late = [{ start: "00:00", type: "bloque" }, { start: "23:30", type: "libre" }];
  addSegment(late);
  assert.equal(late[2].start, "23:59");
  removeSegment(segs, 0); // le premier (00:00) ne se supprime pas
  assert.equal(segs.length, 3);
  removeSegment(segs, 1);
  assert.deepEqual(segs.map((s) => s.start), ["00:00", "17:00"]);
});

test("setMode: suit_frise removes the entry", () => {
  const kid = draft().kids[0];
  setMode(kid, "tv", "bloque");
  assert.equal(kid.resource_modes.tv, "bloque");
  setMode(kid, "switch", "suit_frise");
  assert.deepEqual(kid.resource_modes, { tv_adguard: "bloque", tv: "bloque" });
});

test("toggleOwner and toggleListValue", () => {
  const r = draft().resources[0];
  toggleOwner(r, "hugo");
  assert.deepEqual(r.owners, []);
  toggleOwner(r, "zoe");
  assert.deepEqual(r.owners, ["zoe"]);
  const list = ["a"];
  toggleListValue(list, "b");
  toggleListValue(list, "a");
  assert.deepEqual(list, ["b"]);
});

test("toggleProfile only for optional days, copying fin_de_semaine", () => {
  const kid = draft().kids[0];
  toggleProfile(kid, "vacances");
  assert.deepEqual(kid.profiles.vacances, kid.profiles.fin_de_semaine);
  assert.notEqual(kid.profiles.vacances, kid.profiles.fin_de_semaine);
  toggleProfile(kid, "vacances");
  assert.equal("vacances" in kid.profiles, false);
  toggleProfile(kid, "ecole"); // obligatoire : rien
  assert.equal("ecole" in kid.profiles, true);
});

test("profileGeometry", () => {
  const g = profileGeometry([{ start: "00:00", type: "bloque" }, { start: "12:00", type: "libre" }, { start: "18:00", type: "bloque" }]);
  assert.deepEqual(g, [
    { left: 0, width: 50, type: "bloque" },
    { left: 50, width: 25, type: "libre" },
    { left: 75, width: 25, type: "bloque" },
  ]);
  assert.deepEqual(profileGeometry([{ start: "00:00", type: "bloque" }, { start: "zz", type: "libre" }]),
    [{ left: 0, width: 100, type: "bloque" }]); // heure invalide ignorée
});

test("isDirty", () => {
  const a = draft();
  const b = draft();
  assert.equal(isDirty(a, b), false);
  b.kids[0].name = "X";
  assert.equal(isDirty(a, b), true);
});
