// Point d'entrée chargé par l'intégration : importe les cartes et les déclare au sélecteur de cartes.
import './resource-card.js';
import './timeline-card.js';
import './switch-card.js';
import './kid-card.js';
import { tLang } from './i18n.js';

// Sans `hass` au chargement : nom et description dans la langue du navigateur.
const language = globalThis.navigator?.language;
const CARDS = ['resource', 'timeline', 'switch', 'kid'].map((key) => ({
  type: `parental-${key}-card`,
  name: tLang(language, `cards.${key}.name`),
  description: tLang(language, `cards.${key}.description`),
}));

window.customCards = window.customCards || [];
for (const card of CARDS) {
  if (!window.customCards.some((c) => c.type === card.type)) window.customCards.push(card);
}

console.info('Parental control: cards loaded');
