// Tests de la logique partagée des cartes (lib.js), sans DOM.
import test from "node:test";
import assert from "node:assert/strict";

// Fuseau fixé avant le chargement : les heures affichées sont locales.
process.env.TZ = "America/Toronto";
const {
  fmtDuration,
  shouldSubscribe,
  exceptionsForResource,
  exceptionsForKid,
  formatPill,
  resourceView,
  timelineGeometry,
  needsCode,
  serviceLabel,
  esc,
  reasonLine,
  stateBadge,
  bonusLabel,
  simulationBadge,
  quotaBar,
  keypadInput,
  dayTypeLabel,
  segmentClass,
  statusClass,
  nextStepLabel,
  exceptionSpans,
  bonusMinutes,
  switchGauge,
  canRequest,
  findRequest,
  requestsFor,
  requestLine,
  ownerChoices,
  requestRemaining,
  requestOutcome,
  requestsScreen,
} = await import("../../custom_components/parental_control/www/lib.js");

const NOW = new Date("2026-10-30T15:00:00-04:00");

const state = (exceptions = []) => ({
  kids: { gabin: { name: "Gabin" }, lea: { name: "Léa" } },
  resources: {
    tv: { name: "TV", kind: "media_player", owners: ["gabin"], open: false, reason: "Bloqué", until: null,
      used_minutes: 10, remaining_minutes: 20, leisure: ["tv"] },
    net: { name: "Internet", kind: "adguard_services", owners: ["gabin"], open: true, reason: "Ok", until: "2026-10-30T18:00:00-04:00",
      used_minutes: null, remaining_minutes: null, leisure: [] },
    switch: { name: "Switch", kind: "nintendo", owners: ["lea"], open: true, reason: "", until: null,
      used_minutes: 5, remaining_minutes: 55, leisure: [], used_entity: "sensor.u", remaining_entity: "sensor.r" },
  },
  paused: false,
  exceptions,
  now: "2026-10-30T15:00:00-04:00",
});

const exc = (id, target, extra = {}) => ({
  id, open: true, until: null, ends_at: null,
  target: { resource_id: null, kid_id: null, service: null, ...target }, ...extra,
});

test("fmtDuration", () => {
  assert.equal(fmtDuration(65), "1h 05m");
  assert.equal(fmtDuration(0), "0h 00m");
  assert.equal(fmtDuration(-5), "0h 00m");
  assert.equal(fmtDuration(120), "2h 00m");
});

test("serviceLabel", () => {
  assert.equal(serviceLabel("disneyplus"), "Disney+");
  assert.equal(serviceLabel("youtube"), "YouTube");
  assert.equal(serviceLabel("minecraft"), "Minecraft");
});

test("needsCode", () => {
  const admin = { user: { is_admin: true } };
  const user = { user: { is_admin: false } };
  for (const a of ["open", "bonus", "stop", "cancel"]) assert.equal(needsCode(admin, a), false);
  assert.equal(needsCode(user, "open"), true);
  assert.equal(needsCode(user, "bonus"), true);
  assert.equal(needsCode(user, "stop"), false);
  assert.equal(needsCode(user, "cancel"), false);
});

test("resourceView handles empty state", () => {
  for (const s of [null, undefined, {}, { kids: {}, resources: {}, paused: false, exceptions: [] }]) {
    assert.equal(resourceView(s, "tv").status, "unavailable");
  }
});

test("resourceView unknown resource", () => {
  const v = resourceView(state(), "disparue");
  assert.equal(v.status, "unknown");
});

test("resourceView exposes kinds and icon (mixed device)", () => {
  const st = state();
  st.resources.tv = { ...st.resources.tv, kinds: ["adguard_services", "media_player"], icon: "mdi:television" };
  const v = resourceView(st, "tv");
  assert.deepEqual(v.kinds, ["adguard_services", "media_player"]);
  assert.equal(v.icon, "mdi:television");
  assert.deepEqual(resourceView(state(), "tv").kinds, ["media_player"]);
  assert.equal(resourceView(state(), "tv").icon, null);
});

