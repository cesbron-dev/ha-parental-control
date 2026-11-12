# Services configurables — conception

Date : 2026-11-11. Statut : validé en conversation (maquettes approuvées par Olivier).
Remplace la partie « label de service » de `2026-11-10-ha-parental-control-services-par-label-design.md`
(jamais publiée hors bêta) ; les labels de cible restent tels quels.

## Intention

Aujourd'hui, un service est soit un identifiant AdGuard (`youtube`, `roblox`…) tiré d'un catalogue
de plusieurs dizaines d'entrées, soit un label HA déclaré « label de service » (`label:<id>`). La
liste est longue et collée à AdGuard.

Olivier veut que le parent **crée sa propre liste de services** dans l'écran Général, puis rattache
à chaque service ce qui le bloque réellement :

- un ou plusieurs **services AdGuard Home**, choisis par leur nom dans le catalogue AdGuard ;
- et/ou un ou plusieurs **labels d'interrupteurs tiers** (règles UniFi, etc.).

Exemple : « Jeux vidéo » = Roblox + Fortnite + Steam (AdGuard) + label « Console » (règle UniFi).

## Objectifs

- Une liste de services définie par le parent (nom, icône, rattachements), dans l'onglet Général.
- Ces services sont **la seule unité** partout ailleurs : loisirs et sur demande (par défaut et par
  enfant), demandes d'accès, exceptions, notifications, cartes, simulation. Le catalogue AdGuard ne
  sert plus qu'à choisir ce qu'on rattache.
- Bloquer un service bloque d'un coup tout ce qui y est rattaché ; l'ouvrir ouvre tout.

## Non-objectifs

- Pas de migration de l'existant (décidé par Olivier) : à la mise à jour, on **repart d'une liste
  vide**. Les identifiants AdGuard bruts présents dans les loisirs, sur demande, exceptions ou
  demandes deviennent inconnus et sont ignorés. Conséquence assumée : les services AdGuard que
  l'ancienne configuration avait bloqués restent bloqués sur les clients (l'intégration ne les gère
  plus) jusqu'à ce que le parent les débloque ou les rattache à un service ; le README le dit.
- Pas de changement des labels de cible (enfant ou appareil logique), de l'interrupteur d'appareil
  (`ResourceKind.SWITCH`) ni du calcul des frises.
- Pas de groupes de services imbriqués.

## Anti-objectifs

- Toucher un service AdGuard ou un interrupteur que le parent n'a rattaché à aucun service géré.
- Faire échouer le chargement d'une configuration existante : elle se charge, avec des listes vides.
- Un service AdGuard qui reste ouvert alors qu'un service géré qui le contient est bloqué.

## Ce qui est décidé

### Modèle

Un service :

- `id` : identifiant stable, créé une fois à partir du nom (minuscules, sans accents, `_`),
  dédoublonné par suffixe ; il ne change pas au renommage.
