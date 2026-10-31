// Socle des cartes qui suivent l'état du moteur : souscription WebSocket liée au cycle de vie de l'élément.
import { subscribeState } from "./connection.js";
import { shouldSubscribe } from "./lib.js";

export class StateCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._state = undefined; // undefined : pas encore reçu ; null : souscription impossible
    this._unsub = null;
    this._subConn = null;
    this._failedConn = null; // connexion sur laquelle la souscription vient d'échouer
    this._tick = null;
  }

  // À surcharger : dessine la carte.
  _render() {}

  // Appelé à chaque nouveau `hass` (souvent) : les cartes ne redessinent que si leur affichage change.
  _hassChanged() {}

  // Appelé à la déconnexion, en plus du nettoyage commun.
  _cleanup() {}

  set hass(hass) {
    this._hass = hass;
    if (this.isConnected) this._subscribe();
    this._hassChanged(hass);
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass) this._subscribe();
    // Compte à rebours des pilules rafraîchi chaque minute.
    clearInterval(this._tick);
    this._tick = setInterval(() => {
      if (!this._unsub && !this._subConn && this.isConnected) {
        this._failedConn = null;
        this._subscribe();
      }
      this._render();
    }, 60000);
    this._render();
  }

  disconnectedCallback() {
    clearInterval(this._tick);
    this._tick = null;
    this._cleanup();
    this._unsubscribe();
  }

  _subscribe() {
    const conn = this._hass?.connection;
    if (!shouldSubscribe(conn, this._subConn, this._failedConn)) return;
    this._unsubscribe();
    this._subConn = conn;
    const token = {};
    this._subToken = token;
    subscribeState(this._hass, (msg) => {
      if (this._subToken !== token) return;
      this._state = msg;
      this._render();
    }).then(
      (unsub) => {
        // Déconnectée entre-temps : on relâche tout de suite la souscription.
        if (this._subToken !== token) unsub();
        else this._unsub = unsub;
      },
      () => {
        if (this._subToken !== token) return;
        // Échec (ex. `not_loaded` juste après un redémarrage de HA) : le tick de 60 s réessaiera.
        this._failedConn = this._subConn;
        this._subConn = null;
        this._state = null;
        this._render();
      },
    );
  }

  _unsubscribe() {
    this._subToken = null;
    this._subConn = null;
    this._unsub?.();
    this._unsub = null;
  }
}
