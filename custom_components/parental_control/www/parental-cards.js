// Point d'entrée chargé par l'intégration : importe les cartes et les déclare au sélecteur de cartes.
import './resource-card.js';

const CARDS = [
  {
    type: 'parental-resource-card',
    name: 'Contrôle parental — Appareil',
    description: "État d'un appareil du moteur, autorisations en cours, Autoriser… et Arrêter.",
  },
];

window.customCards = window.customCards || [];
for (const card of CARDS) {
  if (!window.customCards.some((c) => c.type === card.type)) window.customCards.push(card);
}

console.info('Contrôle parental : cartes chargées');