- `name` : nom affiché, choisi par le parent (obligatoire, non vide).
- `icon` : icône MDI facultative (`mdi:…`).
- `adguard` : liste d'identifiants de services AdGuard (peut être vide).
- `labels` : liste de `{label_id, on_means_allowed}` (peut être vide). `on_means_allowed` est
  **par label** (deux interrupteurs d'un même service peuvent fonctionner en sens inverse) ; défaut
  `false` : allumé = bloqué.

Un service sans rattachement est permis (il ne bloque rien).

Règles de validation :

- `id` unique ; un `id` inconnu dans une liste ou une exception est ignoré (voir Configuration).
- Un label est rattaché à **au plus un** service.
- Un label ne peut pas être à la fois rattaché à un service et label de cible.
- Un même identifiant AdGuard peut figurer dans plusieurs services. Il est bloqué dès qu'un service
  géré qui le contient est bloqué (« bloqué l'emporte »).

### Comportement

- Le calcul des services bloqués (`blocked_services`), des exceptions de service et des listes
  loisirs / sur demande travaille sur les **identifiants de services du parent**.
- **AdGuard** : un appareil AdGuard bloque l'union des identifiants AdGuard des services bloqués ;
  il gère (et peut débloquer) l'union des identifiants AdGuard des services gérés, comme aujourd'hui
  pour les loisirs.
- **Interrupteurs** : un interrupteur qui porte un label rattaché au service S et un ou plusieurs
  labels de cible suit l'état de S pour ses cibles, exactement comme les services par label actuels
  (cible enfant = état de l'enfant ; cible appareil = état du service sur l'appareil ; plusieurs
  cibles = bloqué dès qu'une l'exige ; service non géré pour les cibles = interrupteur laissé tel
  quel ; dérive corrigée ; sans cible = avertissement).
- Ce qui distinguait « service AdGuard » et « service par label » (préfixe `label:`) se lit
  désormais dans le service :
  - « concerne AdGuard » = le service a au moins un identifiant AdGuard ;
  - « concerne des interrupteurs » = le service a au moins un label.
  Un service mixte a les deux comportements.
- Les services ouverts par exception qui gardent les lecteurs allumés (`opened_services`) et les
  avertissements de fermeture de service ne concernent que les services qui ont de l'AdGuard.
- Une exception ou une demande sur un service est valide si sa portée contient un appareil AdGuard
  et que le service a de l'AdGuard, ou si le service a des labels et que la portée n'est pas vide.

### Configuration

- Nouvelle clé `services` (liste ordonnée, ordre d'affichage) dans la configuration stockée.
- La clé `label_services` (bêta 0.4.0-beta.1) et les identifiants `label:…` disparaissent ; une
  clé `label_services` présente est ignorée au chargement.
- Chargement d'une configuration stockée : les identifiants de service inconnus dans
  `default_leisure`, `default_on_demand` et les ajouts / retraits par enfant sont retirés sans
  erreur (avec une ligne de journal). Une configuration envoyée par le panneau qui contient un
  identifiant inconnu est refusée (`invalid_config`).
- Exceptions et demandes en cours sur un service inconnu : sans effet.

### Panneau Règles (maquettes validées)

- **Général › Services** : liste des services (icône, nom, pastilles des rattachements : AdGuard
  et labels avec le nombre d'interrupteurs trouvés), « Ajouter un service ». Remplace la carte
  « Services par label ».
- **Édition d'un service** : nom, icône ; liste des services AdGuard rattachés avec retrait, ajout
  par recherche dans le catalogue AdGuard ; liste des labels rattachés avec, pour chacun, les
  interrupteurs trouvés et la bascule « Allumé = autorisé » ; ajout d'un label parmi les labels HA
  libres (ni rattachés ailleurs, ni de cible) ; « Supprimer » retire aussi le service de toutes les
  listes.
- **Loisirs / sur demande** (par défaut et par enfant) : ne proposent que les services du parent.
- Le récapitulatif « Interrupteurs pilotés » et le champ « Label de cible » restent.

### Cartes

- Les noms et icônes affichés viennent des services du parent (état publié). Les éditeurs de carte
  (« Services affichés ») listent ces services.

## Contraintes

- Même architecture : moteur pur dans `core/`, adaptateurs dans `adapters/`, WebSocket et panneau
  existants. Textes en français. Seuls les parents modifient la configuration.
- Tests pytest et JS, comme aujourd'hui ; non-régression sur le comportement AdGuard pour un
  service à un seul identifiant AdGuard.
- Même branche `feat/services-par-label` ; version publiée en bêta `v0.4.0-beta.2`.

## Laissé au constructeur

- La forme exacte de l'état publié pour les cartes (noms, icônes, « a de l'AdGuard / des labels »).
- La génération exacte de l'identifiant et la disposition fine du panneau, dans le style actuel.
- Le nettoyage des exceptions et demandes orphelines (ignorer suffit).
