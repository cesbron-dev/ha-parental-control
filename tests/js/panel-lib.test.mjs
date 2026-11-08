import test from "node:test";
import assert from "node:assert/strict";

const {
  slugify, uniqueId, setPath, addKid, removeKid, addResource, removeResource,
  addDevice, removeDevice, addIntegration, removeIntegration, integrationKindsAllowed, moveDevice, moveTargets,
  addSegment, removeSegment, setMode, toggleOwner, toggleProfile, toggleListValue,
  profileGeometry, isDirty, emptyConfig, hasDevices,
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
  assert.deepEqual(integrationKindsAllowed(addResource(d, "Vide")), ["media_player", "switch", "adguard_services", "nintendo"]);
  assert.deepEqual(integrationKindsAllowed(d.resources[0]), ["media_player", "switch", "adguard_services"]);
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

test("moveTargets respecte la règle Nintendo seule dans sa ressource", () => {
  const d = draft();
  assert.deepEqual(moveTargets(d, 1, 0), [0]); // AdGuard : la Télé, pas la Switch
  assert.deepEqual(moveTargets(d, 2, 0), []); // Nintendo : aucune ressource vide
  const vide = addResource(d, "Vide");
  assert.deepEqual(moveTargets(d, 2, 0), [3]);
  assert.deepEqual(moveTargets(d, 0, 0), [1, 3]);
  addIntegration(vide.devices[0], "media_player");
  assert.deepEqual(moveTargets(d, 2, 0), []);
  assert.deepEqual(moveTargets(d, 0, 5), []); // appareil absent
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

test("emptyConfig : brouillon v2 d'une nouvelle installation, prêt à recevoir un appareil", () => {
  const cfg = emptyConfig();
  assert.deepEqual(cfg, { version: 2, default_leisure: [], default_on_demand: [], calendar_map: {}, notify: [], request_notify: [], request_notify_owners: {}, kids: [], resources: [] });
  const res = addResource(cfg, "Télé");
  addIntegration(res.devices[0], "media_player");
  assert.equal(cfg.version, 2);
  assert.deepEqual(cfg.resources, [{ id: "tele", name: "Télé", owners: [], quota_minutes: {},
    devices: [{ name: "Télé", integrations: [{ kind: "media_player", entity_id: "" }] }] }]);
  assert.notEqual(emptyConfig(), emptyConfig()); // une copie neuve à chaque appel
});

test("hasDevices : une ressource collée en JSON sans arbre", () => {
  assert.equal(hasDevices(draft().resources[0]), true);
  assert.equal(hasDevices({ id: "tv", kind: "media_player", entity_id: "media_player.tv" }), false);
  assert.equal(hasDevices({ id: "tv", devices: null }), false);
});

test("entityChoices lists one domain with device name and integration", async () => {
  const { entityChoices } = await import("../../custom_components/parental_control/www/panel-lib.js");
  const hass = {
    states: {
      "media_player.google_tv_salon": { attributes: { friendly_name: "Google TV salon" } },
      "media_player.chromecast_salon": { attributes: { friendly_name: "Chromecast salon" } },
      "media_player.inconnu": { attributes: {} },
      "switch.prise_pc": { attributes: { friendly_name: "Prise PC" } },
      "switch.controle_parental_pause": { attributes: { friendly_name: "Pause générale" } },
      "switch.chromecast_filtrage": { attributes: { friendly_name: "Chromecast Filtrage" } },
    },
    entities: {
      "media_player.google_tv_salon": { entity_id: "media_player.google_tv_salon", platform: "androidtv_remote", device_id: "d1" },
      "media_player.chromecast_salon": { entity_id: "media_player.chromecast_salon", platform: "cast" },
      "switch.prise_pc": { entity_id: "switch.prise_pc", platform: "un_truc" },
      "switch.controle_parental_pause": { entity_id: "switch.controle_parental_pause", platform: "parental_control" },
      "switch.chromecast_filtrage": { entity_id: "switch.chromecast_filtrage", platform: "adguard_clients", entity_category: "config" },
    },
    devices: { d1: { name: "Chambre principale", name_by_user: "Google TV salon" } },
  };
  assert.deepEqual(entityChoices(hass, "media_player"), [
    { value: "media_player.chromecast_salon", label: "Chromecast salon — Google Cast" },
    { value: "media_player.google_tv_salon", label: "Google TV salon — Android TV Remote" },
    { value: "media_player.inconnu", label: "media_player.inconnu" },
  ]);
  assert.deepEqual(entityChoices(hass, "switch"), [{ value: "switch.prise_pc", label: "Prise PC — un_truc" }]);
  assert.deepEqual(entityChoices(null, "switch"), []);
});

test("addIntegration builds a switch integration", async () => {
  const { addIntegration } = await import("../../custom_components/parental_control/www/panel-lib.js");
  const dev = { name: "Prise", integrations: [] };
  addIntegration(dev, "switch");
  assert.deepEqual(dev.integrations, [{ kind: "switch", entity_id: "" }]);
});

// --- Refonte A : frise à poignées, services, résumés ---

const lib = await import("../../custom_components/parental_control/www/panel-lib.js");
const segs = () => [{ start: "00:00", type: "bloque" }, { start: "16:15", type: "apres_devoirs" }, { start: "19:00", type: "bloque" }];

test("fractionToMinutes : position sur la frise -> minutes, au pas de 5 min", () => {
  assert.equal(lib.fractionToMinutes(0), 0);
  assert.equal(lib.fractionToMinutes(0.5), 720);
  assert.equal(lib.fractionToMinutes(1), 1440);
  assert.equal(lib.fractionToMinutes(16.2 / 24), 970); // 16:12 -> 16:10
  assert.equal(lib.fractionToMinutes(16.23 / 24), 975); // 16:13,8 -> 16:15
  assert.equal(lib.fractionToMinutes(-0.2), 0);
  assert.equal(lib.fractionToMinutes(1.4), 1440);
  assert.equal(lib.fractionToMinutes(Number.NaN), 0);
});

test("segmentBounds : bornes d'une limite entre ses voisines, au pas de 5 min", () => {
  assert.deepEqual(lib.segmentBounds(segs(), 1), { min: 5, max: 1135 }); // 00:05 .. 18:55
  assert.deepEqual(lib.segmentBounds(segs(), 2), { min: 980, max: 1435 }); // 16:20 .. 23:55
  assert.equal(lib.segmentBounds(segs(), 0), null); // 00:00 fixe
  assert.equal(lib.segmentBounds(segs(), 3), null);
  // Voisines hors grille : bornes arrondies vers l'intérieur.
  const odd = [{ start: "00:00", type: "bloque" }, { start: "10:02", type: "libre" }, { start: "10:09", type: "bloque" }, { start: "10:13", type: "libre" }];
  assert.deepEqual(lib.segmentBounds(odd, 2), { min: 605, max: 610 });
  // Pas de place sur la grille.
  const tight = [{ start: "00:00", type: "bloque" }, { start: "10:01", type: "libre" }, { start: "10:03", type: "bloque" }, { start: "10:04", type: "libre" }];
  assert.equal(lib.segmentBounds(tight, 2), null);
});

test("setSegmentStart : arrondi au pas de 5 min et borné par les voisines", () => {
  const s = segs();
  assert.equal(lib.setSegmentStart(s, 1, 1000), "16:40");
  assert.equal(s[1].start, "16:40");
  assert.equal(lib.setSegmentStart(s, 1, 1002), "16:40");
  assert.equal(lib.setSegmentStart(s, 1, 1003), "16:45");
  assert.equal(lib.setSegmentStart(s, 1, 2000), "18:55"); // pas au-delà de la suivante
  assert.equal(lib.setSegmentStart(s, 1, -10), "00:05"); // pas avant la précédente
  assert.equal(lib.setSegmentStart(s, 2, 1440), "23:55");
  assert.equal(lib.setSegmentStart(s, 0, 300), null); // première limite fixe
  assert.equal(s[0].start, "00:00");
});

test("timelineBlocks : plages de la frise avec heures de début et de fin", () => {
  assert.deepEqual(lib.timelineBlocks(segs()), [
    { index: 0, left: 0, width: (975 / 1440) * 100, type: "bloque", start: "00:00", end: "16:15" },
    { index: 1, left: (975 / 1440) * 100, width: (165 / 1440) * 100, type: "apres_devoirs", start: "16:15", end: "19:00" },
    { index: 2, left: (1140 / 1440) * 100, width: (300 / 1440) * 100, type: "bloque", start: "19:00", end: "24:00" },
  ]);
  assert.deepEqual(lib.timelineBlocks([{ start: "00:00", type: "libre" }, { start: "zz", type: "bloque" }]).map((b) => [b.index, b.end]),
    [[0, "24:00"]]); // heure invalide ignorée, index d'origine conservé
});

const svcDraft = () => {
  const cfg = draft();
  cfg.default_leisure = ["youtube", "roblox"];
  cfg.default_on_demand = ["netflix"];
  Object.assign(cfg.kids[0], { leisure_add: ["fortnite"], leisure_remove: ["roblox"], on_demand_add: [], on_demand_remove: [] });
  return cfg;
};

test("serviceChips : pastilles communes (barrées si retirées) puis ajouts de l'enfant", () => {
  const cfg = svcDraft();
  assert.deepEqual(lib.serviceChips(cfg, cfg.kids[0], "leisure"), [
    { service: "youtube", common: true, removed: false },
    { service: "roblox", common: true, removed: true },
    { service: "fortnite", common: false, removed: false },
  ]);
  assert.deepEqual(lib.serviceChips(cfg, cfg.kids[0], "on_demand"), [{ service: "netflix", common: true, removed: false }]);
  // Brouillon ancien sans les clés « sur demande » : listes vides.
  const old = draft();
  delete old.kids[0].on_demand_add;
  assert.deepEqual(lib.serviceChips(old, old.kids[0], "on_demand"), []);
});

test("toggleKidService : retire/rétablit un service commun, retire un ajout propre", () => {
  const cfg = svcDraft();
  const kid = cfg.kids[0];
  lib.toggleKidService(cfg, kid, "leisure", "roblox");
  assert.deepEqual(kid.leisure_remove, []);
  lib.toggleKidService(cfg, kid, "leisure", "youtube");
  assert.deepEqual(kid.leisure_remove, ["youtube"]);
  lib.toggleKidService(cfg, kid, "leisure", "fortnite");
  assert.deepEqual(kid.leisure_add, []);
  const old = draft();
  delete old.kids[0].on_demand_remove;
  old.default_on_demand = ["netflix"];
  lib.toggleKidService(old, old.kids[0], "on_demand", "netflix");
  assert.deepEqual(old.kids[0].on_demand_remove, ["netflix"]);
});

test("addKidService : ajout propre, ou rétablit un service commun retiré", () => {
  const cfg = svcDraft();
  const kid = cfg.kids[0];
  assert.equal(lib.addKidService(cfg, kid, "on_demand", "  Twitch "), "twitch");
  assert.deepEqual(kid.on_demand_add, ["twitch"]);
  lib.addKidService(cfg, kid, "on_demand", "twitch"); // déjà là
  assert.deepEqual(kid.on_demand_add, ["twitch"]);
  lib.addKidService(cfg, kid, "leisure", "roblox"); // commun retiré : rétabli
  assert.deepEqual(kid.leisure_remove, []);
  assert.deepEqual(kid.leisure_add, ["fortnite"]);
  lib.addKidService(cfg, kid, "leisure", "youtube"); // déjà commun
  assert.deepEqual(kid.leisure_add, ["fortnite"]);
  assert.equal(lib.addKidService(cfg, kid, "leisure", "   "), null);
});

test("addCommonService / removeCommonService : un service n'est que dans une liste commune", () => {
  const cfg = svcDraft();
  assert.equal(lib.addCommonService(cfg, "on_demand", "YouTube"), "youtube");
  assert.deepEqual(cfg.default_on_demand, ["netflix", "youtube"]);
  assert.deepEqual(cfg.default_leisure, ["roblox"]);
  lib.addCommonService(cfg, "on_demand", "youtube"); // pas de doublon
  assert.deepEqual(cfg.default_on_demand, ["netflix", "youtube"]);
  lib.removeCommonService(cfg, "on_demand", "netflix");
  assert.deepEqual(cfg.default_on_demand, ["youtube"]);
  const old = draft();
  delete old.default_on_demand;
  lib.addCommonService(old, "on_demand", "tiktok");
  assert.deepEqual(old.default_on_demand, ["tiktok"]);
});

test("moveCommonService : passe d'une liste commune à l'autre avec les exceptions des enfants", () => {
  const cfg = svcDraft();
  const kid = cfg.kids[0];
  kid.on_demand_add = ["roblox"]; // redondant une fois roblox commun « sur demande »
  assert.equal(lib.moveCommonService(cfg, "roblox"), "on_demand");
  assert.deepEqual(cfg.default_leisure, ["youtube"]);
  assert.deepEqual(cfg.default_on_demand, ["netflix", "roblox"]);
  assert.deepEqual(kid.leisure_remove, []);
  assert.deepEqual(kid.on_demand_remove, ["roblox"]); // l'exception suit le service
  assert.deepEqual(kid.on_demand_add, []);
  assert.equal(lib.moveCommonService(cfg, "netflix"), "leisure");
  assert.deepEqual(cfg.default_leisure, ["youtube", "netflix"]);
  assert.equal(lib.moveCommonService(cfg, "inconnu"), null);
});

test("dayLabels : journées définies de l'enfant, en libellés courts", () => {
  const kid = draft().kids[0];
  assert.equal(lib.dayLabels(kid), "École · Fin de semaine");
  kid.profiles.vacances = { segments: [{ start: "00:00", type: "libre" }] };
  assert.equal(lib.dayLabels(kid), "École · Fin de semaine · Vacances");
  assert.equal(lib.dayLabels({ profiles: {} }), "Aucune journée");
});

test("resourceSummary : appareils physiques et intégrations, Nintendo à part", () => {
  const cfg = draft();
  assert.equal(lib.resourceSummary(cfg.resources[0]), "1 intégration");
  assert.equal(lib.resourceSummary(cfg.resources[2]), "Console Nintendo");
  const r = cfg.resources[0];
  lib.addDevice(r, "Google TV");
  lib.addIntegration(r.devices[1], "adguard_services");
  lib.addIntegration(r.devices[1], "switch");
  assert.equal(lib.resourceSummary(r), "2 appareils · 3 intégrations");
  assert.equal(lib.resourceSummary({ id: "x", devices: [{ name: "x", integrations: [] }] }), "Aucune intégration");
  assert.equal(lib.resourceSummary({ id: "tv", kind: "media_player" }), "Format ancien");
});

test("integrationSummary : ce qui est piloté, en une ligne", () => {
  const hass = {
    states: { "media_player.tv": { attributes: { friendly_name: "Tv salon" } }, "switch.prise": { attributes: {} } },
    entities: { "media_player.tv": { platform: "smartthings" }, "switch.prise": { platform: "shelly" } },
  };
  const registry = [{ id: "a", name: "tv" }, { id: "n", name: "Switch", name_by_user: "Switch papa" }];
  assert.deepEqual(lib.integrationSummary(hass, registry, { kind: "media_player", entity_id: "media_player.tv" }),
    { title: "Tv salon", detail: "SmartThings · media_player.tv", found: true });
  assert.deepEqual(lib.integrationSummary(hass, registry, { kind: "switch", entity_id: "switch.prise", turn_on_when_allowed: true }),
    { title: "switch.prise", detail: "Shelly · switch.prise · rallumée à l'autorisation", found: true });
  assert.deepEqual(lib.integrationSummary(hass, registry, { kind: "media_player", entity_id: "media_player.vieux" }),
    { title: "media_player.vieux", detail: "media_player.vieux", found: false });
  assert.deepEqual(lib.integrationSummary(hass, registry, { kind: "media_player", entity_id: "" }),
    { title: null, detail: "", found: false });
  assert.deepEqual(lib.integrationSummary(hass, registry, { kind: "adguard_services", device_id: "a" }),
    { title: "tv", detail: "AdGuard Home", found: true });
  assert.deepEqual(lib.integrationSummary(hass, registry, { kind: "nintendo", device_id: "n" }),
    { title: "Switch papa", detail: "Nintendo", found: true });
  assert.deepEqual(lib.integrationSummary(null, [], { kind: "adguard_services", device_id: "zz" }),
    { title: "zz", detail: "AdGuard Home", found: false });
});

test("safeColor : seules les couleurs #rrggbb passent dans un style", () => {
  assert.equal(lib.safeColor("#4D96FF"), "#4D96FF");
  assert.equal(lib.safeColor("red;background:url(x)"), null);
  assert.equal(lib.safeColor(null), null);
  assert.equal(lib.safeColor("#abc"), null);
});

test("addCommonService qui fait passer un service d'une liste à l'autre suit moveCommonService", () => {
  const cfg = svcDraft();
  const kid = cfg.kids[0];
  kid.on_demand_add = ["roblox"];
  assert.equal(lib.addCommonService(cfg, "on_demand", "Roblox"), "roblox");
  assert.deepEqual(cfg.default_leisure, ["youtube"]);
  assert.deepEqual(cfg.default_on_demand, ["netflix", "roblox"]);
  assert.deepEqual(kid.leisure_remove, []); // plus d'exemption périmée côté loisirs
  assert.deepEqual(kid.on_demand_remove, ["roblox"]);
  assert.deepEqual(kid.on_demand_add, []);
});

test("removeCommonService retire aussi les exemptions des enfants pour ce service", () => {
  const cfg = svcDraft();
  const kid = cfg.kids[0];
  kid.on_demand_remove = ["netflix"];
  lib.removeCommonService(cfg, "leisure", "roblox");
  assert.deepEqual(cfg.default_leisure, ["youtube"]);
  assert.deepEqual(kid.leisure_remove, []);
  lib.removeCommonService(cfg, "on_demand", "netflix");
  assert.deepEqual(kid.on_demand_remove, []);
  const old = draft(); // enfant sans clés « sur demande »
  delete old.kids[0].on_demand_remove;
  old.default_on_demand = ["x"];
  lib.removeCommonService(old, "on_demand", "x");
  assert.deepEqual(old.default_on_demand, []);
});

test("brouillon mêlant une ressource sans arbre : moveTargets, integrationKindsAllowed et moveDevice ne plantent pas", () => {
  const cfg = draft();
  cfg.resources.push({ id: "vieux", name: "Vieux", kind: "media_player", entity_id: "media_player.x", owners: [] });
  assert.deepEqual(moveTargets(cfg, 0, 0), [1]); // pas vers la Nintendo ni vers la ressource sans arbre
  assert.deepEqual(moveTargets(cfg, 3, 0), []);
  assert.deepEqual(integrationKindsAllowed(cfg.resources[3]), []);
  assert.equal(moveDevice(cfg, 0, 0, 3), null);
  assert.equal(cfg.resources[0].devices.length, 1);
});

test("isIconName : seules les icônes « jeu:nom » sont enregistrées", () => {
  assert.equal(lib.isIconName("mdi:television"), true);
  assert.equal(lib.isIconName("hass:power-socket-eu"), true);
  assert.equal(lib.isIconName("mdi:"), false);
  assert.equal(lib.isIconName("television"), false);
  assert.equal(lib.isIconName('mdi:tv" onload="x'), false);
  assert.equal(lib.isIconName("MDI:TV"), false);
  assert.equal(lib.isIconName(null), false);
});

test("AdGuard catalogue: readable names, unknown services and menu choices", () => {
  const catalog = { youtube: "YouTube", tiktok: "TikTok", discord: "Discord" };
  assert.deepEqual(lib.serviceLabel(catalog, "youtube"), { name: "YouTube", known: true });
  assert.deepEqual(lib.serviceLabel(catalog, "youtub"), { name: "youtub", known: false });
  // Sans catalogue (intégration absente), rien n'est signalé inconnu.
  assert.deepEqual(lib.serviceLabel({}, "youtub"), { name: "youtub", known: true });
  assert.deepEqual(lib.serviceOptions(catalog, ["tiktok"]), [
    { value: "discord", label: "Discord" },
    { value: "youtube", label: "YouTube" },
  ]);
  assert.deepEqual(lib.serviceOptions(null, []), []);
  const cfg = { default_leisure: ["tiktok"], default_on_demand: ["youtube"] };
  assert.deepEqual(lib.commonServices(cfg), ["tiktok", "youtube"]);
  assert.deepEqual(lib.commonServices({}), []);
});

test("Notification services: menu choices with mobile_app device names", () => {
  const services = ["mobile_app_iphone_de_julie", "mobile_app_ipad_de_zoe", "persistent_notification", "mobile_app_inconnu"];
  const devices = [
    { name: "iPhone de Julie", identifiers: [["mobile_app", "a"]] },
    { name: "iPad de Zoé", name_by_user: "iPad Zoé", identifiers: [["mobile_app", "b"]] },
    { name: "Télé", identifiers: [["samsungtv", "c"]] },
  ];
  assert.equal(lib.notifyLabel("notify.mobile_app_iphone_de_julie", devices), "iPhone de Julie");
  assert.equal(lib.notifyLabel("notify.persistent_notification", devices), "notify.persistent_notification");
  // Téléphones de l'application seulement, sans ceux déjà pris, triés par libellé.
  assert.deepEqual(lib.notifyOptions(services, devices, ["notify.mobile_app_iphone_de_julie"], true), [
    { value: "notify.mobile_app_ipad_de_zoe", label: "iPad Zoé" },
    { value: "notify.mobile_app_inconnu", label: "notify.mobile_app_inconnu" },
  ]);
  assert.deepEqual(lib.notifyOptions(services, devices, [], false).map((o) => o.value), [
    "notify.mobile_app_ipad_de_zoe", "notify.mobile_app_iphone_de_julie",
    "notify.mobile_app_inconnu", "notify.persistent_notification",
  ]);
});