test("exceptionsForResource: service exception follows kinds, not kind", () => {
  const st = state([exc("e1", { resource_id: "tv", service: "youtube" })]);
  assert.equal(exceptionsForResource(st, "tv").length, 0);
  st.resources.tv.kinds = ["adguard_services", "media_player"];
  assert.equal(exceptionsForResource(st, "tv").length, 1);
});

test("resourceView ok", () => {
  const v = resourceView({ ...state(), paused: true }, "tv");
  assert.equal(v.status, "ok");
  assert.equal(v.name, "TV");
  assert.equal(v.kind, "media_player");
  assert.deepEqual(v.owners, ["gabin"]);
  assert.equal(v.open, false);
  assert.equal(v.reason, "Bloqué");
  assert.equal(v.used, 10);
  assert.equal(v.remaining, 20);
  assert.deepEqual(v.leisure, ["tv"]);
  assert.equal(v.nintendo, null);
  assert.equal(v.paused, true);
});

test("resourceView nintendo", () => {
  const v = resourceView(state(), "switch");
  assert.deepEqual(v.nintendo, { used_entity: "sensor.u", remaining_entity: "sensor.r" });
});

test("exceptionsForResource kid and global", () => {
  const s = state([
    exc("r", { resource_id: "tv" }),
    exc("k", { kid_id: "gabin" }),
    exc("k2", { kid_id: "lea" }),
    exc("g", {}),
    exc("r2", { resource_id: "net" }),
    exc("closed", { resource_id: "tv" }, { open: false }),
  ]);
  const tv = exceptionsForResource(s, "tv");
  assert.deepEqual(tv.map((e) => [e.id, e.scope]), [["r", "resource"], ["k", "kid"], ["g", "all"]]);
  assert.equal(tv[1].kid, "Gabin");
  assert.equal(tv[0].label, "Tout l'appareil");
  assert.deepEqual(exceptionsForResource(s, "switch").map((e) => e.id), ["k2", "g"]);
});

test("exceptionsForResource service only on adguard_services", () => {
  const s = state([exc("s", { kid_id: "gabin", service: "youtube" })]);
  assert.deepEqual(exceptionsForResource(s, "tv"), []);
  const net = exceptionsForResource(s, "net");
  assert.equal(net.length, 1);
  assert.equal(net[0].label, "YouTube");
  assert.equal(net[0].service, "youtube");
});

test("exceptionsForResource empty state", () => {
  assert.deepEqual(exceptionsForResource(null, "tv"), []);
});

test("exceptionsForKid", () => {
  const s = state([
    exc("k", { kid_id: "gabin" }, { ends_at: "2026-10-30T22:00:00-04:00" }),
    exc("r", { resource_id: "tv" }),
    exc("r-lea", { resource_id: "switch" }),
    exc("g", {}),
    exc("other", { kid_id: "lea" }),
    exc("closed", { kid_id: "gabin" }, { open: false }),
  ]);
  const list = exceptionsForKid(s, "gabin");
  assert.deepEqual(list.map((e) => [e.id, e.scope]), [["k", "kid"], ["r", "resource"], ["g", "all"]]);
  assert.equal(list[0].endsAt, "2026-10-30T22:00:00-04:00");
  assert.equal(list[1].endsAt, null);
  assert.deepEqual(exceptionsForKid(null, "gabin"), []);
});

test("formatPill with until", () => {
  const e = { label: "YouTube", scope: "resource", until: "2026-10-30T15:41:10-04:00", endsAt: null };
  assert.equal(formatPill(e, NOW), "YouTube · 42 min");
  const long = { ...e, until: "2026-10-30T16:15:00-04:00" };
  assert.equal(formatPill(long, NOW), "YouTube · 1 h 15");
});

