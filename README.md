# Contrôle parental pour Home Assistant

Intégration Home Assistant (HACS) de contrôle parental. Chaque enfant a une frise
horaire par type de journée (école, fin de semaine, congé pédagogique, vacances).
Le moteur l'applique en continu aux téléviseurs (`media_player`), aux services
AdGuard Home (via [ha-adguard-clients](https://github.com/cesbron-dev/ha-adguard-clients)) et aux consoles Nintendo Switch. Il gère aussi
les devoirs, les quotas, les minuteurs, les bonus, les exceptions manuelles et une
pause générale.

Le projet comporte trois pièces :

1. **le moteur** (ce dépôt) : intégration, services, entités, API WebSocket ;
2. **les cartes du tableau de bord** : voir [Cartes](#cartes) ;
3. **l'éditeur visuel de la configuration** : à venir.

En attendant l'éditeur, la configuration se charge sous forme de JSON (voir plus bas).

## Installation (HACS)

1. HACS, menu en haut à droite, **Dépôts personnalisés**.
2. Dépôt `https://github.com/cesbron-dev/ha-parental-control`, catégorie **Intégration**.
3. Installer « Parental Control », puis redémarrer Home Assistant.
4. **Paramètres, Appareils et services, Ajouter une intégration, Contrôle parental**
   (l'intégration est listée sous ce nom dans Home Assistant, « Parental Control » dans HACS).
5. Choisir le **code parent** : 4 à 8 chiffres. Il est stocké haché (PBKDF2), jamais en clair.
   Une seule instance de l'intégration est possible. Le code se change plus tard dans les
   options de l'intégration.

Une fois ajoutée, l'intégration n'a encore aucune configuration : chargez le JSON ci-dessous.

## Configuration JSON

### Exemple annoté

Le JSON est un document unique (les commentaires `//` ci-dessous sont à retirer, JSON n'en
accepte pas).

```jsonc
{
  "version": 2,                       // 2 (la version 1 est convertie, voir « Appareils logiques »)
  "default_leisure": ["youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch"],
  "calendar_map": {                   // mot (sans accent ni casse) -> type de journée
    "pédagogique": "conge_peda",
    "vacances": "vacances",
    "relâche": "vacances"
  },
  "notify": ["notify.mobile_app_iphone_de_marc"],   // services notify des parents
  "kids": [
    {
      "id": "hugo",                  // identifiant unique, utilisé par les services
      "name": "Hugo",
      "emoji": "🎮",                  // optionnel (pour les cartes)
      "color": "#FF6B6B",             // optionnel (pour les cartes)
      "calendar": "calendar.ecole_primaire",   // optionnel : calendrier du type de journée
      "leisure_add": [],              // services de loisirs en plus de default_leisure
      "leisure_remove": [],           // services retirés de default_leisure
      "resource_modes": { "switch": "sur_demande" },   // optionnel, par ressource
      "profiles": {
        "ecole": {                    // profils "ecole" et "fin_de_semaine" obligatoires
          "segments": [
            { "start": "00:00", "type": "bloque" },
            { "start": "15:25", "type": "libre" },
            { "start": "16:00", "type": "apres_devoirs" },
            { "start": "19:00", "type": "bloque" }
          ]
        },
        "fin_de_semaine": {
          "quota_minutes": 120,       // budget journalier de l'enfant (segments "quota")
          "segments": [
            { "start": "00:00", "type": "bloque" },
            { "start": "08:00", "type": "quota" },
            { "start": "20:00", "type": "bloque" }
          ]
        }
      }
    }
  ],
  "resources": [                      // appareils logiques
    {
      "id": "tv",
      "name": "Télé salon",
      "icon": "mdi:television",       // optionnel
      "owners": ["hugo"],
      "quota_minutes": { "fin_de_semaine": 180 },
      "devices": [                    // appareils physiques
        {
          "name": "Samsung",
          "integrations": [
            {
              "kind": "media_player",
              "entity_id": "media_player.tv_salon",
              "notify_service": null  // optionnel : "notify.xxx" pour avertir sur l'appareil
            },
            { "kind": "adguard_services", "device_id": "1ef9511faa6db9c5969524170a8fe8e3" }
          ]
        }
      ]
    },
    {
      "id": "iphone_hugo",
      "name": "iPhone Hugo",
      "owners": ["hugo"],
      "devices": [
        {
          "name": "iPhone Hugo",
          "integrations": [
            { "kind": "adguard_services", "device_id": "7c2a9e0b4d1f4e6a8b3c5d7e9f102132" }
          ]
        }
      ]
    },
    {
      "id": "switch",
      "name": "Switch",
      "owners": ["hugo"],
      "devices": [
        {
          "name": "Switch",
          "integrations": [
            {
              "kind": "nintendo",
              "device_id": "c52a9e7f10b84d3698e1f4a7d3b60c28",
              "limit_entity": "number.switch_papa_temps_d_ecran_max_aujourd_hui",
              "remaining_entity": "sensor.switch_papa_temps_d_ecran_restant",
              "used_entity": "sensor.switch_papa_temps_d_ecran_utilise"
            }
          ]
        }
      ]
    }
  ]
}
```

### Les clés

**Racine**

| Clé | Rôle |
|---|---|
| `version` | `2`. Une configuration en `1` (ou sans `version`) est convertie à la lecture. |
| `default_leisure` | Services AdGuard considérés comme des loisirs (ce sont eux que le moteur bloque et débloque). Défaut : `youtube`, `roblox`, `tiktok`, `netflix`, `disneyplus`, `twitch`. |
| `calendar_map` | Associe un mot cherché dans le titre des événements « journée entière » du calendrier de l'enfant à un type de journée. Comparaison sans accent ni casse, par inclusion. |
| `notify` | Services `notify.*` des parents : avertissements de fin de plage d'un enfant et de re-blocage d'un service AdGuard ouvert par exception. |
| `kids` | Liste des enfants. |
| `resources` | Liste des appareils logiques contrôlés (voir [Appareils logiques](#appareils-logiques)). |

**Enfant (`kids[]`)**

| Clé | Rôle |
|---|---|
| `id`, `name` | Identifiant unique et nom affiché (obligatoires). |
| `emoji`, `color` | Décoration pour les cartes (optionnels). |
| `calendar` | Entité `calendar.*` dont les événements « journée entière » déterminent le type de journée. |
| `leisure_add`, `leisure_remove` | Ajustent `default_leisure` pour cet enfant. |
| `resource_modes` | Par `id` de ressource, remplace le comportement de la frise : `suit_frise` (défaut), `sur_demande`, `bloque` ou `libre`. |
| `profiles` | Un profil par type de journée : `ecole`, `fin_de_semaine`, `conge_peda`, `vacances`. `ecole` et `fin_de_semaine` sont obligatoires. |

**Profil**

| Clé | Rôle |
|---|---|
| `segments` | Frise de la journée (au moins un segment). Le premier commence à `00:00`, les heures `start` (`HH:MM`) sont strictement croissantes ; un segment dure jusqu'au début du suivant, ou jusqu'à minuit. |
| `quota_minutes` | Budget journalier de l'enfant pour les segments `quota` mesurés par minuteur (optionnel : sans lui, pas de limite). |
| `warn_minutes` (dans un segment) | Préavis avant la fin de la plage ouverte, en minutes (défaut `5`). |

**Types de segment**

| Type | Comportement |
|---|---|
| `bloque` | Tout est bloqué. |
| `libre` | Tout est autorisé. |
| `apres_devoirs` | Autorisé seulement après `devoirs_termines` du jour ; sinon statut « en attente des devoirs ». |
| `quota` | Autorisé dans la limite du budget. Pour l'enfant : il faut démarrer un minuteur (`demarrer_minuteur`), le temps du minuteur est décompté du `quota_minutes` du profil ; les ressources AdGuard ne s'ouvrent que pendant ce minuteur. Seul un appareil avec un lecteur multimédia (`media_player`) ou un interrupteur (`switch`) a son propre budget, décompté par l'usage réel : son `quota_minutes` pour le type de journée, ou à défaut le quota de temps d'écran le plus généreux des enfants concernés (voir [Appareils logiques](#appareils-logiques)). Illimité seulement si ni l'appareil ni aucun de ces enfants n'a de quota ce jour-là. La Switch n'a pas de quota côté moteur : on lui accorde du temps avec `ajouter_bonus` (`resource_id: switch`). |
| `sur_demande` | Bloqué jusqu'à ce qu'un parent ouvre (service `exception` avec `open: true`) ; statut « sur demande ». Pour la Switch, pas d'exception : `ajouter_bonus` avec `resource_id: switch`. |

**Type de journée.** Le calendrier de l'enfant fixe le type via `calendar_map`. Priorité en
cas de recoupement : `vacances`, puis `conge_peda`, puis `ecole` / `fin_de_semaine`. Sans
événement reconnu : `ecole` du lundi au vendredi, `fin_de_semaine` samedi et dimanche.
Si le profil `conge_peda` ou `vacances` n'existe pas, c'est le profil `fin_de_semaine` qui
s'applique (et, pour une ressource, son `quota_minutes` de `fin_de_semaine`).

**Ressource (`resources[]`, appareil logique)**

| Clé | Rôle |
|---|---|
| `id`, `name` | Identifiant unique et nom affiché (obligatoires). |
| `icon` | Icône `mdi:` (optionnel, sinon déduite). |
| `owners` | Liste d'`id` d'enfants, qui doivent exister. |
| `quota_minutes` | Objet optionnel `{ "<type de journée>": minutes }`. |
| `devices` | Appareils physiques : `{ "name": ..., "integrations": [...] }`. Au moins une intégration au total. |

Chaque intégration porte un `kind` :

| `kind` | Clés propres | Remarques |
|---|---|---|
| `media_player` | `entity_id` (obligatoire), `notify_service` (optionnel) | Tout lecteur multimédia, quelle que soit l'intégration (Samsung/SmartThings, Android TV Remote, Google Cast…). Éteint quand la règle est fermée. Temps d'usage compté, `quota_minutes` applicable. Avec Google Cast, l'extinction arrête seulement la diffusion : préférer l'entité Android TV Remote d'une Google TV. |
| `switch` | `entity_id` (obligatoire, `switch.*`), `turn_on_when_allowed` (optionnel, `false` par défaut) | Prise commandée, écran de PC… Coupé quand la règle est fermée (et recoupé s'il est rallumé). Allumé, il compte comme utilisé : temps d'usage compté, `quota_minutes` applicable. Avec `turn_on_when_allowed: true`, rallumé une fois au passage de l'appareil à « autorisé » (fin de plage fermée, fin de pause) ; jamais au démarrage de HA ni après un enregistrement de la configuration, ni par une exception de service. Attention : couper la prise d'un PC l'éteint brutalement, et une prise laissée allumée sans rien de branché consomme quand même le quota. Le panneau ne propose ni les interrupteurs du contrôle parental lui-même ni les interrupteurs de configuration (réglages AdGuard…). |
| `adguard_services` | `device_id` (obligatoire) | Appareil d'un client persistant de l'intégration `adguard_clients`. Le moteur lit l'attribut `services` de son capteur « Services bloqués » et écrit par `adguard_clients.set_blocked_services` (une écriture par décision). Seuls les services de loisirs sont gérés. |
| `nintendo` | `device_id`, `limit_entity`, `remaining_entity`, `used_entity` | Les quatre sont obligatoires ; les trois entités sont celles de l'intégration Nintendo (limite du jour en `number`, temps restant et utilisé en `sensor`). La limite du jour doit rester à 0 : le temps s'accorde par bonus. |

## Appareils logiques

Pour la famille, « la Télé » est un seul appareil, même si le moteur doit en piloter plusieurs
morceaux. La configuration a donc trois niveaux :

1. l'**appareil logique** (`resources[]`) : celui des cartes et des règles (enfants concernés,
   quota par type de journée, mode par enfant) ;
2. ses **appareils physiques** (`devices`) : de simples étiquettes pour ranger, sans règle propre ;
3. leurs **intégrations** (`integrations`) : un lecteur `media_player`, un interrupteur `switch`,
   un client AdGuard, une console Nintendo.

Exemple : la Télé, avec la Samsung (lecteur et client AdGuard) et la Google TV (lecteur et deux
clients AdGuard, un en local et un par le VPN).

```json
{
  "id": "tv",
  "name": "Télé",
  "icon": "mdi:television",
  "owners": ["hugo", "zoe"],
  "quota_minutes": { "fin_de_semaine": 90 },
  "devices": [
    {
      "name": "Samsung",
      "integrations": [
        { "kind": "media_player", "entity_id": "media_player.tv_salon" },
        { "kind": "adguard_services", "device_id": "1ef9511faa6db9c5969524170a8fe8e3" }
      ]
    },
    {
      "name": "Google TV",
      "integrations": [
        { "kind": "media_player", "entity_id": "media_player.google_tv" },
        { "kind": "adguard_services", "device_id": "5e3b8c1d9f7a4b2e6c0d8a1f3b5e7c92" },
        { "kind": "adguard_services", "device_id": "a4d8f6e2c0b14a39857e6d5c4b3a2918" }
      ]
    }
  ]
}
```

**Les règles s'appliquent une fois, à l'appareil logique.** Fermée, la Télé éteint tous ses
lecteurs et bloque les loisirs sur chaque client AdGuard ; « Autoriser » ouvre tout, « Arrêter »
ferme tout. Une exception sur un service (YouTube) s'ouvre sur tous les clients AdGuard de
l'appareil ; si l'appareil est fermé, ses lecteurs ne sont pas éteints (seul ce service
passe) ; ils le sont de nouveau à la fin de l'exception. Le mode par enfant (`resource_modes`)
est unique par appareil logique et vaut pour
toutes ses intégrations.

**Quota.** Pour un appareil qui contient un lecteur multimédia, le temps compte dès qu'un lecteur
est en marche, une seule fois même si plusieurs tournent ensemble : c'est le compteur commun de
l'appareil. Le budget est le `quota_minutes` de l'appareil pour le type de journée ; à défaut, le
quota de temps d'écran de la frise de chaque enfant concerné (avec ses bonus), et comme
l'appareil est partagé, c'est le plus généreux de ces quotas qui s'applique. Aucun quota nulle
part ce jour-là : pas de limite. Cela vaut aussi pour une télé seule. Un appareil sans lecteur
(AdGuard seul) s'ouvre pendant un minuteur de l'enfant et puise dans son budget.

**Nintendo.** Une console doit rester seule dans son appareil logique : une seule intégration
`nintendo`, aucune autre. Le moteur refuse sinon la configuration (« une console Nintendo ne se
regroupe pas »). Son fonctionnement ne change pas (bonus, pas d'exception).

**Intégration absente.** Un lecteur, un client AdGuard ou une console introuvable dans Home
Assistant (un Chromecast débranché, par exemple) est signalé une fois dans les journaux et
ignoré : les autres intégrations de l'appareil continuent d'être pilotées.

**Anciennes configurations.** Une configuration en version 1 (ressources plates avec `kind`) est
acceptée et convertie à la lecture : chaque ressource devient un appareil logique avec un seul
appareil physique (même nom) et une seule intégration. Le stockage est réécrit en version 2 au
premier enregistrement. Le comportement ne change pas, sauf pour le quota de repli : une télé
sans `quota_minutes` pour le type de journée, illimitée en version 1, prend maintenant le quota
de temps d'écran le plus généreux des enfants concernés (voir **Quota** ci-dessus) ; donnez-lui
un `quota_minutes` pour fixer sa propre limite. Le moteur ne devine pas que `tv_adguard` va avec `tv` : on les regroupe dans le panneau
« Règles », onglet Appareils, avec **Déplacer vers…** sur l'appareil physique. La ressource
ainsi vidée est supprimée à l'enregistrement, avec ses autorisations en cours et le temps du jour
qui lui étaient rattachés ; les modes qui la citent sont retirés.

### Charger la configuration

- Service **`parental_control.importer_configuration`** (réservé aux administrateurs) avec
  le champ `config` contenant l'objet JSON. Outils de développement, Actions, mode YAML :

  ```yaml
  action: parental_control.importer_configuration
  data:
    config:
      version: 2
      kids: []
      resources: []
  ```

- Ou la commande WebSocket **`parental_control/config/set`** (`{"type": "parental_control/config/set", "config": {...}}`,
  administrateur seulement). `parental_control/config/get` renvoie la configuration courante
  (administrateur seulement aussi : elle contient les identifiants d'appareils et les cibles de
  notification), `parental_control/state` l'état courant et `parental_control/state/subscribe`
  s'abonne aux changements (pour les cartes).

Une configuration invalide est refusée en citant le chemin fautif (par exemple
`kids[0].profiles.ecole.segments[2].start : heure invalide`). Si la configuration
enregistrée est invalide au démarrage, le moteur reste inactif : l'erreur est journalisée et
une notification persistante « Contrôle parental : configuration invalide, moteur inactif »
s'affiche (elle disparaît au chargement d'une configuration valide).

Quand une configuration retire un enfant ou une ressource, les décisions qui les visaient
(exceptions, minuteurs, bonus, devoirs) sont supprimées.

## Services

Le « code » est le code parent. Un utilisateur **administrateur**, ou un appel **sans
utilisateur** (automatisation, script), n'a pas besoin de le fournir. Un utilisateur non
administrateur doit le passer dans le champ `code` pour les actions qui débloquent.

| Service | Champs | Code exigé (non admin) |
|---|---|---|
| `parental_control.devoirs_termines` | `kid_id` | oui |
| `parental_control.ajouter_bonus` | `minutes` (1 à 240) et exactement un de `kid_id` ou `resource_id` | oui |
| `parental_control.exception` | `open` (obligatoire), `resource_id`, `kid_id`, `service`, `minutes` (1 à 240) | oui si `open: true`, non pour une fermeture |
| `parental_control.annuler_exception` | `exception_id` | oui si l'exception annulée est une fermeture (annuler rouvre) |
| `parental_control.demarrer_minuteur` | `kid_id`, `minutes` (1 à 240) | oui |
| `parental_control.arreter_minuteur` | `kid_id` | non |
| `parental_control.pause` | `active` | oui pour lever la pause (`active: false`), non pour la poser |
| `parental_control.importer_configuration` | `config` | réservé aux administrateurs |

Précisions :

- `ajouter_bonus` sur un `kid_id` ajoute des minutes au quota de l'enfant du jour ; sur une
  `resource_id` avec un lecteur ou un interrupteur, au quota de la ressource ; sur une ressource
  `nintendo`, accorde du temps de jeu à la console. Pas de bonus pour AdGuard.
- `exception` sans `service` exige un `resource_id` (cible précise). Avec `service`, la cible
  est un service AdGuard, pour une ressource, pour toutes les ressources d'un enfant ou pour
  toutes. Une exception sur la Switch est refusée (« Pour la Switch, utilisez
  ajouter_bonus »). Sans `minutes`, l'exception dure jusqu'au prochain changement de règle ; avec
  `minutes`, pour cette durée. Le service retourne `{"id": "..."}` quand on demande la
  réponse (`response_variable`) : c'est l'`exception_id` à passer à `annuler_exception`.
- Les exceptions en cours sont listées dans les attributs du capteur de statut.

## Entités

Chaque enfant, chaque ressource et la pause générale sont des appareils (type « service »).

| Entité | Détail |
|---|---|
| `sensor` Statut, par enfant | États : `autorise`, `bloque`, `attente_devoirs`, `attente_minuteur`, `quota_epuise`, `sur_demande`, `pause`. Les détails de l'instantané (type de journée, segment, fin de plage, temps restant, exceptions) sont en attributs. |
| `button` Devoirs terminés, par enfant | Équivaut au service `devoirs_termines`, pour un administrateur seulement : un bouton ne transmet pas de code, il est donc refusé à un non-administrateur (utiliser le service avec `code`). |
| `binary_sensor` Autorisée, par ressource | Ouverte selon la règle. Pour AdGuard, les services bloqués sont en attribut. |
| `sensor` Temps utilisé / Temps restant, par ressource | Minutes, seulement pour les appareils avec un lecteur, un interrupteur ou une console Nintendo. |
| `switch` Pause générale | Ferme toutes les ressources (sur AdGuard, les services de loisirs) et remet la limite du jour Nintendo à 0. N'importe qui peut la poser ; l'éteindre est refusé à un non-administrateur (pas de code possible sur un interrupteur : utiliser le service `pause` avec `code`). |

Les identifiants d'entités sont ceux que Home Assistant génère à partir des noms (par
exemple `sensor.hugo_statut` si l'appareil s'appelle « Hugo »).

### Événement `parental_control_warning`

Émis avant une fermeture prévue, au préavis du segment (`warn_minutes`, 5 min par défaut,
le plus petit des propriétaires pour une ressource) :

```yaml
event_type: parental_control_warning
data:
  target: "kid:hugo"        # ou "resource:tv", ou "service:iphone_hugo:youtube"
  closes_at: "2026-10-29T19:00:00-04:00"
  message: "Hugo : fin des écrans dans 5 min"
```

Une cible `service:<ressource>:<service>` signale un service AdGuard débloqué (par exemple
ouvert par exception) qui va être rebloqué alors que la ressource reste fermée ; message :
« youtube sur iPhone Hugo : coupure dans 5 min ».

Pour un enfant ou un service, le message est aussi envoyé aux services de `notify` ; les
messages d'un même instant de fermeture sont regroupés en une seule notification. Pour une
ressource, il est envoyé par son `notify_service` s'il est défini.

## Cartes

L'intégration charge ses cartes toute seule dans le tableau de bord (aucune ressource à
ajouter) ; elles apparaissent dans le sélecteur de cartes, sous « Contrôle parental ».
Elles lisent l'état du moteur en direct et n'appellent que les services `parental_control.*`.
`resource` est l'`id` d'une ressource de la configuration JSON. Chaque carte a un éditeur
visuel (bouton « Modifier » de la carte) : l'appareil et les enfants se choisissent dans des
listes tirées des règles, et les options (nom, icône, titre, minutes bonus) se remplissent sans
YAML ; « Afficher l'éditeur de code » reste disponible. Après une mise à jour,
redémarrez Home Assistant : l'adresse des cartes change avec leur contenu, ce qui évite qu'un
navigateur garde une ancienne version.

| Carte | Rôle | Configuration minimale |
|---|---|---|
| `parental-resource-card` | Un appareil : état, autorisations en cours (✕ pour annuler), « Autoriser… » et « Arrêter ». Pour une Switch : pilules bonus à la place. Appareil AdGuard : ses services en bascules (vert débloqué, gris bloqué). | `resource: tv` |
| `parental-timeline-card` | La frise de la journée de chaque enfant. | `type: custom:parental-timeline-card` ; `kids: [hugo]` limite aux enfants listés |
| `parental-switch-card` | Une console Nintendo : jauge du temps restant, temps utilisé, état de la règle et bonus. Complète l'intégration Nintendo officielle. | `resource: switch` |

```yaml
type: custom:parental-resource-card
resource: tv
services: [youtube, netflix]  # optionnel : services affichés (tous par défaut)
show_services: false          # optionnel : masque les bascules de services
```

**Bascules de services.** Toucher un service bloqué l'autorise jusqu'au prochain changement de
plage (un compte non administrateur saisit le code et peut choisir une durée) ; toucher un service
débloqué le bloque, sans code. Les cartes suivent le thème clair ou sombre de Home Assistant.

```yaml
type: custom:parental-switch-card
resource: switch
title: Nintendo Switch        # optionnel
bonus_minutes: [15, 30, 60]   # optionnel
```

**Le code parent.** Un compte non administrateur doit saisir le code (petit cadenas sur la
pilule) pour **autoriser** et pour les **bonus**. Il est saisi sur un pavé numérique tactile (pas de clavier
natif qui recouvre l'écran ; le clavier physique marche aussi), envoyé avec
l'appel et oublié ; il n'est jamais stocké dans une carte ni dans la configuration du
tableau de bord. « Arrêter » et ✕ partent sans code, après une confirmation en deux appuis.

## Panneau « Règles »

L'intégration ajoute un panneau **Règles** dans la barre latérale (administrateurs seulement) pour
modifier la configuration sans écrire de JSON : enfants et frises par type de jour (segments,
quotas, avertissements), loisirs, mode par appareil, appareils logiques en arbre (appareils
physiques, puis intégrations : lecteur, clients AdGuard, console Nintendo, avec une pastille qui
dit si l'entité ou l'appareil existe dans Home Assistant) et leurs quotas, loisirs par défaut, mots du calendrier scolaire et notifications. Les
modifications restent en brouillon jusqu'à « Enregistrer » ; le moteur valide et, en cas d'erreur,
indique le champ fautif. Un onglet JSON garde l'accès à la configuration brute.

## Mode simulation

Le mode simulation fait tourner tout le moteur (états, frises, exceptions, avertissements) sans
piloter aucun appareil : rien n'est bloqué, éteint ni limité. Il sert à valider les règles avant de
les laisser agir.

- **Interrupteur** `switch` « Simulation », à côté de « Pause ». Les cartes affichent une pastille
  « SIMULATION » dans leur en-tête et le panneau « Règles » un bandeau en tête.
- **Journal de bord.** Chaque action que le moteur aurait faite (fermer une ressource, rebloquer un
  service, remettre la limite Nintendo à 0…) y est inscrite à la place de l'appel réel.
- **Installations.** Une nouvelle installation démarre en simulation ; une installation existante
  reste en mode réel.
- **Code parent.** **Activer** la simulation relâche tous les appareils : un compte non
  administrateur doit donc fournir le code parent. Un interrupteur ne transmet pas de code : il est
  refusé à un non-administrateur, comme pour l'arrêt de la pause. La désactiver n'en demande pas.
- **Notifications.** Les notifications aux parents partent toujours, préfixées « [Simulation] ».
- **Sortie de simulation.** En la quittant, le moteur réapplique tout de suite l'état voulu à
  chaque appareil.

## Tablette murale

1. Créer un **utilisateur Home Assistant dédié, non administrateur**, pour la tablette.
2. Y afficher le tableau de bord. Les [cartes](#cartes) demandent le code pour débloquer ; le bouton « Devoirs
   terminés » et l'arrêt de la pause restent refusés sur la tablette : les parents les
   utilisent depuis leur téléphone (utilisateur administrateur).
3. Les actions qui débloquent demandent le **code parent** dans le champ `code` d'un appel
   de service. **N'écrivez jamais le code** dans une action `perform-action` d'un tableau de
   bord ni dans une automatisation ou un script qu'un non-administrateur peut déclencher.
4. **Masquez à l'utilisateur de la tablette les entités brutes** AdGuard
   (appareils `adguard_clients`), Nintendo et télé : il pourrait les manipuler directement. Le
   moteur corrige une dérive (service AdGuard débloqué pendant une fermeture, télé rallumée, limite
   Nintendo relevée), mais pas avant qu'elle ait eu lieu.
5. **Verrouillage** : après 5 codes faux consécutifs, les essais sont refusés 60 s ; chaque
   échec suivant double la durée, jusqu'à 15 minutes. Un bon code remet le compteur à zéro.
   Le compteur est par utilisateur et **en mémoire** : un redémarrage de Home Assistant le
   remet à zéro.

## Limites connues

- **Appels sans utilisateur.** Une automatisation ou un script appelle les services sans
  utilisateur : le code n'est alors pas demandé. Ne créez pas d'automatisation ou de script qui
  débloque quelque chose et qu'un utilisateur non administrateur peut déclencher
  (`automation.trigger`, `script.turn_on`, etc.), ce serait un contournement du code.
- **AdGuard.** L'appareil vient de la configuration (`device_id`) ; son capteur « Services
  bloqués » est retrouvé au démarrage du moteur. Un capteur absent ou indisponible est signalé
  dans les journaux et ignoré : **les services ne sont alors pas bloqués sur cet appareil**.
  Un client réglé sur « Utiliser les services bloqués globaux » n'applique pas sa propre liste :
  le moteur l'écrit quand même et prévient dans les journaux ; désactivez ce réglage sur les
  appareils des enfants. Un appareil créé après le démarrage du moteur demande de recharger
  l'intégration.
- **Retrait d'un loisir.** Retirer un service de `default_leisure` (ou via `leisure_remove`)
  pendant qu'il est bloqué le laisse bloqué : le moteur ne le gère plus.
- **Nintendo.** Le moteur ne coupe jamais une partie en cours : il n'accorde que du temps
  bonus (tranches de 30 minutes par appel, espacées de 5 s) et garde la limite du jour à 0.
  Une limite relevée (par exemple depuis la tablette) est remise à 0. La pause générale remet
  aussi la limite à 0 ; on **n'a pas vérifié sur la vraie console** si cela coupe un bonus
  déjà accordé. L'action `nintendo_parental_controls.add_bonus_time` appelée directement ne
  peut pas être contrôlée par le moteur (il ne retire pas un bonus) : masquez-la et ne
  laissez pas l'utilisateur de la tablette l'appeler.
- **Statut de l'enfant.** Le capteur de statut suit la frise : il ne reflète pas les
  exceptions manuelles (une ressource ouverte par exception n'y change rien).
- **Minuteur après minuit.** Un minuteur qui franchit minuit est décompté entièrement sur le
  jour où il a démarré.
- **Pause et exceptions.** Pendant la pause, les exceptions « jusqu'au prochain changement de
  règle » n'échoient pas.
- **Redémarrage et exceptions.** Un service hors loisirs bloqué par une exception reste
  bloqué après un redémarrage de Home Assistant (échec du côté fermé), jusqu'à ce qu'un parent
  le débloque.
- **Précision de la télé.** L'usage est compté une fois par minute (précision de ± 1 minute).
- **Le code est une chaîne.** Envoyez-le entre guillemets : en YAML, `code: 0123` devient
  l'entier `123`.

## Développement

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/pytest
```
