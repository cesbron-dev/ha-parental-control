// Tests de connection.js avec une fausse connexion Home Assistant.
import test from "node:test";
import assert from "node:assert/strict";
import { subscribeState, callAction } from "../../custom_components/parental_control/www/connection.js";

function fakeHass() {
  const subs = [];
  const calls = [];
  const hass = {
    calls,
    subs,
    connection: {
      subscribeMessage: async (cb, msg) => {
        const sub = { cb, msg, unsubscribed: 0 };
        subs.push(sub);
        return () => { sub.unsubscribed += 1; };
      },
    },
    callService: async (domain, service, data) => { calls.push([domain, service, data]); },
  };
  return hass;
}

test("subscribeState shares one subscription and replays last state", async () => {
  const hass = fakeHass();
  const a = [], b = [];
  const unA = await subscribeState(hass, (s) => a.push(s));
  assert.equal(hass.subs.length, 1);
  assert.deepEqual(hass.subs[0].msg, { type: "parental_control/state/subscribe" });
  hass.subs[0].cb({ n: 1 });
  const unB = await subscribeState(hass, (s) => b.push(s));
  assert.equal(hass.subs.length, 1);
  assert.deepEqual(b, [{ n: 1 }]);
  hass.subs[0].cb({ n: 2 });
  assert.deepEqual(a, [{ n: 1 }, { n: 2 }]);
  unA();
  assert.equal(hass.subs[0].unsubscribed, 0);
  unB();
  await new Promise((r) => setImmediate(r));
  assert.equal(hass.subs[0].unsubscribed, 1);
  // nouvelle souscription après le départ du dernier abonné
  await subscribeState(hass, () => {});
  assert.equal(hass.subs.length, 2);
});

test("callAction adds code only when given and never throws", async () => {
  const hass = fakeHass();
  assert.deepEqual(await callAction(hass, "exception", { a: 1 }), { ok: true });
  assert.deepEqual(await callAction(hass, "exception", { a: 1 }, "1234"), { ok: true });
  assert.deepEqual(hass.calls, [
    ["parental_control", "exception", { a: 1 }],
    ["parental_control", "exception", { a: 1, code: "1234" }],
  ]);
  hass.callService = async () => { throw new Error("Code invalide"); };
  assert.deepEqual(await callAction(hass, "exception", {}, "0"), { ok: false, error: "Code invalide" });
});

test("un callback qui lève n'empêche pas les autres de recevoir l'état", async () => {
  const hass = fakeHass();
  const errors = [];
  const origError = console.error;
  console.error = (e) => errors.push(e);
  try {
    const b = [], c = [];
    await subscribeState(hass, () => { throw new Error("carte cassée"); });
    await subscribeState(hass, (s) => b.push(s));
    hass.subs[0].cb({ n: 1 });
    assert.deepEqual(b, [{ n: 1 }]);
    // rejeu du dernier état à un nouvel abonné : le callback fautif ne bloque pas non plus
    await subscribeState(hass, () => { throw new Error("autre carte cassée"); });
    await subscribeState(hass, (s) => c.push(s));
    assert.deepEqual(c, [{ n: 1 }]);
    assert.equal(errors.length, 2); // diffusion + rejeu
  } finally {
    console.error = origError;
  }
});

test("après un échec de souscription, un nouvel appel réessaie", async () => {
  const hass = fakeHass();
  const ok = hass.connection.subscribeMessage;
  hass.connection.subscribeMessage = async () => { throw new Error("not_loaded"); };
  await assert.rejects(subscribeState(hass, () => {}), /not_loaded/);
  hass.connection.subscribeMessage = ok;
  const got = [];
  await subscribeState(hass, (s) => got.push(s));
  assert.equal(hass.subs.length, 1);
  hass.subs[0].cb({ n: 1 });
  assert.deepEqual(got, [{ n: 1 }]);
});