test("formatPill without until uses ends_at in local time", () => {
  const e = { label: "Tout l'appareil", scope: "resource", until: null, endsAt: "2026-10-30T22:45:00-04:00" };
  assert.equal(formatPill(e, NOW), "Tout l'appareil · jusqu'à 22:45");
  // même instant exprimé en UTC : l'heure affichée reste locale
  assert.equal(formatPill({ ...e, endsAt: "2026-10-31T02:45:00Z" }, NOW), "Tout l'appareil · jusqu'à 22:45");
});

test("formatPill open ended and scopes", () => {
  const e = { label: "Tout l'appareil", scope: "resource", until: null, endsAt: null };
  assert.equal(formatPill(e, NOW), "Tout l'appareil · jusqu'à nouvel ordre");
  assert.equal(formatPill({ ...e, scope: "kid", kid: "Gabin" }, NOW),
    "Tout l'appareil · jusqu'à nouvel ordre · Gabin · tous ses appareils");
  assert.equal(formatPill({ ...e, scope: "all" }, NOW),
    "Tout l'appareil · jusqu'à nouvel ordre · tout le monde");
});

test("timelineGeometry projects on local day", () => {
  const g = timelineGeometry([
    { start: "2026-10-30T06:00:00-04:00", end: "2026-10-30T12:00:00-04:00", type: "libre" },
  ], NOW);
  assert.equal(g.bars.length, 1);
  assert.equal(g.bars[0].left, 25);
  assert.equal(g.bars[0].width, 25);
  assert.equal(g.bars[0].type, "libre");
  assert.equal(g.nowPct, 62.5);
});

test("timelineGeometry clamps to day", () => {
  const g = timelineGeometry([
    { start: "2026-10-29T20:00:00-04:00", end: "2026-10-30T06:00:00-04:00", type: "bloque" },
    { start: "2026-10-30T22:00:00-04:00", end: "2026-10-31T08:00:00-04:00", type: "bloque" },
    { start: "2026-10-28T00:00:00-04:00", end: "2026-10-29T00:00:00-04:00", type: "libre" },
  ], NOW);
  assert.deepEqual(g.bars, [
    { left: 0, width: 25, type: "bloque" },
    { left: (22 / 24) * 100, width: 100 - (22 / 24) * 100, type: "bloque" },
  ]);
  assert.deepEqual(timelineGeometry(null, NOW).bars, []);
});

test("esc", () => {
  assert.equal(esc(`<b a="1">'&'</b>`), "&lt;b a=&quot;1&quot;&gt;&#39;&amp;&#39;&lt;/b&gt;");
  assert.equal(esc(null), "");
  assert.equal(esc(3), "3");
});

test("reasonLine adds local until", () => {
  assert.equal(reasonLine({ reason: "Soirée", until: null }), "Soirée");
  assert.equal(reasonLine({ reason: "Exception", until: "2026-10-31T02:45:00Z" }), "Exception · jusqu'à 22:45");
  assert.equal(reasonLine({ reason: "", until: "2026-10-30T07:05:00-04:00" }), "jusqu'à 07:05");
  assert.equal(reasonLine({ reason: "", until: null }), "");
});

test("reasonLine does not repeat an hour already in the engine reason", () => {
  assert.equal(reasonLine({ reason: "Écrans autorisés jusqu'à 20:00", until: "2026-10-31T20:00:00-04:00", open: true }),
    "Écrans autorisés jusqu'à 20:00");
});

test("reasonLine shows resume time of a closed resource", () => {
  assert.equal(reasonLine({ reason: "Bloqué", until: null, open: false, resumesAt: "2026-10-31T08:00:00-04:00" }),
    "Bloqué · reprise 08:00");
  // ouverte : pas de « reprise »
  assert.equal(reasonLine({ reason: "Ok", until: null, open: true, resumesAt: "2026-10-31T08:00:00-04:00" }), "Ok");
  // `until` connu : il l'emporte
  assert.equal(reasonLine({ reason: "Fermée", until: "2026-10-30T21:00:00-04:00", open: false,
    resumesAt: "2026-10-31T08:00:00-04:00" }), "Fermée · jusqu'à 21:00");
});

