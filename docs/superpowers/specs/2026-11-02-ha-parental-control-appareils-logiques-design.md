# Contrôle parental — appareils logiques (pièce 4)

## Intention

Pour la famille, « la Télé » est **un** appareil. Derrière, il y a plusieurs choses à piloter : chez
Olivier, la Samsung (lecteur multimédia HA + son client AdGuard) et une Google TV / Chromecast
(lecteur multimédia + deux clients AdGuard, un en local et un par le VPN). Aujourd'hui le moteur
impose une ressource par intégration (`tv` en `media_player`, `tv_adguard` en `adguard_services`) :
deux cartes, deux jeux de règles, et un utilisateur lambda qui ne comprend pas la différence.

On ajoute une hiérarchie : **appareil logique → appareils physiques → intégrations**. Les règles se
posent sur l'appareil logique ; chaque intégration applique la même décision à sa façon.

## Décisions d'Olivier

- Un appareil logique regroupe plusieurs appareils physiques ; on ne voit que lui sur la tablette
  (une carte « Télé »).
- Les règles (enfants concernés, quota par type de jour, mode par enfant) se règlent une fois, sur
  l'appareil logique ; Samsung et filtrage DNS appliquent la même décision : fermé → lecteurs
  éteints et clients AdGuard fermés ; « Autoriser 30 min » ouvre tout ; « Arrêter » ferme tout.
- Autoriser un service (YouTube) sur la Télé l'ouvre sur **tous** ses clients AdGuard.
- Quota de la Télé : le temps compte dès qu'**un** lecteur multimédia de l'appareil est en marche,
  **une seule fois** même si plusieurs tournent en même temps.
- Configuration en **arbre à 3 niveaux** (maquette A) : Télé → Samsung, Google TV → leurs
  intégrations, avec « + Ajouter une intégration » sous chaque appareil physique et « + Ajouter un
  appareil physique » sous l'appareil logique ; une pastille dit si l'intégration est trouvée dans HA.

## Modèle

Vocabulaire : dans le code, l'appareil logique reste la **ressource** (`Resource`, id stable : les
exceptions, l'historique d'usage, les modes par enfant et les entités HA s'y rattachent). Dessous :

- **appareil physique** (`devices`) : `{name, integrations: [...]}` — une étiquette pour ranger,
  sans règle propre (*mon choix*) ;
- **intégration** (`integrations`) : `{kind, ...options}` avec les mêmes `kind` et options
  qu'aujourd'hui : `media_player` (`entity_id`, `notify_service` facultatif), `adguard_services`
  (`device_id`), `nintendo` (`device_id`, `limit_entity`, `remaining_entity`, `used_entity`).

Config (JSON, `version: 2`) :

```json
{"id": "tv", "name": "Télé", "icon": "mdi:television", "owners": ["gabin","leo","mael"],
 "quota_minutes": {"fin_de_semaine": 90},
 "devices": [
   {"name": "Samsung", "integrations": [
     {"kind": "media_player", "entity_id": "media_player.tv_salon"},
     {"kind": "adguard_services", "device_id": "…"}]},
   {"name": "Google TV", "integrations": [
     {"kind": "media_player", "entity_id": "media_player.google_tv"},
     {"kind": "adguard_services", "device_id": "…"},
     {"kind": "adguard_services", "device_id": "…"}]}]}
```

`icon` est facultatif (sinon déduit). `kind` disparaît du niveau ressource.

### Comportement déduit des intégrations (*mon choix*, fidèle au moteur actuel)

Le moteur raisonne aujourd'hui sur `resource.kind`. Il raisonne désormais sur **ce que contient**
l'appareil :

- **contient au moins un lecteur multimédia** → comportement « Télé » actuel : budget de
  l'appareil (`quota_minutes` de la ressource), compteur d'usage commun incrémenté quand
  `in_use()` d'au moins un lecteur est vrai, bonus de ressource (`ajouter_bonus` resource_id) en
  minutes de quota ;
- **contient au moins un client AdGuard** → comportement « services » actuel : fermé = loisirs
  bloqués (`blocked_services`), exceptions par service possibles, appliqués à **chaque** client ;
