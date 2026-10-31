// Tests du mécanisme de confirmation en deux appuis et des pilules (style.js), sans DOM.
import test from "node:test";
import assert from "node:assert/strict";

const { ConfirmState, CONFIRM_MS, pill } = await import("../../custom_components/parental_control/www/style.js");

test("ConfirmState arms then runs, and disarms after CONFIRM_MS", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let changes = 0;
  const c = new ConfirmState(() => changes++);
  assert.equal(c.press("stop"), false); // 1er appui : arme
  assert.equal(c.armed, "stop");
  assert.equal(c.press("cancel:x"), false); // autre pilule : réarme sur celle-ci
  assert.equal(c.armed, "cancel:x");
  assert.equal(c.press("cancel:x"), true); // 2e appui : exécute
  assert.equal(c.armed, null);
  c.press("stop");
  t.mock.timers.tick(CONFIRM_MS);
  assert.equal(c.armed, null);
  assert.equal(c.press("stop"), false);
  c.clear();
  assert.equal(c.armed, null);
  assert.ok(changes >= 5);
});

test("pill escapes label and shows armed state", () => {
  const html = pill({ action: "a", icon: "mdi:power", label: "<i>x</i>", cls: "rouge", confirm: true });
  assert.match(html, /&lt;i&gt;x&lt;\/i&gt;/);
  assert.match(html, /data-confirm/);
  assert.match(html, /mdi:power/);
  const armed = pill({ action: "a", icon: "mdi:power", label: "Arrêter", armed: true, lock: true });
  assert.match(armed, /Confirmer \?/);
  assert.match(armed, /mdi:check/);
  assert.match(armed, /class="pill[^"]*\barmed\b/);
  assert.match(pill({ action: "a", icon: "mdi:plus", label: "Autoriser…", lock: true }), /mdi:lock/);
  assert.match(pill({ action: "a", icon: "mdi:plus", label: "x", disabled: true }), / disabled/);
  assert.match(pill({ action: "a", icon: "mdi:check", label: "x", trailing: "mdi:close" }), /mdi:close/);
  assert.doesNotMatch(pill({ action: "a", icon: "mdi:check", label: "x", trailing: "mdi:close", armed: true }), /mdi:close/);
});