test("resourceView resumesAt is the earliest end of the owners' blocked segments", () => {
  const s = state();
  s.kids.gabin = { ...s.kids.gabin, segment: "bloque", segment_end: "2026-10-31T08:00:00-04:00" };
  s.kids.lea = { ...s.kids.lea, segment: "bloque", segment_end: "2026-10-31T07:30:00-04:00" };
  s.resources.tv.owners = ["gabin", "lea"];
  assert.equal(resourceView(s, "tv").resumesAt, "2026-10-31T07:30:00-04:00");
  // un propriétaire hors segment « bloque » : la reprise n'est pas connue
  s.kids.lea.segment = "apres_devoirs";
  assert.equal(resourceView(s, "tv").resumesAt, null);
  // propriétaire inconnu : pas de reprise
  s.resources.tv.owners = ["inconnu"];
  assert.equal(resourceView(s, "tv").resumesAt, null);
  // Switch (sur demande) : jamais de reprise
  s.resources.switch.owners = ["gabin"];
  assert.equal(resourceView(s, "switch").resumesAt, null);
});

test("stateBadge", () => {
  assert.deepEqual(stateBadge({ paused: true, open: true }), { label: "Pause", cls: "warn" });
  assert.deepEqual(stateBadge({ paused: false, open: true }), { label: "Autorisé", cls: "ok" });
  assert.deepEqual(stateBadge({ paused: false, open: false }), { label: "Bloqué", cls: "bad" });
});

test("bonusLabel", () => {
  assert.equal(bonusLabel(15), "+15m");
  assert.equal(bonusLabel(30), "+30m");
  assert.equal(bonusLabel(60), "+1h");
  assert.equal(bonusLabel(120), "+2h");
  assert.equal(bonusLabel(90), "+1h30m");
});

test("quotaBar", () => {
  assert.equal(quotaBar({ used: null, remaining: null }), null);
  assert.deepEqual(quotaBar({ used: 10, remaining: 20 }), { pct: (10 / 30) * 100, text: "0h 10m / 0h 30m", over: false });
  // sans temps restant, la ressource n'a pas de quota : pas de barre (télé à « 0h 00m / 0h 00m »)
  assert.equal(quotaBar({ used: 45, remaining: null }), null);
  assert.equal(quotaBar({ used: 0, remaining: null }), null);
  assert.deepEqual(quotaBar({ used: null, remaining: 60 }), { pct: 0, text: "0h 00m / 1h 00m", over: false });
  assert.deepEqual(quotaBar({ used: 0, remaining: 0 }), { pct: 0, text: "0h 00m / 0h 00m", over: false });
});

test("dayTypeLabel", () => {
  assert.equal(dayTypeLabel("ecole"), "Jour d'école");
  assert.equal(dayTypeLabel("fin_de_semaine"), "Fin de semaine");
  assert.equal(dayTypeLabel("conge_peda"), "Congé pédago");
  assert.equal(dayTypeLabel("vacances"), "Vacances");
  assert.equal(dayTypeLabel("autre"), "autre");
  assert.equal(dayTypeLabel(undefined), "");
});

test("segmentClass", () => {
  for (const t of ["libre", "apres_devoirs", "quota", "sur_demande", "bloque"]) assert.equal(segmentClass(t), t);
  assert.equal(segmentClass("inconnu"), "bloque");
});

test("statusClass", () => {
  assert.equal(statusClass("autorise"), "ok");
  assert.equal(statusClass("attente_devoirs"), "warn");
  assert.equal(statusClass("pause"), "warn");
  assert.equal(statusClass("bloque"), "bad");
  assert.equal(statusClass("quota_epuise"), "bad");
});