- un appareil **AdGuard seul** garde exactement le comportement actuel (budget de l'enfant) ;
- **Nintendo** : une intégration Nintendo ne cohabite avec **aucune** autre dans le même appareil
  logique (validation refusée, message clair) et une seule par appareil — *mon choix* : la Switch
  se pilote par bonus et compte son temps elle-même, la mélanger n'a pas de sens aujourd'hui.
  Son comportement ne change pas (refus d'`exception`, `ajouter_bonus` → `grant`).
- au moins une intégration par appareil logique ; un appareil physique sans intégration est
  accepté (en cours de saisie dans le panneau) mais ne pilote rien.

### Application (adaptateurs)

Un adaptateur par intégration (les trois existants, inchangés dans leur logique) et un adaptateur
**composite** par ressource : `entity_ids` = union ; `in_use` = l'un des lecteurs ; `drifted` =
l'un des membres ; `apply`, `warn`, `force_close` = chaque membre, **isolément** (l'échec ou
l'absence d'un membre — Chromecast VPN débranché — est journalisé une fois et n'empêche pas les
autres) ; `grant` = l'intégration Nintendo. Le moteur ne voit que le composite.

## Migration

Une config `version: 1` (ressources plates avec `kind`) est **acceptée et convertie** à la lecture
(`parse_config`, `importer_configuration`, stockage) : chaque ressource devient un appareil logique
avec un appareil physique (même nom) et une intégration (même `kind` et options). Le stockage est
réécrit en v2 au premier enregistrement. Aucun changement de comportement tant qu'on ne touche à
rien. `config/get` renvoie toujours du v2.

Regrouper la Télé est ensuite une action dans le panneau (voir « Déplacer »), pas une migration
automatique : rien ne permet de deviner que `tv_adguard` va avec `tv`.

## Panneau « Règles », onglet Appareils

Arbre de la maquette A pour chaque appareil logique :

- en-tête : icône, nom, enfants concernés, nombre d'intégrations ; réglages de l'appareil logique
  (nom, icône, enfants, quota par type de jour) comme aujourd'hui ;
- niveau 2 : appareils physiques (nom modifiable, supprimer, **« Déplacer vers… »** un autre
  appareil logique — c'est ainsi qu'on range « TV (AdGuard) » sous la Télé ; un appareil logique
  vidé de ses appareils physiques est proposé à la suppression) ;
- niveau 3 : intégrations (type, réglage selon le type comme aujourd'hui : entité `media_player`,
  appareil `adguard_clients`, appareil Nintendo + ses trois entités), supprimer, et une pastille
  verte/rouge selon que l'entité ou l'appareil existe dans HA ;
- « + Ajouter une intégration » sous un appareil physique, « + Ajouter un appareil physique » sous
  l'appareil logique, « + Ajouter un appareil » en bas ;
- un appareil logique Nintendo n'offre pas d'ajout d'autre type (et inversement on ne peut pas
  ajouter de Nintendo à un appareil qui a autre chose) ;
- supprimer un appareil logique retire toujours les modes qui le citent.

Les modes par enfant (onglet Enfants) listent les appareils logiques, comme aujourd'hui.

## Cartes et entités

- `state/subscribe` (affichage) : par ressource, `kind` reste fourni pour les cartes, **déduit** :
  `nintendo` si Nintendo, sinon `media_player` s'il y a un lecteur, sinon `adguard_services` ; en
  plus `kinds` (liste des types présents) et `icon`. Les cartes existantes marchent donc sans
  changement ; la carte appareil utilise `icon` s'il est fourni et propose « Autoriser un service »
  dès que `kinds` contient `adguard_services`.
- Éditeur visuel : la liste d'appareils montre les appareils logiques (libellé : nom seul, plus de
  type entre parenthèses quand l'appareil en a plusieurs).
