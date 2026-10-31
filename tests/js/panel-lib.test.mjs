import test from "node:test";
import assert from "node:assert/strict";

const {
  slugify, uniqueId, setPath, addKid, removeKid, addResource, removeResource,
  addSegment, removeSegment, setMode, toggleOwner, toggleProfile, toggleListValue,
  profileGeometry, isDirty,
} = await import("../../custom_components/parental_control/www/panel-lib.js");

const draft = () => ({
  version: 1,
  default_leisure: ["youtube", "roblox"],
  calendar_map: {},
  notify: [],
  kids: [
    {
      id: "gabin", name: "Gabin", emoji: null, color: null, calendar: null,
      leisure_add: [], leisure_remove: [], resource_modes: { switch: "sur_demande" },
      profiles: {
        ecole: { segments: [{ start: "00:00", type: "bloque" }, { start: "16:00", type: "libre" }] },
        fin_de_semaine: { quota_minutes: 120, segments: [{ start: "00:00", type: "quota" }] },
      },
    },
  ],
  resources: [
    { id: "tv", name: "Télé", kind: "media_player", owners: ["gabin"], entity_id: "media_player.tv", quota_minutes: {} },
    { id: "switch", name: "Switch", kind: "nintendo", owners: ["gabin"], device_id: "d", limit_entity: "number.l",
      remaining_entity: "sensor.r", used_entity: "sensor.u", quota_minutes: {} },
  ],
});

test("slugify", () => {
  assert.equal(slugify("Maël"), "mael");
  assert.equal(slugify("  iPad des enfants! "), "ipad_des_enfants");
  assert.equal(slugify("Télé (AdGuard)"), "tele_adguard");
  assert.equal(slugify("!!!"), "");
});

test("uniqueId", () => {
  assert.equal(uniqueId("leo", ["gabin"]), "leo");
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
});

test("addKid copies the first kid's profiles and gets a unique id", () => {
  const d = draft();
  const kid = addKid(d, "Léo");
  assert.equal(kid.id, "leo");
  assert.equal(d.kids.length, 2);
  assert.deepEqual(kid.profiles, d.kids[0].profiles);
  assert.notEqual(kid.profiles, d.kids[0].profiles); // copie, pas la même référence
  const empty = { ...draft(), kids: [] };
  const first = addKid(empty, "Gabin");
  assert.deepEqual(Object.keys(first.profiles).sort(), ["ecole", "fin_de_semaine"]);
  assert.deepEqual(first.profiles.ecole.segments, [{ start: "00:00", type: "bloque" }]);
});

test("removeKid also removes it from owners", () => {
  const d = draft();
  removeKid(d, 0);
  assert.equal(d.kids.length, 0);
  assert.deepEqual(d.resources[0].owners, []);
});

test("addResource / removeResource keep modes consistent", () => {
  const d = draft();
  const r = addResource(d, "adguard_services", "iPad");
  assert.equal(r.id, "ipad");
  assert.equal(r.kind, "adguard_services");
  assert.equal(r.device_id, "");
  assert.deepEqual(r.owners, []);
  const n = addResource(d, "nintendo", "Switch");
  assert.equal(n.id, "switch_2");
  assert.deepEqual([n.device_id, n.limit_entity, n.remaining_entity, n.used_entity], ["", "", "", ""]);
  removeResource(d, 1); // la Switch d'origine
  assert.equal("switch" in d.kids[0].resource_modes, false);
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
  assert.deepEqual(kid.resource_modes, { tv: "bloque" });
});

test("toggleOwner and toggleListValue", () => {
  const r = draft().resources[0];
  toggleOwner(r, "gabin");
  assert.deepEqual(r.owners, []);
  toggleOwner(r, "leo");
  assert.deepEqual(r.owners, ["leo"]);
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
