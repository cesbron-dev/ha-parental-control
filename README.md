# Contrôle parental pour Home Assistant

Intégration Home Assistant (HACS) de contrôle parental. Chaque enfant a une frise
horaire par type de journée (école, fin de semaine, congé pédagogique, vacances).
Le moteur l'applique en continu aux téléviseurs (`media_player`), aux services
AdGuard Home (via [ha-adguard-clients](https://github.com/cesbron-dev/ha-adguard-clients)) et aux consoles Nintendo Switch. Il gère aussi
les devoirs, les quotas, les minuteurs, les bonus, les exceptions manuelles et une
pause générale.

Le projet comporte trois pièces :

1. **le moteur** (ce dépôt) : intégration, services, entités, API WebSocket ;
2. **les cartes du tableau de bord** : à venir ;
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
  "version": 1,                       // seule valeur acceptée
  "default_leisure": ["youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch"],
  "calendar_map": {                   // mot (sans accent ni casse) -> type de journée
    "pédagogique": "conge_peda",
    "vacances": "vacances",
    "relâche": "vacances"
  },
  "notify": ["notify.mobile_app_iphone_de_olivier"],   // services notify des parents
  "kids": [
    {
      "id": "gabin",                  // identifiant unique, utilisé par les services
      "name": "Gabin",
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
  "resources": [
    {
      "id": "tv",
      "name": "Télé salon",
      "kind": "media_player",
      "owners": ["gabin"],
      "entity_id": "media_player.tv_salon",
      "notify_service": null,         // optionnel : "notify.xxx" pour avertir sur l'appareil
      "quota_minutes": { "fin_de_semaine": 180 }
    },
    {
      "id": "iphone_gabin",
      "name": "iPhone Gabin",
      "kind": "adguard_services",
      "owners": ["gabin"],
      "device_id": "1ef9511faa6db9c5969524170a8fe8e3"  // appareil du client (adguard_clients)
    },
    {
      "id": "switch",
      "name": "Switch",
      "kind": "nintendo",
      "owners": ["gabin"],
      "device_id": "b64d274dc045916f9a6de862a104fbb5",
      "limit_entity": "number.switch_papa_temps_d_ecran_max_aujourd_hui",
      "remaining_entity": "sensor.switch_papa_temps_d_ecran_restant",
      "used_entity": "sensor.switch_papa_temps_d_ecran_utilise"
    }
  ]
}
```

### Les clés

**Racine**

| Clé | Rôle |
|---|---|
| `version` | `1` (défaut). |
| `default_leisure` | Services AdGuard considérés comme des loisirs (ce sont eux que le moteur bloque et débloque). Défaut : `youtube`, `roblox`, `tiktok`, `netflix`, `disneyplus`, `twitch`. |
| `calendar_map` | Associe un mot cherché dans le titre des événements « journée entière » du calendrier de l'enfant à un type de journée. Comparaison sans accent ni casse, par inclusion. |
| `notify` | Services `notify.*` des parents : avertissements de fin de plage d'un enfant et de re-blocage d'un service AdGuard ouvert par exception. |
| `kids` | Liste des enfants. |
| `resources` | Liste des appareils contrôlés. |

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
| `quota` | Autorisé dans la limite du budget. Pour l'enfant : il faut démarrer un minuteur (`demarrer_minuteur`), le temps du minuteur est décompté du `quota_minutes` du profil ; les ressources AdGuard ne s'ouvrent que pendant ce minuteur. Seule une ressource `media_player` (TV) a son propre budget : le `quota_minutes` de la ressource, décompté par l'usage réel. Sans quota défini : illimité. La Switch n'a pas de quota côté moteur : on lui accorde du temps avec `ajouter_bonus` (`resource_id: switch`). |
| `sur_demande` | Bloqué jusqu'à ce qu'un parent ouvre (service `exception` avec `open: true`) ; statut « sur demande ». Pour la Switch, pas d'exception : `ajouter_bonus` avec `resource_id: switch`. |

**Type de journée.** Le calendrier de l'enfant fixe le type via `calendar_map`. Priorité en
cas de recoupement : `vacances`, puis `conge_peda`, puis `ecole` / `fin_de_semaine`. Sans
événement reconnu : `ecole` du lundi au vendredi, `fin_de_semaine` samedi et dimanche.
Si le profil `conge_peda` ou `vacances` n'existe pas, c'est le profil `fin_de_semaine` qui
s'applique (et, pour une ressource, son `quota_minutes` de `fin_de_semaine`).

**Ressource (`resources[]`)**

Clés communes : `id`, `name`, `kind`, `owners` (liste d'`id` d'enfants, qui doivent exister)
et `quota_minutes` (objet optionnel `{ "<type de journée>": minutes }`).

| `kind` | Clés propres | Remarques |
|---|---|---|
| `media_player` | `entity_id` (obligatoire), `notify_service` (optionnel) | Éteinte quand la règle est fermée. Temps d'usage compté, `quota_minutes` applicable. |
| `adguard_services` | `device_id` (obligatoire) | Appareil d'un client persistant de l'intégration `adguard_clients`. Le moteur lit l'attribut `services` de son capteur « Services bloqués » et écrit par `adguard_clients.set_blocked_services` (une écriture par décision). Seuls les services de loisirs sont gérés. |
| `nintendo` | `device_id`, `limit_entity`, `remaining_entity`, `used_entity` | Les quatre sont obligatoires ; les trois entités sont celles de l'intégration Nintendo (limite du jour en `number`, temps restant et utilisé en `sensor`). La limite du jour doit rester à 0 : le temps s'accorde par bonus. |

### Charger la configuration

- Service **`parental_control.importer_configuration`** (réservé aux administrateurs) avec
  le champ `config` contenant l'objet JSON. Outils de développement, Actions, mode YAML :

  ```yaml
  action: parental_control.importer_configuration
  data:
    config:
      version: 1
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
  `resource_id` de type `media_player`, au quota de la ressource ; sur une ressource
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
| `sensor` Temps utilisé / Temps restant, par ressource | Minutes, seulement pour les ressources `media_player` et `nintendo`. |
| `switch` Pause générale | Ferme toutes les ressources (sur AdGuard, les services de loisirs) et remet la limite du jour Nintendo à 0. N'importe qui peut la poser ; l'éteindre est refusé à un non-administrateur (pas de code possible sur un interrupteur : utiliser le service `pause` avec `code`). |

Les identifiants d'entités sont ceux que Home Assistant génère à partir des noms (par
exemple `sensor.gabin_statut` si l'appareil s'appelle « Gabin »).

### Événement `parental_control_warning`

Émis avant une fermeture prévue, au préavis du segment (`warn_minutes`, 5 min par défaut,
le plus petit des propriétaires pour une ressource) :

```yaml
event_type: parental_control_warning
data:
  target: "kid:gabin"        # ou "resource:tv", ou "service:iphone_gabin:youtube"
  closes_at: "2026-10-29T19:00:00-04:00"
  message: "Gabin : fin des écrans dans 5 min"
```

Une cible `service:<ressource>:<service>` signale un service AdGuard débloqué (par exemple
ouvert par exception) qui va être rebloqué alors que la ressource reste fermée ; message :
« youtube sur iPhone Gabin : coupure dans 5 min ».

Pour un enfant ou un service, le message est aussi envoyé aux services de `notify` ; les
messages d'un même instant de fermeture sont regroupés en une seule notification. Pour une
ressource, il est envoyé par son `notify_service` s'il est défini.

## Tablette murale

1. Créer un **utilisateur Home Assistant dédié, non administrateur**, pour la tablette.
2. Y afficher le tableau de bord. Les cartes arriveront plus tard ; **en attendant, les
   parents débloquent depuis leur téléphone (utilisateur administrateur)**. Sur la tablette,
   le bouton « Devoirs terminés » et l'arrêt de la pause sont refusés.
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
