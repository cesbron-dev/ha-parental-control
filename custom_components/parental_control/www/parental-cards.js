// Point d'entrée chargé par l'intégration : importe les cartes et les déclare au sélecteur de cartes.
import './resource-card.js';
import './timeline-card.js';

const CARDS = [
  {
    type: 'parental-resource-card',
    name: 'Contrôle parental — Appareil',
    description: "État d'un appareil du moteur, autorisations en cours, Autoriser… et Arrêter.",
  },
  {
    type: 'parental-timeline-card',
    name: 'Contrôle parental — Frise',
    description: "Frise de la journée de chaque enfant : segments, maintenant et exceptions en cours.",
  },
];

window.customCards = window.customCards || [];
for (const card of CARDS) {
  if (!window.customCards.some((c) => c.type === card.type)) window.customCards.push(card);
}

console.info('Contrôle parental : cartes chargées');