test("nextStepLabel", () => {
  assert.equal(nextStepLabel({ status: "bloque", segment_end: "2026-10-31T07:00:00-04:00" }), "reprise 07:00");
  assert.equal(nextStepLabel({ status: "autorise", segment_end: "2026-10-30T20:30:00-04:00" }), "jusqu'à 20:30");
  assert.equal(nextStepLabel({ status: "bloque", segment_end: null }), "");
  assert.equal(nextStepLabel(undefined), "");
});

test("exceptionSpans", () => {
  // Fin explicite : de 15:00 à 18:00 (62,5 % -> 75 % de la journée).
  const [a] = exceptionSpans([{ id: "e1", endsAt: "2026-10-30T18:00:00-04:00" }], NOW);
  assert.equal(a.id, "e1");
  assert.equal(a.left, 62.5);
  assert.equal(a.width, 12.5);
  // Sans fin : jusqu'à minuit.
  const [b] = exceptionSpans([{ id: "e2", endsAt: null }], NOW);
  assert.equal(b.width, 37.5);
  // Fin après minuit : bornée à la journée ; fin déjà passée : écartée.
  assert.equal(exceptionSpans([{ id: "e3", endsAt: "2026-10-31T03:00:00-04:00" }], NOW)[0].width, 37.5);
  assert.deepEqual(exceptionSpans([{ id: "e4", endsAt: "2026-10-30T14:00:00-04:00" }], NOW), []);
  assert.deepEqual(exceptionSpans(undefined, NOW), []);
});

test("bonusMinutes : défaut 15/30/60, config filtrée aux entiers > 0", () => {
  assert.deepEqual(bonusMinutes({}), [15, 30, 60]);
  assert.deepEqual(bonusMinutes({ bonus_minutes: [10, "20", 0, -5, 1.5, "x"] }), [10, 20]);
  assert.deepEqual(bonusMinutes({ bonus_minutes: [] }), [15, 30, 60]);
  assert.deepEqual(bonusMinutes({ bonus_minutes: "30" }), [15, 30, 60]);
});

test("switchGauge : accordé = utilisé + restant, jauge = restant / accordé", () => {
  const view = { nintendo: { used_entity: "sensor.u", remaining_entity: "sensor.r" } };
  const hass = (u, r) => ({ states: { "sensor.u": { state: u }, "sensor.r": { state: r } } });
  assert.deepEqual(switchGauge(hass("42", "18"), view), { used: 42, remaining: 18, granted: 60, pct: 30 });
  // Non numérique, indisponible ou entité absente : 0 ; rien d'accordé -> jauge vide.
  assert.deepEqual(switchGauge(hass("unavailable", "unknown"), view), { used: 0, remaining: 0, granted: 0, pct: 0 });
  assert.equal(switchGauge({ states: {} }, view).granted, 0);
  assert.equal(switchGauge(hass("0", "30.5"), view).pct, 100);
});

test("shouldSubscribe : pas de rafale après un échec, nouvelle connexion réessaie", () => {
  const a = {}, b = {};
  assert.equal(shouldSubscribe(undefined, null, null), false);
  assert.equal(shouldSubscribe(a, null, null), true);
  assert.equal(shouldSubscribe(a, a, null), false); // déjà souscrite
  assert.equal(shouldSubscribe(a, null, a), false); // échec sur cette connexion : le tick réessaiera
  assert.equal(shouldSubscribe(b, null, a), true); // autre connexion
});

test("keypadInput: digits up to 8, backspace, clear", () => {
  assert.equal(keypadInput("", "1"), "1");
  assert.equal(keypadInput("123", "4"), "1234");
  assert.equal(keypadInput("12345678", "9"), "12345678"); // 8 chiffres au plus (code de 4 à 8)
  assert.equal(keypadInput("123", "back"), "12");
  assert.equal(keypadInput("", "back"), "");
  assert.equal(keypadInput("123", "clear"), "");
  assert.equal(keypadInput("12", "x"), "12"); // touche inconnue : rien
});

