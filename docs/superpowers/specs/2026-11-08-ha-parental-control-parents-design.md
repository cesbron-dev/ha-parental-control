# Parents non administrateurs — conception

## Intention

Aujourd'hui, l'intégration ne connaît que deux sortes de comptes : les **administrateurs** Home
Assistant, qui font tout sans code, et **tous les autres**, traités comme des enfants : ils
doivent saisir le code parent pour débloquer, ne voient pas le panneau « Règles » et se voient
proposer « Demander ».

Manou est un parent mais n'est pas administratrice HA (compte créé ainsi exprès sur ha-test).
Sur son iPad personnel, la carte lui affiche le pavé numérique ou « Demander » quand elle veut
autoriser du temps, et le panneau « Règles » lui est fermé. Olivier veut qu'elle agisse en parent
sans lui donner les droits d'administration de tout Home Assistant.

## Décisions d'Olivier

- **Qui est parent :** tout utilisateur HA **propriétaire d'un téléphone de la liste
  `request_notify`** (« Demandes de temps (parents) »). C'est la règle qui décide déjà qui peut
  répondre aux demandes (`request_listener.parent_user_ids`). Pas de liste séparée.
- **Ce qu'un parent non administrateur obtient :** les mêmes droits qu'un administrateur dans
  l'intégration :
  - agir **sans code** (autoriser/exception, bonus, devoirs terminés, minuteur, arrêt de la
    pause, activation de la simulation), et ne plus se voir proposer « Demander » ;
  - **ouvrir et modifier** le panneau « Règles » (y compris l'onglet JSON et la liste
    `request_notify`, donc ajouter ou retirer un parent) ;
  - accéder à l'écran « Demandes » par le bouton du panneau.
- **Barre latérale :** acceptable que l'entrée « Règles » apparaisse aussi chez les enfants
  (HA ne sait pas publier un panneau pour une partie seulement des comptes non admins). Ils n'y
  voient qu'un message « Réservé aux parents ».
- **Appareil de Manou :** iPad personnel, non partagé avec les enfants. Le risque « appareil
  partagé connecté au compte d'un parent » est donc hors sujet pour ce cas.
- **Plus tard :** HA travaille sur des groupes d'utilisateurs. La source « qui est parent » doit
  être isolée pour pouvoir être remplacée par un groupe sans toucher au reste.

## Objectifs

- Un parent non admin n'a plus jamais de pavé numérique ni de « Demander » dans les cartes.
- Un parent non admin ouvre « Règles » et enregistre une configuration.
- Rien ne change pour les enfants ni pour la tablette : code ou « Demander », comme avant.
- Rien ne change pour les administrateurs.

## Non-objectifs

- Pas de liste de parents distincte de `request_notify`.
- Pas de gestion des groupes d'utilisateurs HA (pas encore disponibles) ; seulement un point
  d'entrée unique pour les brancher plus tard.
- Pas de changement des droits des administrateurs ni des automatisations (`user_id` absent →
  pas de code, inchangé).

## Anti-objectifs (échec même si « ça marche »)

- Un compte non parent qui lit ou modifie la configuration, ou débloque sans code, **par un appel
  direct** (WebSocket ou service) — cacher un bouton dans l'interface ne compte pas comme une
  protection : chaque contrôle se fait **côté serveur**.
