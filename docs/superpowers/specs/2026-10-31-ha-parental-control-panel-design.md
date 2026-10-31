# Contrôle parental — panneau « Règles » (pièce 3)

Olivier a demandé un panneau pour gérer la configuration des règles et m'a laissé les choix par
défaut (« on corrige au besoin ») : tout ce qui suit est **mon choix**, à corriger à l'usage.

## Intention

Modifier les règles sans écrire de JSON : enfants, frises par type de jour, quotas, appareils,
loisirs, modes. Le moteur fournit déjà `parental_control/config/get` et `config/set` (admin) ; `set`
valide (`parse_config`) et renvoie une erreur qui cite le chemin fautif.

## Décisions

- **Où** : un panneau de la barre latérale, « Règles » (`mdi:shield-edit`, URL `/parental-control`),
  **réservé aux admins**, enregistré par l'intégration (`panel_custom`, module servi depuis `www/`
  comme les cartes). Rien à installer.
- **Comment on édite** : le panneau charge la config, l'édite **en brouillon** et n'écrit qu'au clic
  sur « Enregistrer » (`config/set`). « Annuler les modifications » recharge. Un bandeau signale les
  modifications non enregistrées ; quitter la page avec un brouillon modifié demande confirmation.
  Une erreur du moteur s'affiche telle quelle (elle cite le chemin, ex. `kids[0].profiles.ecole…`).
- **Onglets** :
  1. **Enfants** — nom, emoji, couleur, calendrier scolaire (suggestions `calendar.*`) ; frise par type
     de jour (École et Fin de semaine obligatoires ; Congé pédagogique et Vacances facultatifs, sinon
     ils suivent Fin de semaine) : quota du jour et liste de segments (heure de début, type, minutes
     d'avertissement), le premier fixé à 00:00, avec un aperçu en barre colorée comme la frise des
     cartes ; loisirs ajoutés/retirés par rapport à la liste commune ; mode par appareil (Suit la
     frise, Sur demande, Bloqué, Libre ; « Suit la frise » = pas d'entrée).
  2. **Appareils** — nom, type (Télé / client AdGuard / Nintendo), enfants concernés (cases), options
     selon le type : entité `media_player` (Télé), appareil `adguard_clients` (AdGuard), appareil
     Nintendo + ses trois entités limite/restant/utilisé (suggestions filtrées sur l'appareil) ;
     quota par type de jour.
  3. **Général** — loisirs par défaut (pastilles ajout/retrait), correspondance mots du calendrier →
     type de jour, services de notification.
  4. **JSON** — la config brute, modifiable : secours et import/export.
- **Identifiants** : un nouvel enfant ou appareil reçoit un id tiré de son nom (minuscules, sans
  accents, `_`), modifiable tant qu'il n'est pas enregistré, figé ensuite (les exceptions et
  l'historique s'y rattachent). Supprimer un enfant le retire aussi des propriétaires et des modes ;
  supprimer un appareil retire les modes qui le citent — sinon le moteur refuserait la config.
- **Technique** : JavaScript sans compilation, comme les cartes ; logique pure (édition du brouillon,
  identifiants, segments, aperçu) dans un module testé sous `node --test` ; style « verre » sombre
  des cartes.

## Hors périmètre

Le changement du code parent (options de l'intégration), l'historique des modifications, l'édition
simultanée à plusieurs.