- Entités HA : capteurs de durée si l'appareil a un lecteur ou est Nintendo ; attribut
  `blocked_services` du capteur « autorisé » si l'appareil a un client AdGuard. Identifiants
  inchangés (fondés sur l'id de ressource).

## Mode simulation (dry-run)

Demande d'Olivier : vérifier sur l'instance de test que tout est juste avant de configurer la
prod. Le moteur décide comme d'habitude, mais **ne touche à aucun appareil** et dit ce qu'il
aurait fait.

- **Interrupteur** `switch.<…>_simulation` (« Simulation »), à côté de « Pause », état conservé
  au redémarrage. *Mon choix* : une **nouvelle** installation démarre en simulation (on configure,
  on observe, puis on coupe) ; une installation existante reste en mode réel à la mise à jour.
- **Ce qui est simulé** : tout appel d'adaptateur — `apply` (extinction d'un lecteur, services
  AdGuard), `warn` (message sur l'appareil), `grant` (bonus Nintendo), `force_close` (pause), et la
  correction d'une dérive. Garde unique : un adaptateur « simulation » qui enveloppe le composite
  et remplace chaque appel par une trace. Les décisions (exceptions, bonus de quota, devoirs,
  compteur d'usage, frise) fonctionnent normalement : les cartes et capteurs montrent ce qui se
  passerait.
- **Ce qui ne l'est pas** (*mon choix*) : les notifications aux parents (`notify`) partent,
  préfixées « [Simulation] », pour pouvoir vérifier les alertes.
- **Où voir ce qu'il aurait fait** : une entrée de **journal de bord** HA par action, au nom de
  l'appareil logique, ex. « Simulation : éteindrait Samsung (media_player.tv_salon) »,
  « Simulation : bloquerait youtube, roblox sur Chromecast (VPN) » — seulement quand l'action
  diffère de la précédente pour cette intégration (pas de répétition à chaque évaluation) ; plus
  une ligne de log `info`.
- **Visible partout** : bandeau « Simulation — aucun appareil n'est piloté » en tête du panneau
  Règles ; petit badge « SIMULATION » sur les cartes ; `simulation: true` dans l'état WebSocket.
- **Sortie de simulation** : le moteur réapplique immédiatement l'état voulu à toutes les
  intégrations (resynchronisation), comme au démarrage.

Indépendant du reste : peut être livré en premier, sur le modèle actuel, puis suivre les appareils
logiques (une trace par intégration).

## Hors périmètre

- Proposer automatiquement les intégrations d'un même appareil physique (adresse MAC commune) :
  idée notée pour plus tard.
- Règles propres à un appareil physique.
- Regrouper automatiquement la config existante d'Olivier : il le fait dans le panneau.

## Précisions (relecture)

- **Jour sans quota d'appareil** (décision d'Olivier) : un appareil avec lecteur multimédia dont
  `quota_minutes` ne définit rien pour le type de jour prend, pour chaque enfant concerné, le quota
  de temps d'écran de sa frise (`profile.quota_minutes` + bonus de l'enfant) ; l'appareil étant
  partagé, la limite retenue est **la plus généreuse** des enfants concernés (même règle que
  l'actuel `max(budgets)`). L'usage reste le compteur commun de l'appareil. Si aucun enfant n'a de
  quota ce jour-là : pas de limite. S'applique à tout appareil avec lecteur, y compris une télé
  seule (changement assumé par rapport à aujourd'hui, où « pas de quota d'appareil » = illimité).

- **Un seul mode par enfant et par appareil logique** (`resource_modes[<id>]`), appliqué à toutes
  ses intégrations — décision d'Olivier (« les règles se règlent une fois »).
- **Validation dans le moteur** (`parse_config`), donc aussi pour `config/set` et
  `importer_configuration` : Nintendo seul et unique dans son appareil ; au moins une intégration
  par appareil logique (le brouillon du panneau peut temporairement en avoir zéro, l'enregistrement
  est refusé avec le chemin fautif) ; appareil physique sans intégration accepté.
- **« Déplacer vers… »** est une opération du brouillon du panneau (pas de commande WebSocket) :
  l'appareil physique passe sous l'appareil cible ; si la source est vidée, elle est supprimée à
  l'enregistrement comme une suppression normale (ses modes retirés ; ses exceptions, bonus et
  usage du jour, rattachés à son id, cessent de s'appliquer — comme aujourd'hui pour une ressource
  supprimée). Le panneau l'annonce dans le bandeau de confirmation (*mon choix*).
- **Entités HA** : créées et retirées à chaud par `async_track_entities` quand les capacités d'un
  appareil changent (comportement existant), pas de redémarrage.
- **Cartes** : seule la carte appareil (et son éditeur) lit `kinds` ; les autres fichiers ne
  changent que si un test le montre nécessaire.

## Laissé au constructeur

Découpage des fonctions de l'évaluateur pour passer de `kind` aux capacités, forme exacte du
composite, présentation fine de l'arbre (dans le style « verre » existant du panneau), tests.
