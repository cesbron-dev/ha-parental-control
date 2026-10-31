# Contrôle parental — cartes Lovelace et dashboard tablette (pièce 2)

## 1. Intention

Le moteur `parental_control` (pièce 1) décide et applique les règles. Il manque de quoi **voir** où on en
est et **agir** depuis Home Assistant sans passer par les entités brutes (AdGuard, TV, Nintendo) :

- une carte par appareil avec son état et le temps restant quand un service ou l'appareil a été autorisé
  pour une durée ;
- une vue de l'avancement des règles de la journée ;
- un dashboard sur la tablette du salon, consultable par tout le monde, où seul un parent (avec le code)
  peut agir.

Les cartes remplacent les cartes inline de l'instance de test (`controle-parental-tv-card`,
`controle-parental-switch-card`) et les tuiles AdGuard de l'ancien pont MQTT.

## 2. Objectifs, non-objectifs, anti-objectifs

**Objectifs**
- Trois cartes : **appareil** (générique), **frise de la journée**, **Switch** (complément Nintendo).
- Cartes **agnostiques** : elles ne lisent que le moteur. Le type d'appareil (AdGuard, TV, Nintendo…) vient
  de la config du moteur ; aucune carte ne lit ni n'écrit d'entité AdGuard ou TV. Seule la carte Switch lit
  en plus les entités de l'intégration Nintendo officielle (c'est un complément de cette intégration).
- Un dashboard tablette sur un compte non admin ; le dashboard « Contrôle parental » actuel réservé aux admins.

**Non-objectifs**
- Le panneau d'édition de la configuration (pièce 3).
- Une carte par enfant ou une vue « liste par enfant » (proposées, non retenues).

**Anti-objectifs** (échec même si « ça marche »)
- Un code parent stocké dans une carte, une config de dashboard ou une action.
- Un enfant qui **ouvre** quelque chose (autorisation, bonus, devoirs finis, minuteur, fin de pause) depuis
  la tablette sans le code.
- Une carte qui contourne le moteur (appel direct à AdGuard, `media_player.turn_off`, Nintendo
  `add_bonus_time`…) : le moteur reprendrait la main et les deux se contrediraient.

## 3. Contraintes

- Sur un compte non admin, toute action **qui ouvre** (autoriser, bonus, devoirs finis, démarrer un
  minuteur, lever la pause) demande le code parent. Les actions **restrictives** (« Arrêter », ✕ sur une
  autorisation, arrêter un minuteur, mettre en pause) restent sans code : ce sont des restrictions,
  acceptées par Olivier. Le moteur vérifie déjà le code (paramètre `code` des services, contrôlé quand `context.user_id` n'est pas
  admin) ; la carte demande le code au moment d'agir et l'oublie aussitôt (pas de mémorisation, même en
  session).
- Sur un compte admin, pas de code (le moteur ne le demande pas).
- Textes de l'interface en français.
- Style « verre » sombre de l'instance de test (cf. `BASE_CSS` des cartes inline actuelles : fond
  dégradé translucide, bord clair, coins 18 px, titres en capitales espacées, pilules à bord coloré,
  confirmation « Confirmer ? » en deux appuis sous 3 s).
- Tablette en paysage d'abord ; lisible sur téléphone (pas de défilement horizontal).

## 4. Ce qui a été décidé

### 4.1 Carte appareil (`custom:parental-resource-card`)

Une carte par ressource du moteur. Config : `resource: <id>` (obligatoire), `name`/`icon` (facultatifs,
sinon ceux de la config du moteur ou une icône par type).

