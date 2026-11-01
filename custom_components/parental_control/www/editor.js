// Éditeurs visuels des cartes (alternative au YAML) : un `ha-form` dont les listes d'appareils et
// d'enfants viennent de l'état du moteur.
import { subscribeState } from "./connection.js";
import { editorSchema, editorConfig, editorData } from "./editor-lib.js";

class ParentalCardEditor extends HTMLElement {
  constructor(card) {
    super();
    this._card = card;
    this._state = undefined; // undefined : pas encore reçu ; null : souscription impossible
    this._unsub = null;
    this._subConn = null;
    this.attachShadow({ mode: "open" });
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // Une seule tentative de souscription par connexion : en cas d'échec, saisie libre de l'id.
    if (hass?.connection && hass.connection !== this._subConn) this._subscribe(hass);
    this._render();
  }

  disconnectedCallback() {
    this._unsub?.();
    this._unsub = null;
    this._subConn = null;
  }

  async _subscribe(hass) {
    this._unsub?.();
    this._unsub = null;
    this._subConn = hass.connection;
    try {
      const unsub = await subscribeState(hass, (state) => {
        this._state = state;
        this._render();
      });
      if (this._subConn === hass.connection) this._unsub = unsub;
      else unsub();
    } catch (err) {
      console.warn("Contrôle parental : état indisponible pour l'éditeur", err);
      this._state = null;
      this._render();
    }
  }

  _render() {
    if (!this._hass || !this._config) return;
    let form = this.shadowRoot.querySelector("ha-form");
    if (!form) {
      form = document.createElement("ha-form");
      form.computeLabel = (s) => s.label ?? s.name;
      form.computeHelper = (s) => s.helper;
      form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        this._config = editorConfig(this._config, ev.detail.value);
        this.dispatchEvent(new CustomEvent("config-changed", {
          detail: { config: this._config }, bubbles: true, composed: true,
        }));
      });
      this.shadowRoot.append(form);
    }
    form.hass = this._hass;
    form.data = editorData(this._config);
    form.schema = editorSchema(this._card, this._state, this._config);
  }
}

const EDITORS = { resource: "parental-resource-card-editor", switch: "parental-switch-card-editor", timeline: "parental-timeline-card-editor" };
for (const [card, tag] of Object.entries(EDITORS)) {
  if (!customElements.get(tag)) {
    customElements.define(tag, class extends ParentalCardEditor {
      constructor() {
        super(card);
      }
    });
  }
}

// Élément d'édition d'une carte, pour `static getConfigElement()`.
export const createEditor = (card) => document.createElement(EDITORS[card]);
