# ha-parental-control — moteur de règles (conception)

Date : 2026-10-28 · Statut : validée
Repo cible : `ha-parental-control` (nouveau, unique). Ce document sera déplacé dans ce repo à sa création.

## 1. Intention

Remplacer le bricolage actuel de l'instance de test (helpers `tele_*`, scripts `mode_*`, cartes inline
`controle-parental-tv-card` / `controle-parental-switch-card`, automatisations à la main) par une
**intégration HACS** qui applique des règles de contrôle parental **par enfant** sur des **ressources
hétérogènes** (TV, console Switch, services filtrés par AdGuard, et à terme un firewall).

Le pourquoi : la famille (Maël au secondaire, Gabin et Léo au primaire) a une journée structurée
(fenêtres après l'école, devoirs, souper) que l'on veut appliquer automatiquement, avec des exceptions
décidées par un parent, sans réécrire d'automatisations à chaque changement d'horaire.

Le projet complet a trois morceaux, construits dans cet ordre :
1. **Moteur de règles** (ce document) — intégration Python.
2. Cartes d'affichage (carte enfant, vue globale, tuiles ressources style TV/Switch actuelles, grille AdGuard).
3. Panneau d'édition visuel (frise de la journée), servi par l'intégration.

Les morceaux 2 et 3 sont hors périmètre ici, mais le moteur doit exposer tout ce dont ils auront besoin.

## 2. Objectifs

- Calculer à tout instant, pour chaque enfant et chaque ressource, si l'accès est **autorisé**, **pourquoi**,
  **jusqu'à quand**, et le **temps restant** (quota).
- **Appliquer** la décision sur les ressources (couper la TV, bloquer les services loisirs AdGuard, gérer
  la Switch) avec **avertissement 5 min avant** chaque fermeture.
- Offrir des **actions parent** : « devoirs terminés », bonus de temps, exception manuelle (ouvrir/fermer une
  ressource ou un service), avec durée au choix.
- Choisir le **profil du jour** à partir d'un calendrier HA.
- Être **générique** : un type de ressource = un adaptateur qui pilote des entités HA existantes.

## 3. Non-objectifs

- Pas de contrôle des iPhone/iPad au-delà d'AdGuard : le contrôle parental Apple reste hors HA.
- Pas d'appel direct aux API AdGuard / Nintendo / TV : le moteur pilote uniquement des **entités HA**.
- Pas d'interface dans ce morceau (le panneau et les cartes viennent ensuite). La configuration initiale
  doit cependant être possible sans éditer de YAML (voir §9).
- Pas d'identification de qui regarde la TV.

## 4. Anti-objectifs (échec même si « ça marche »)

- Un enfant qui contourne la règle via la tablette murale : toute action qui débloque doit pouvoir exiger un code.
- Une coupure sans avertissement préalable.
- Un redémarrage de HA qui rouvre tout, ou qui fait perdre « devoirs terminés », les bonus ou les exceptions du jour.
- Couper tout Internet : seuls les services de la liste « loisirs » sont bloqués.
- Écraser en silence une décision manuelle d'un parent avant son échéance.

## 5. Modèle

### Enfant
`id`, nom, emoji/couleur (pour les cartes), **calendrier scolaire** (entité `calendar.*`, propre à chaque enfant
car primaire et secondaire n'ont pas les mêmes congés pédagogiques), liste de **ressources** associées,
liste de services loisirs (héritée de la liste par défaut, avec ajouts et retraits).

### Type de jour et profil
Types : `ecole`, `fin_de_semaine`, `conge_peda`, `vacances`.
- Lundi–vendredi = `ecole` par défaut, samedi–dimanche = `fin_de_semaine`.
- Un événement du calendrier de l'enfant **surcharge** le type du jour. Le type est déduit du titre de
  l'événement via une table de correspondance configurable (ex. « Congé pédagogique » → `conge_peda`).
- *(Choix du concepteur)* Seuls les événements **sur la journée entière** comptent : le type de jour est fixé
  pour la journée. Un événement de plusieurs jours (vacances) s'applique à chaque jour couvert, fins de
  semaine comprises. En cas de chevauchement, priorité : `vacances` > `conge_peda` > défaut du jour de semaine.
- Chaque enfant a **un profil par type de jour**.

### Profil = frise de segments
Un profil est une suite de segments couvrant 00:00–24:00. Types de segment :

| Type | Comportement |
|---|---|
| `bloque` | accès fermé |
| `libre` | accès ouvert |
| `apres_devoirs` | fermé jusqu'à l'action parent « devoirs terminés », puis ouvert jusqu'à la fin du segment |
| `quota` | ouvert tant qu'il reste du quota (minutes) pour la journée ; fermé à la fin du segment (heure limite) |
| `sur_demande` | fermé ; ouvert seulement par un bonus/une exception parent |

Chaque segment porte : quota éventuel, délai d'avertissement (défaut 5 min).

**Mode par ressource** *(choix du concepteur)* : dans le profil d'un enfant, chaque ressource est soit
« suit la frise » (défaut), soit dans un mode fixe pour toute la journée (`sur_demande`, `bloque`, `libre`).
La Switch est en `sur_demande` fixe pendant que la TV et les appareils suivent la frise. On garde ainsi
une seule frise par enfant et par type de jour. Le capteur de statut de l'enfant reflète la frise ;
l'état de chaque ressource est exposé à part.

Exemples réels :
- Gabin/Léo, `ecole` : bloqué → 15:25 libre → 16:00 `apres_devoirs` → 19:00 bloqué.
- Maël, `ecole` : bloqué → 16:15 `apres_devoirs` → 19:00 bloqué.
- `fin_de_semaine` : `quota` (ex. 2 h) jusqu'à l'heure limite, puis bloqué.
- Switch : `sur_demande` en permanence.

### Ressource
Une ressource a un **type** (adaptateur) et des entités HA. Elle peut être **partagée** entre plusieurs enfants.
- **Appareils AdGuard** : la configuration AdGuard sera refaite pour avoir **un client par appareil**, chaque
  appareil étant affecté à un enfant. Les noms de clients actuels (`iphone_enfants`, `enfants_ipad`…) vont
  donc changer : le moteur ne doit pas les coder en dur. *(Choix du concepteur)* Le modèle permet quand même
  plusieurs propriétaires par appareil ; dans ce cas, la règle des ressources partagées s'applique.
- **Ressource partagée** (la TV) : autorisée **dès qu'au moins un enfant** y a droit.
- **Quota d'une ressource partagée** : compté sur la ressource elle-même (temps d'allumage de la TV),
  puisqu'on ne sait pas qui regarde. *(Choix du concepteur)* Le quota de la TV est défini **sur la ressource**
  (par type de jour), indépendamment des quotas des enfants. Un bonus accordé « sur la TV » augmente ce budget.
  Un bonus accordé à un enfant augmente le quota de cet enfant.
- **Quota par jour** : un quota est un budget journalier. Plusieurs segments `quota` dans une même journée
  puisent dans le même budget.
- **Quota sur des services non mesurables (AdGuard) = minuteur.** AdGuard sait bloquer mais pas compter.
  Pendant un segment `quota`, les services loisirs de l'enfant restent **bloqués** jusqu'au **démarrage
  d'un minuteur**. Le minuteur débloque les services, décompte le temps écoulé sur le quota de l'enfant, et
  les recoupe à la fin (avertissement 5 min avant), à l'épuisement du quota ou à l'heure limite du
  segment, selon ce qui arrive en premier. **Seul un parent démarre le minuteur** (ex. « 30 minutes »), avec
  code sur la tablette ; il se coupe à la fin, **sans modification possible par les enfants**.
  *(Choix du concepteur)* La durée est plafonnée au quota restant ; un parent peut annuler un minuteur en cours.

### Exceptions et bonus (décisions parent)
- **Devoirs terminés** (par enfant, valable pour la journée).
- **Bonus** : +N minutes de quota, ou ouverture d'un segment `sur_demande` pendant N minutes.
- **Exception manuelle** : ouvrir ou fermer une ressource, ou un service AdGuard précis sur un appareil
  (ou sur tous les appareils d'un enfant, ou de tous les enfants), avec durée **au choix au moment de l'action** :
  - « jusqu'à la prochaine décision de la règle » : le prochain changement de l'état **calculé par la règle**
    pour la cible (pour une ressource partagée, le prochain changement de son état agrégé) ;
  - « pendant N minutes ».
  Une exception active l'emporte sur la règle jusqu'à son échéance. On peut la lister et l'annuler.
- **Pause générale** : ferme tout pour tous, immédiatement, jusqu'à désactivation.

Toutes ces décisions sont **persistées** et survivent à un redémarrage de HA. « Devoirs terminés » et les
bonus de quota expirent à minuit. Une exception avec une durée court jusqu'à son terme, même après minuit.

**Code parent** *(choix du concepteur)* : la tablette murale est connectée avec un utilisateur HA **non
administrateur** dédié. Les services qui débloquent (`devoirs_termines`, `ajouter_bonus`, `exception` qui
ouvre, désactivation de la pause) exigent un paramètre `code` quand l'utilisateur appelant
(`context.user_id`) n'est pas administrateur. Les cartes demandent ce code. Le code est configuré dans
l'intégration et stocké sous forme hachée. Les actions qui ferment ne demandent jamais de code.
Les comptes parents (téléphones) sont administrateurs et n'ont pas besoin de code.

## 6. Adaptateurs de ressources (v1)

Chaque adaptateur sait : mesurer l'usage (si possible), appliquer `ouvert`/`fermé`, avertir.

| Adaptateur | Entités pilotées (instance de test) | Mesure | Fermer | Avertir |
|---|---|---|---|---|
| `media_player` (TV) | `media_player.tv_salon` | temps à l'état `on`, compté par le moteur | `media_player.turn_off` ; ré-extinction si rallumée pendant la fermeture | notification à l'écran si possible (voir §10) |
| `adguard_services` | switches `switch.adguard_<client>_svc_<service>` du bridge (ON = **bloqué**). Clients : `iphone_enfants`, `enfants_ipad`, `chromebook_mael`, `tv` (instance en sortie du VPN Chromecast) | aucune | passer à ON les switches des services loisirs | — |
| `nintendo` | `number.switch_papa_temps_d_ecran_max_aujourd_hui`, `sensor.switch_papa_temps_d_ecran_restant` / `_utilise`, `sensor.switch_papa_temps_d_ecran_utilise_par_<compte>`, service `nintendo_parental_controls.add_bonus_time` | capteurs Nintendo (y compris par compte enfant, exposés à titre informatif) | rien à faire : la limite du jour reste à 0, le temps n'existe que par les bonus | assuré par la console |

*(Choix du concepteur)* La Switch est **une ressource partagée au niveau de la console** (une seule limite
Nintendo). « Ouvrir » = appeler `add_bonus_time` pour N minutes. Le moteur ne remet jamais la limite à 0
en cours de partie : c'est l'épuisement du bonus qui ferme, avec l'avertissement natif de la console.
La pause générale, elle, pose la limite à 0 (seul cas de coupure sans préavis, voulu).

Contraintes connues de l'adaptateur Nintendo : `add_bonus_time` accepte 30 min max par appel et renvoie un
HTTP 409 si deux appels se suivent trop vite. Il faut découper en tranches de 30 min espacées d'environ 5 s,
comme le fait l'actuel `script.switch_ajouter_bonus`.

Ajouter un type de ressource (firewall, prise connectée…) = écrire un nouvel adaptateur, sans toucher au moteur.

## 7. Comportement du moteur

- Il réévalue la situation à chaque changement de segment, d'exception, de type de jour, et chaque minute
  pour les quotas.
- Il calcule pour chaque enfant : état (`autorise`, `bloque`, `attente_devoirs`, `quota_epuise`, `sur_demande`,
  `pause`, `exception`), raison lisible, prochaine échéance, temps restant.
- Il en déduit l'état de chaque ressource (OU logique pour les ressources partagées) et l'applique via
  l'adaptateur. Il n'envoie des commandes qu'en cas de **changement** (pas de spam d'appels).
- Avant chaque fermeture prévisible (fin de segment, quota bientôt épuisé, fin d'exception), il avertit
  N minutes avant.
- Il est idempotent et se resynchronise au démarrage de HA (réapplique l'état attendu).
- *(Choix du concepteur)* **Le moteur fait foi** sur les entités qu'il contrôle. Un changement fait hors du
  moteur (télécommande, switch AdGuard basculé ailleurs) est **annulé** tant que l'état attendu est
  « fermé ». Quand l'état attendu est « ouvert », il est laissé tel quel. Les décisions parent passent par
  les services du moteur (et donc par les cartes), pas par les entités brutes.
- *(Choix du concepteur)* Avertissement des fermetures AdGuard : événement HA `parental_control_warning`,
  attribut sur le capteur de l'enfant (affiché sur la tablette et les cartes) et notification facultative à
  une liste de cibles `notify.*` configurable (téléphones parents). Pas de notification sur les appareils
  des enfants.

## 8. Ce que le moteur expose (pour les cartes, le panneau et les automatisations)

Entités par enfant : statut (`sensor`, avec attributs raison, échéance, temps restant, type de jour,
segment courant, exceptions actives), bouton « devoirs terminés ».
Entités par ressource : autorisée (`binary_sensor`), temps utilisé et restant (`sensor`).
Entité globale : pause générale (`switch`).

Services HA : `devoirs_termines`, `ajouter_bonus`, `exception` (cible, ouvrir/fermer, durée ou
« jusqu'à la prochaine décision »), `annuler_exception`, `demarrer_minuteur` / `arreter_minuteur`, `pause`.
Une API (WebSocket) pour lire et écrire la configuration complète, utilisée plus tard par le panneau d'édition.

## 9. Configuration

- Installation via HACS, puis ajout de l'intégration par l'UI (config flow).
- La configuration des enfants, profils, ressources et listes de services est stockée par l'intégration
  (stockage HA), pas en YAML. L'éditeur visuel (morceau 3) l'éditera plus tard. **En attendant**, il faut un
  moyen minimal de la saisir : options flow, ou import d'un fichier/JSON via un service. Laissé au constructeur.
- Liste de services loisirs par défaut : YouTube, Roblox, TikTok, Netflix, Disney+, Twitch, etc. Elle est
  ajustable par enfant.

## 10. Mise en place sur l'instance de test

*(Choix du concepteur)* L'intégration **remplace** l'existant, sans import automatique. Le plan prévoit une
étape de bascule : désactiver les scripts `mode_*`, les automatisations télé et `script.switch_ajouter_bonus`
(repris par l'adaptateur Nintendo), puis saisir la configuration dans l'intégration. Les helpers `tele_*`
peuvent rester le temps de comparer, mais rien ne doit les piloter en parallèle du moteur.

## 11. Laissé au constructeur

- Structure interne Python (coordinator, store, découpage des adaptateurs).
- Mécanisme exact d'avertissement sur la TV (notification Android TV / Google TV, `notify.*` disponible ou non).
  À défaut, avertissement via une entité/événement que les cartes et la tablette afficheront.
- Format de stockage et migration de version.
- Tests : logique du moteur testable sans HA (fonctions pures sur « heure + config + décisions → états »).