Contenu (version « compacte » retenue) :
- en-tête : icône, nom, enfants concernés, badge d'état (`Autorisé` vert / `Bloqué` rouge / `Pause`…) ;
- ligne de raison : raison du moteur et prochain changement (« Soirée · reprise à 7:00 »,
  « Exception · jusqu'à 22:45 (reste 53 min) ») ;
- **pilules des autorisations en cours** : une par exception ouverte qui touche cette ressource
  (appareil entier ou service), avec le temps restant en direct ; ✕ annule l'exception
  (`annuler_exception`) ;
- si la ressource a un quota du jour (temps utilisé/restant non nul) : barre « utilisé / autorisé » comme
  l'ancienne carte Télé ;
- **« Autoriser… »** : fenêtre commune (cf. 4.4) ;
- **« Arrêter »** (rouge, confirmation) : ferme la ressource jusqu'au prochain changement de règle —
  `parental_control.exception {resource_id, open: false}` sans durée. Le moteur fait le reste : la TV
  s'éteint, un client AdGuard voit tous ses **services de loisirs** (ceux gérés par le moteur, pas toute la
  liste AdGuard) bloqués d'un coup.

### 4.2 Frise de la journée (`custom:parental-timeline-card`)

Une barre par enfant de 0 h à 24 h pour aujourd'hui, segments colorés par type (libre, après devoirs,
bloqué, école/nuit), trait « maintenant », graduation 0/6/12/18/24 h, légende. En-tête : « Aujourd'hui »,
type de jour, heure. Pour chaque enfant : nom, statut et prochaine étape (« bloqué — reprise 7:00 »,
« attente devoirs — libre après « devoirs finis » »). Les exceptions actives de l'enfant (ou de ses
ressources) apparaissent en hachuré bleu sur la plage qu'elles couvrent. Toucher une barre ouvre le détail
de la règle et des exceptions de l'enfant. Config : facultative (`kids: [ids]` pour restreindre).

### 4.3 Carte Switch (`custom:parental-switch-card`)

Reprend la carte `controle-parental-switch-card` de l'instance de test : jauge en arc (restant/accordé),
bloc « Temps de jeu », temps utilisé, pilules bonus `+15m +30m +1h`. « Accordé » = utilisé + restant
(comme la carte actuelle, lu sur les entités Nintendo). Différences :
- les bonus passent par `parental_control.ajouter_bonus {resource_id, minutes}` (plus par le script
  `switch_ajouter_bonus` ni par Nintendo directement) ;
- une ligne affiche l'état de la règle du moteur pour cette ressource (« autorisée jusqu'à 20:00 ») ;
- **ni « Arrêter » ni « Autoriser… »** : sur la Switch la limite Nintendo reste à 0 et le temps n'existe
  que par les bonus ; le moteur ne peut ni couper une partie ni retirer un bonus. La carte ne propose que ce
  qui marche vraiment : les pilules bonus remplacent « Autoriser… ».
Config : `resource: <id>` ; les entités Nintendo (temps utilisé/restant) sont retrouvées à partir de
l'appareil Nintendo référencé par la ressource du moteur.

### 4.4 Fenêtre « Autoriser… » et saisie du code

- **Quoi** : « Tout l'appareil » + un choix par service de loisirs de la ressource (AdGuard seulement ; pour
  une TV, seul « Tout l'appareil »). Une ressource Nintendo n'a pas cette fenêtre : la carte appareil
  utilisée sur une Switch applique les mêmes règles que la carte Switch (bonus à la place d'« Autoriser… »,
  pas d'« Arrêter »).
- **Pendant** : 15 min, 30 min, 1 h, 2 h, « jusqu'au prochain changement » (sans durée).
- Appel : `parental_control.exception {resource_id, open: true, service?, minutes?}`.
- **Code** : si l'utilisateur n'est pas admin, toute action qui ouvre (Autoriser, bonus) ouvre la saisie du
  code avant l'appel ; un code faux affiche l'erreur renvoyée par le moteur. Sur un compte non admin ces
  boutons portent un petit cadenas. « Arrêter » et ✕ s'exécutent sans code (confirmation seulement).

### 4.5 Changement du moteur : « Arrêter » l'emporte sur les services autorisés

Aujourd'hui le moteur applique les exceptions de ressource puis les exceptions de service
(`_apply_exceptions`, `core/evaluator.py`) : fermer un iPad où YouTube est autorisé 1 h laisse YouTube
ouvert. Règle voulue : **une exception de fermeture de ressource l'emporte, pour cette ressource, sur
toutes les exceptions de service plus anciennes qui s'y appliquent** (au sens de
`_service_exception_applies` : ciblées sur la ressource, sur un de ses enfants ou sur tout le monde).
Mon choix : c'est une règle d'évaluation (« la plus récente gagne » étendue aux services), pas une
suppression — une exception de service visant un enfant reste valable sur ses autres appareils. Elle vaut
pour tout appelant (carte, automatisation, service). Le changement vit dans le moteur.

