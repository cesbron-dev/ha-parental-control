// Connexion partagée entre les cartes : une seule souscription à l'état par connexion HA.

const entries = new WeakMap(); // connexion -> {callbacks, last, unsub}

// Une carte qui lève ne doit pas priver les autres de l'état.
function safeCall(cb, msg) {
  try {
    cb(msg);
  } catch (err) {
    console.error(err);
  }
}

// Abonne `callback` à l'état du moteur ; renvoie (via promesse) la fonction de désabonnement.
export async function subscribeState(hass, callback) {
  const conn = hass.connection;
  let entry = entries.get(conn);
  if (!entry) {
    entry = { callbacks: new Set(), last: undefined, unsub: null };
    const e = entry;
    entries.set(conn, e);
    e.unsub = conn
      .subscribeMessage(
        (msg) => {
          e.last = msg;
          for (const cb of [...e.callbacks]) safeCall(cb, msg);
        },
        { type: "parental_control/state/subscribe" },
      )
      .catch((err) => {
        if (entries.get(conn) === e) entries.delete(conn);
        throw err;
      });
  }
  entry.callbacks.add(callback);
  // Le dernier état reçu est servi tout de suite aux nouveaux abonnés.
  if (entry.last !== undefined) safeCall(callback, entry.last);
  const e = entry;
  await e.unsub;
  let done = false;
  return () => {
    if (done) return;
    done = true;
    e.callbacks.delete(callback);
    if (e.callbacks.size === 0) {
      if (entries.get(conn) === e) entries.delete(conn);
      e.unsub.then((u) => u());
    }
  };
}

// Appelle un service parental_control ; ajoute `code` seulement s'il est fourni, ne lève jamais.
export async function callAction(hass, service, data, code) {
  try {
    await hass.callService("parental_control", service, code ? { ...data, code } : data);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err?.message ?? String(err) };
  }
}