test("simulationBadge : pastille seulement en simulation", () => {
  assert.equal(simulationBadge({ simulation: true }), '<span class="sim">SIMULATION</span>');
  assert.equal(simulationBadge({ simulation: false }), "");
  assert.equal(simulationBadge({}), "");
  assert.equal(simulationBadge(null), "");
  assert.equal(simulationBadge(undefined), "");
});

test("resourceView exposes on-demand services", () => {
  const s = { resources: { ipad: { name: "iPad", kind: "adguard_services", leisure: ["roblox", "youtube"], on_demand: ["youtube"] } } };
  assert.deepEqual(resourceView(s, "ipad").onDemand, ["youtube"]);
  assert.deepEqual(resourceView({ resources: { ipad: { name: "iPad" } } }, "ipad").onDemand, []);
});

test("serviceToggles: on-demand services only, state from blocked_services, own exceptions", async () => {
  const { serviceToggles } = await import("../../custom_components/parental_control/www/lib.js");
  const state = {
    resources: {
      tv: { kinds: ["adguard_services", "media_player"], owners: ["leo"], on_demand: ["youtube", "netflix", "tiktok"], leisure: ["roblox"], blocked_services: ["youtube", "tiktok", "roblox"] },
      ps: { kinds: ["media_player"], leisure: ["netflix"] },
    },
    exceptions: [
      { id: "a", target: { resource_id: "tv", service: "netflix" }, open: false },
      { id: "b", target: { kid_id: "leo", service: "netflix" }, open: true },
      { id: "c", target: { resource_id: "tv", service: null }, open: true },
    ],
  };
  const t = serviceToggles(state, "tv");
  // Loisirs (roblox) absents ; netflix ouvert par l'exception d'enfant b (Léo propriétaire).
  assert.deepEqual(t.map((x) => [x.service, x.open, x.exceptions, x.openedElsewhere]), [
    ["youtube", false, [], false],
    ["netflix", true, ["a"], true],
    ["tiktok", false, [], false],
  ]);
  assert.equal(t[0].label, "YouTube");
  // Liste de la carte : filtre et ordre, services inconnus de l'appareil ignorés.
  assert.deepEqual(serviceToggles(state, "tv", ["tiktok", "roblox", "youtube"]).map((x) => x.service), ["tiktok", "youtube"]);
  assert.deepEqual(serviceToggles(state, "ps"), []); // pas d'AdGuard
  assert.deepEqual(serviceToggles(state, "inconnu"), []);
});