### 4.6 Code parent côté moteur

Inchangé : le moteur demande déjà le code (compte non admin) pour les actions qui ouvrent et pas pour
`exception` avec `open: false`, `annuler_exception` d'une autorisation ni `arreter_minuteur` — Olivier
valide ce comportement (actions restrictives). La carte suit le moteur ; le moteur fait foi.

### 4.7 Ce que les cartes lisent

- État : souscription WebSocket existante `parental_control/state/subscribe` (enfants, ressources,
  exceptions, pause, fermetures à venir).
- `parental_control/config/get` est réservé aux admins ; la tablette est non admin. Le moteur ajoute donc
  une **lecture d'affichage non admin**, sans donnée sensible (ni code, ni calendriers) : enfants (id, nom,
  emoji/couleur), ressources (id, nom, type, propriétaires, liste de services de loisirs, appareil
  Nintendo le cas échéant, avec les `entity_id` temps utilisé/restant) et **frise du jour par enfant**
  (segments début/fin/type, calculés par le moteur avec sa propre logique `_timeline` — la carte ne
  recalcule aucune règle). Mes choix : types de segment bruts du profil de l'enfant ; heures en ISO 8601
  avec fuseau ; pour chaque exception active, une plage de fin calculée par le moteur (`until`, ou à défaut
  le prochain changement de règle qui la fera échoir). Les libellés d'attente viennent du statut d'enfant
  existant.

### 4.8 Livraison

- Les cartes sont livrées **dans l'intégration** `parental_control` : fichiers JS servis par l'intégration
  et enregistrés automatiquement comme ressource Lovelace (pas d'installation HACS séparée, toujours à la
  version du moteur).
- JavaScript sans étape de compilation (web components natifs, comme les cartes actuelles).
- Les cartes sont déclarées dans `window.customCards` (sélecteur de cartes de HA).

### 4.9 Dashboards

- Livrable de configuration, pas de code : les dashboards sont créés sur l'instance de test via l'API HA
  (pas par l'intégration). La prod n'est pas visée. Prérequis : un compte non admin pour la tablette
  (à créer par Olivier s'il n'existe pas).
- **Tablette** : nouveau dashboard pour tout le monde (non admin) : frise en haut, une carte appareil par
  ressource, carte Switch.
- **« Contrôle parental »** existant : passe en `require_admin`.
- Sur l'instance de test, retirer ensuite la ressource inline et la vue « Télé (proposition) » quand les
  nouvelles cartes la remplacent.

## 5. Laissé au constructeur

- Noms internes des fichiers, structure du JS, découpage en modules.
- Forme exacte de la lecture d'affichage (nouvelle commande WebSocket ou extension de `state/subscribe`),
  tant qu'elle est non admin, sans donnée sensible et à jour quand la config change.
- Libellés des services (id AdGuard → nom lisible : table simple, id capitalisé à défaut).
- Comportement visuel de la fenêtre et du détail de la frise (dialogue HA natif ou carte en surimpression).

## 6. Mes choix (à vérifier par Olivier)

- Barre de quota sur la carte appareil quand la ressource a un quota.
- Exceptions en hachuré bleu sur la frise ; toucher une barre → détail.
- Cadenas sur les boutons qui demandent le code, pour un compte non admin.
- Code jamais mémorisé, même le temps d'une session.
- Cartes livrées dans l'intégration plutôt qu'en dépôt HACS séparé.
