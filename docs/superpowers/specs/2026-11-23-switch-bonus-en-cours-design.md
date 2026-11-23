# Carte Switch : bonus en cours visible partout

## Intention

Un bonus Switch passe par tranches de 30 min (5 s entre deux) suivies d'une relecture des
capteurs Nintendo : 10 à 15 s pour 1 h. Pendant ce temps la carte ne montre rien et ses pilules
restent cliquables. On veut voir qu'une mise à jour est en cours, **quel que soit l'endroit d'où
vient le bonus** (carte, code parent, service, demande acceptée par notification ou panneau),
par exemple sur la tablette du salon.

## Objectifs / non-objectifs

- Objectif : indicateur « Mise à jour du temps… » sur la carte Switch, pilules désactivées,
  jauge grisée, tant qu'un bonus est en train d'être accordé sur la ressource.
- Non-objectif : progression tranche par tranche, indicateur sur les autres cartes.
- Anti-objectif : un indicateur qui reste bloqué après un échec du bonus.

## Approches

1. **Moteur publie l'état (retenue)** : `engine.add_bonus` est le seul chemin ; il compte les
   bonus en cours par ressource et le snapshot expose `granting`.
2. Carte seule : ne voit pas les bonus accordés ailleurs. Écartée.
3. Déduire des capteurs Nintendo : ils ne changent qu'en fin de tranche. Écartée.

## Design

- `ParentalEngine._granting: dict[str, int]` incrémenté avant `adapter.grant`, décrémenté dans un
  `finally` ; `async_dispatcher_send(SIGNAL_UPDATE)` au début et à la fin. Propriété
  `granting(resource_id) -> bool`.
- `serialize_snapshot` : chaque ressource reçoit `granting: bool` (lisible sans être admin).
- `switch-card.js` : si `granting`, classe `.busy` (jauge grisée et pulsation), ligne
  `card.switch.updating` avec icône, pilules `disabled`. Textes fr/en.
- Simulation : l'enveloppe ne fait que journaliser, l'indicateur ne dure qu'un instant.

## Laissé au constructeur

Détails CSS de la pulsation ; respect de `prefers-reduced-motion`.
