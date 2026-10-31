// Tests de la logique partagée des cartes (lib.js), sans DOM.
import test from "node:test";
import assert from "node:assert/strict";

// Fuseau fixé avant le chargement : les heures affichées sont locales.
process.env.TZ = "America/Toronto";
const {
  fmtDuration,
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
  quotaBar,
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
  assert.deepEqual(quotaBar({ used: 45, remaining: null }), { pct: 100, text: "0h 45m / 0h 45m", over: true });
  assert.deepEqual(quotaBar({ used: null, remaining: 60 }), { pct: 0, text: "0h 00m / 1h 00m", over: false });
  assert.deepEqual(quotaBar({ used: 0, remaining: 0 }), { pct: 0, text: "0h 00m / 0h 00m", over: false });
});