test("kid card: services over the kid's AdGuard devices, its exceptions, homework and timer", async () => {
  const { kidServiceToggles, kidExceptions, kidView, needsCode } = await import("../../custom_components/parental_control/www/lib.js");
  const state = {
    kids: {
      mael: { name: "Maël", segment: "apres_devoirs", status: "attente_devoirs", remaining_minutes: null, timer_end: null },
      leo: { name: "Léo", segment: "quota", status: "attente_minuteur", remaining_minutes: 40, timer_end: null },
    },
    resources: {
      tv: { name: "Télé", owners: ["mael", "leo"], kinds: ["adguard_services", "media_player"], on_demand: ["youtube"], blocked_services: [] },
      ipad: { name: "iPad", owners: ["mael"], kinds: ["adguard_services"], on_demand: ["youtube", "tiktok"], blocked_services: ["youtube", "tiktok"] },
      ps: { name: "PS5", owners: ["mael"], kinds: ["media_player"], on_demand: ["netflix"] },
    },
    exceptions: [
      { id: "a", target: { resource_id: "tv", kid_id: null, service: "youtube" }, open: true, until: null },
      { id: "b", target: { resource_id: null, kid_id: "mael", service: "tiktok" }, open: false, until: null },
      { id: "c", target: { resource_id: null, kid_id: "leo", service: "youtube" }, open: true, until: null },
      { id: "d", target: { resource_id: null, kid_id: null, service: "tiktok" }, open: true, until: null },
      { id: "e", target: { resource_id: null, kid_id: "mael", service: null }, open: true, until: null },
    ],
  };
  // YouTube bloqué sur l'iPad : pas débloqué pour Maël ; PS5 sans AdGuard ignorée.
  assert.deepEqual(kidServiceToggles(state, "mael").map((t) => [t.service, t.open, t.exceptions, t.openedElsewhere]), [
    ["youtube", false, ["a"], false],
    ["tiktok", false, ["b"], true],
  ]);
  assert.deepEqual(kidServiceToggles(state, "mael", ["tiktok", "netflix"]).map((t) => t.service), ["tiktok"]);
  assert.deepEqual(kidServiceToggles(state, "inconnu"), []);

  assert.deepEqual(kidExceptions(state, "mael").map((e) => [e.id, e.label, e.scope]), [
    ["a", "YouTube · Télé", "resource"],
    ["d", "TikTok", "all"],
    ["e", "Tous ses appareils", "resource"],
  ]);

  assert.equal(kidView(state, "mael").homework, "todo");
  assert.equal(kidView(state, "mael").timer, null);
  assert.deepEqual(kidView(state, "leo").timer, { running: false, canStart: true });
  assert.equal(kidView({ ...state, kids: { ...state.kids, mael: { ...state.kids.mael, status: "autorise" } } }, "mael").homework, "done");
  assert.equal(kidView(state, "x").status, "unknown");
  assert.equal(kidView({ kids: {} }, "x").status, "unavailable");

  const user = { user: { is_admin: false } };
  assert.equal(needsCode(user, "homework"), true);
  assert.equal(needsCode(user, "timer"), true);
});

const req = (id, extra = {}) => ({
  id, kind: "open", kid_id: "gabin", resource_id: null, service: null, proposed: 30,
  status: "pending", granted: null, reason: null, expires: "2026-10-30T15:10:00-04:00", ...extra,
});

test("canRequest : faux pour un admin ou sans requests_enabled, vrai sinon", () => {
  const user = { user: { is_admin: false } };
  assert.equal(canRequest(user, { requests_enabled: true }), true);
  assert.equal(canRequest(user, { requests_enabled: false }), false);
  assert.equal(canRequest(user, {}), false);
  assert.equal(canRequest(user, undefined), false);
  assert.equal(canRequest({ user: { is_admin: true } }, { requests_enabled: true }), false);
});

test("findRequest distingue service et ressource, et renvoie la plus récente", () => {
  const s = { requests: [
    req("a", { service: "youtube", expires: "2026-10-30T15:05:00-04:00" }),
    req("b", { service: "youtube", expires: "2026-10-30T15:09:00-04:00" }),
    req("c", { service: "tiktok" }),
    req("d", { resource_id: "tv" }),
    req("e", { kind: "bonus" }),
  ] };
  assert.equal(findRequest(s, { kind: "open", kid_id: "gabin", service: "youtube" }).id, "b");
  assert.equal(findRequest(s, { kind: "open", kid_id: "gabin", service: "tiktok" }).id, "c");
  assert.equal(findRequest(s, { kind: "open", kid_id: "gabin", resource_id: "tv" }).id, "d");
  assert.equal(findRequest(s, { kind: "open", kid_id: "gabin" }), null);
  assert.equal(findRequest(s, { kind: "bonus", kid_id: "gabin" }).id, "e");
  assert.equal(findRequest(s, { kind: "open", kid_id: "lea", service: "youtube" }), null);
  assert.equal(findRequest({}, { kind: "open", kid_id: "gabin" }), null);
});