- La configuration (identifiants d'appareils, cibles de notification) envoyée à un non-parent.
- Un parent qui garde ses droits après le retrait de son téléphone de `request_notify`.

## Comportement attendu

### Qui est parent

`est_parent(user)` = l'utilisateur est administrateur HA, **ou** son `user_id` est dans
`parent_user_ids(hass, config.request_notify)`. Règles existantes conservées :

- appel sans `user_id` (automatisation, système) : traité comme aujourd'hui (pas de code) ;
- deux appareils `mobile_app` de même nom : aucun des deux propriétaires n'est parent par cet
  appareil (règle déjà en place, avertissement déjà journalisé) ;
- configuration absente ou `request_notify` vide : seuls les administrateurs sont parents.

Le statut est évalué **à chaque appel** à partir de la configuration courante : retirer un
téléphone retire le droit immédiatement, sans redémarrage.

### Propriétaire mémorisé (durcissement, décision d'Olivier)

Problème : le nom `notify.mobile_app_<x>` vient du nom de l'appareil, que tout utilisateur
choisit. Si un téléphone de la liste n'existe plus (app réinstallée, appareil supprimé), un
enfant peut enregistrer un appareil sous ce nom et devenir parent.

Règle :

- Chaque téléphone de `request_notify` porte, dans la configuration, l'**utilisateur
  propriétaire mémorisé** au moment où il a été ajouté.
- Ce propriétaire est **déterminé par le serveur** à l'enregistrement de la configuration
  (`config/set`, import), d'après les entrées `mobile_app` du moment ; une valeur envoyée par le
  client n'est jamais crue. Il faut un propriétaire unique (règle des doublons inchangée), sinon
  l'ajout est refusé avec une erreur qui nomme le téléphone.
- Un téléphone déjà présent **garde** son propriétaire mémorisé lors des enregistrements
  suivants ; changer de propriétaire passe par une action explicite dans le panneau
  (« réassocier », ou retirer puis rajouter le téléphone).
- Un utilisateur est reconnu par un téléphone seulement si le propriétaire **actuel** de
  l'appareil de ce nom est **le même** que le propriétaire mémorisé. Sinon ce téléphone ne donne
  aucun droit, et le panneau le signale (« appareil introuvable ou changé de compte »).
- La règle vaut pour **les deux usages** : droits de parent **et** réponse aux demandes (le même
  trou existe déjà pour les réponses).
- **Configuration existante** (téléphones sans propriétaire mémorisé) : au premier chargement
  après la mise à jour, chaque téléphone dont le propriétaire actuel est unique est associé à ce
  propriétaire, une seule fois, avec une ligne de journal ; les autres restent sans propriétaire
  et ne donnent aucun droit jusqu'à ce qu'un parent ou un administrateur les réassocie.
  *(Mon choix : évite de casser les réponses aux demandes en prod à la mise à jour.)*
- Conséquence assumée : après une réinstallation de l'app sur un téléphone, il faut le
  réassocier dans « Règles » (par un administrateur, ou un autre parent).

### Côté serveur

Partout où l'intégration teste aujourd'hui « administrateur », elle teste « parent » :

- `security.check_unlock` : pas de code pour un parent ;
- services réservés aux administrateurs (`importer_configuration`) : ouverts aux parents ;
- entités : bouton « Devoirs terminés », arrêt de la « Pause générale », activation de la
  « Simulation » — utilisables par un parent sans code (elles passent par la même vérification) ;
- WebSocket `config/get`, `config/set`, `services/catalog` : remplacer `require_admin` par un
  contrôle « parent », avec une erreur `unauthorized` pour les autres ;
- écran « Demandes » : inchangé (il utilise déjà `parent_user_ids`), sauf que le bouton
  « Demandes » du panneau devient accessible aux parents non admins puisqu'ils ouvrent le panneau.

### Panneau « Règles »

- Enregistré avec `require_admin=False` : visible dans la barre latérale de tous les comptes.
- Pour un non-parent, le panneau n'affiche que « Réservé aux parents » et n'appelle ni
  `config/get` ni `services/catalog` (et le serveur refuserait de toute façon).
- Pour un parent, comportement identique à celui d'un administrateur aujourd'hui.

### Cartes

Les cartes décident aujourd'hui du pavé et de « Demander » avec `hass.user.is_admin`
(`lib.js : needsCode`, `canRequest`). Elles doivent savoir si **l'utilisateur courant** est
parent. Cette information vient du serveur (la liste `request_notify` et la correspondance
téléphone → utilisateur ne sont pas exposées aux non-parents) et dépend de la connexion :
l'état diffusé à tous ne peut pas la porter tel quel.

- Parent : pas de cadenas, pas de pavé, pas de « Demander ».
- Non-parent : inchangé.
- Si l'information n'est pas encore connue (chargement), la carte se comporte comme pour un
  non-parent ; l'erreur côté serveur reste la vraie protection.

## Contraintes

- Ne pas affaiblir les protections existantes : verrouillage après codes faux, jeton secret des
  notifications, revérification de chaque réponse aux demandes.
- Le format de `request_notify` change (propriétaire mémorisé) : l'ancien format (liste de
  chaînes) doit toujours se charger, via la migration décrite plus haut. La forme exacte du
  nouveau format est laissée au constructeur.
- Tests du durcissement : appareil supprimé puis recréé sous le même nom par un autre compte
  (refusé, pour les droits **et** les réponses), propriétaire envoyé par le client ignoré,
  migration d'une configuration existante.
- Tests : pour chaque point de contrôle serveur, un cas parent non admin (accepté sans code), un
  cas non-parent non admin (refusé ou code exigé), un cas administrateur (inchangé), et le
  retrait d'un téléphone qui retire le droit.
- README à mettre à jour : sections « Le code parent », « Panneau Règles », « Demandes de temps »
  (le passage « parents non administrateurs, le panneau Règles leur est fermé » devient faux) et
  les tableaux qui disent « administrateur seulement ».
- Messages de commit en français.

## Choix faits en rédigeant (à vérifier par Olivier)

- **Répondre aux demandes reste réservé aux propriétaires d'un téléphone listé**, comme
  aujourd'hui : « est parent » (droits dans l'intégration, admins inclus) et « peut répondre à une
  demande » (propriétaire d'un téléphone listé, admins exclus s'ils n'en ont pas) restent deux
  règles distinctes. Un administrateur sans téléphone listé ne gagne pas le droit de répondre.
- **Retrait de son propre téléphone :** l'éditeur avertit (« Vous ne serez plus parent après
  l'enregistrement ») mais n'empêche pas. Un administrateur peut toujours réparer.
- **`importer_configuration` refusé à un non-parent :** garde l'erreur `Unauthorized` actuelle.
- **Cache de l'iPad :** rien à prévoir ; l'URL des fichiers servis contient déjà une version
  calculée à partir de leur contenu (`files_version`).

## Laissé au constructeur

- Comment transmettre « tu es parent » aux cartes : commande WebSocket dédiée par connexion,
  champ ajouté à `state`/`state/subscribe` calculé par connexion, ou autre.
- Nom et emplacement de la fonction « est parent » (un seul point d'entrée, réutilisé partout).
- Libellé et mise en page exacts du message « Réservé aux parents ».