test("requestLine : un libellé par statut", () => {
  assert.equal(requestLine(req("a")), "Demande envoyée · en attente");
  assert.equal(requestLine(req("a", { status: "accepted", granted: 30 })), "Accepté : 30 min");
  assert.equal(requestLine(req("a", { status: "accepted", granted: 60 })), "Accepté : 1 h");
  assert.equal(requestLine(req("a", { status: "accepted", granted: 90 })), "Accepté : 1 h 30");
  assert.equal(requestLine(req("a", { status: "accepted", granted: 65 })), "Accepté : 1 h 05");
  assert.equal(requestLine(req("a", { status: "accepted", granted: null })), "Accepté : jusqu'au prochain changement");
  assert.equal(requestLine(req("a", { kind: "homework", status: "accepted" })), "Accepté");
  assert.equal(requestLine(req("a", { status: "refused" })), "Refusé");
  assert.equal(requestLine(req("a", { status: "expired" })), "Pas de réponse");
  assert.equal(requestLine(req("a", { status: "failed", reason: "Déjà ouvert" })), "Impossible : Déjà ouvert");
});

test("requestsFor filtre par enfant ou par ressource", () => {
  const s = { requests: [req("a"), req("b", { kid_id: "lea" }), req("c", { resource_id: "tv", kid_id: "lea" })] };
  assert.deepEqual(requestsFor(s, { kid_id: "gabin" }).map((r) => r.id), ["a"]);
  assert.deepEqual(requestsFor(s, { kid_id: "lea" }).map((r) => r.id), ["b", "c"]);
  assert.deepEqual(requestsFor(s, { resource_id: "tv" }).map((r) => r.id), ["c"]);
  assert.deepEqual(requestsFor({}, { kid_id: "gabin" }), []);
});

test("ownerChoices : nom de l'enfant, à défaut son id", () => {
  assert.deepEqual(ownerChoices({ kids: { gabin: { name: "Gabin" } } }, ["gabin", "zoe"]),
    [{ value: "gabin", label: "Gabin" }, { value: "zoe", label: "zoe" }]);
  assert.deepEqual(ownerChoices({}, undefined), []);
});

test("requestRemaining : minutes avant l'expiration, arrondies au-dessus", () => {
  assert.equal(requestRemaining("2026-10-30T15:12:00-04:00", NOW), "Expire dans 12 min");
  assert.equal(requestRemaining("2026-10-30T15:00:20-04:00", NOW), "Expire dans 1 min");
  assert.equal(requestRemaining("2026-10-30T15:00:00-04:00", NOW), "Expire maintenant");
  assert.equal(requestRemaining(null, NOW), "Expire maintenant");
});

test("requestOutcome : qui a répondu et ce qui a été accordé", () => {
  const r = (extra) => ({ kind: "open", answered_by: "Manou", ...extra });
  assert.equal(requestOutcome(r({ status: "accepted", granted: 30 })), "Acceptée par Manou : 30 min");
  assert.equal(requestOutcome(r({ status: "accepted", granted: null })), "Acceptée par Manou : jusqu'au prochain changement");
  assert.equal(requestOutcome(r({ kind: "homework", status: "accepted" })), "Acceptée par Manou");
  assert.equal(requestOutcome(r({ status: "refused" })), "Refusée par Manou");
  assert.equal(requestOutcome(r({ status: "expired", answered_by: null })), "Expirée sans réponse");
  assert.equal(requestOutcome(r({ status: "failed", reason: "Déjà ouvert" })), "Acceptée par Manou, mais impossible : Déjà ouvert");
  assert.equal(requestOutcome(r({ status: "refused", answered_by: null })), "Refusée");
});

test("requestsScreen : en attente d'abord (plus ancienne en tête), puis récentes", () => {
  const r = (id, status, created) => ({ id, status, created: `2026-10-30T${created}:00-04:00` });
  const view = requestsScreen([
    r("a", "pending", "14:50"), r("b", "accepted", "14:40"), r("c", "pending", "14:45"), r("d", "expired", "14:55"),
  ]);
  assert.deepEqual(view.pending.map((x) => x.id), ["c", "a"]);
  assert.deepEqual(view.recent.map((x) => x.id), ["d", "b"]);
  assert.deepEqual(requestsScreen(undefined), { pending: [], recent: [] });
});
