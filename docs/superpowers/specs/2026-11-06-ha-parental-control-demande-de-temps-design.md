# Contrôle parental — demande de temps

## Intention

Sur un appareil Apple, un enfant bloqué touche « Demander plus de temps » et le parent répond depuis
son téléphone, où qu'il soit. Chez nous, la tablette murale affiche le tableau de bord familial ;
aujourd'hui, toute action qui débloque exige qu'un parent vienne taper le code parental. On veut le
même confort qu'Apple : **un geste pour l'enfant, un geste pour le parent**.

La demande est une **alternative** au code, pas un remplacement : un parent devant la tablette peut
toujours taper le code.

## Décisions d'Olivier

- Toutes les actions protégées par le code sur les cartes peuvent être **demandées** au lieu d'être
  débloquées par le code : autoriser un service ou un appareil, ajouter du bonus (enfant ou Switch),
  valider « Devoirs terminés », lancer le minuteur.
- L'enfant **propose une durée** (celle qu'il choisit déjà dans la fenêtre actuelle) ; le parent peut
  l'accepter telle quelle, en choisir une autre, ou refuser, **directement dans la notification**.
- Les durées offertes au parent sont celles de la fenêtre « Autoriser… » : 15 min, 30 min, 1 h, 2 h et
  « Jusqu'au prochain changement » (fin de la plage en cours) — pas de « toute la journée ».
- « Devoirs terminés » : seulement *Accepter* / *Refuser*.
- Les demandes partent vers une **liste de destinataires à part**, réservée aux parents. La liste
  `notify` existante reste pour les alertes de fermeture, destinées aux enfants (téléphone, télé…).
- Validé tel que proposé :
  - l'enfant indique qui il est sur la tablette partagée quand la carte ne le dit pas déjà ;
  - les deux parents reçoivent la demande ; la **première réponse l'emporte** et la notification
    disparaît chez l'autre ;
  - **une seule demande en attente** par enfant et par action (même cible) ;
  - sans réponse en **15 minutes**, la demande expire ;
  - la tablette montre l'état : *en attente*, *acceptée (ce qui a été accordé)*, *refusée*,
    *pas de réponse* ;
  - seule une réponse venant d'un téléphone de la liste « Demandes » est prise en compte, jamais une
    réponse fabriquée depuis la tablette ;
  - chaque demande et sa réponse sont tracées dans le journal ;
  - la liste « Demandes » se règle dans le panneau, à côté de la liste d'alertes.
- Téléphones : iPhone (application Home Assistant), qui affichent tous les boutons d'action.
- **Un parent n'est pas forcément administrateur** de HA (Olivier l'est, Manou non). Être
  administrateur ne peut donc pas être la condition pour répondre.

## Qui peut répondre

Une réponse n'est acceptée que si **les deux** conditions sont remplies :

1. Elle porte le **jeton aléatoire** de la demande en attente.
2. Son contexte a pour `user_id` le **propriétaire d'un des téléphones de la liste « Demandes »**.
   On le retrouve à partir des services `notify.mobile_app_<appareil>` de la liste : ils mènent à
   l'entrée `mobile_app` de l'appareil, dont les données contiennent l'utilisateur
   (`user_id`).

Un administrateur reste accepté par la condition 2 s'il a un téléphone dans la liste, et seulement
dans ce cas. Le compte de la tablette n'a pas de téléphone dans la liste : même s'il fabrique un
événement avec le bon jeton, la réponse est refusée.

**À vérifier par le constructeur, test à l'appui.** Les événements `mobile_app_notification_action`
reçus par le webhook de l'application doivent porter le contexte de l'utilisateur enregistré
(`registration_context` dans `mobile_app`). Si ce n'est pas le cas, s'arrêter et le signaler avant
d'aller plus loin.

## Parcours

### Sur la tablette (compte non admin)

1. L'enfant touche une action protégée (ex. « Autoriser » YouTube sur la carte Télé). La fenêtre
   actuelle s'ouvre : quoi, pendant combien de temps, pavé du code.
2. La fenêtre offre en plus **« Demander »**, utilisable sans code dès que la durée (si l'action en a
   une) est choisie. Sur une carte d'appareil (ressource) partagée, la fenêtre demande aussi
   **« Qui demande ? »** parmi les enfants propriétaires ; sur la carte enfant, l'enfant est connu.
3. Après envoi, la carte de l'enfant concerné (et la carte de la ressource visée) affiche
   « Demande envoyée · en attente », puis le résultat : « Accepté : 30 min sur la Télé salon »,
   « Refusé », ou « Pas de réponse ». Le résultat reste visible quelques minutes puis disparaît.
4. Tant qu'une demande identique est en attente, « Demander » est remplacé par « En attente… ».

Un compte admin ne voit pas « Demander » (il n'a pas besoin de code). Si la liste « Demandes » est
vide, « Demander » n'apparaît pas.

### Sur le téléphone du parent

Notification : titre « Contrôle parental », texte du genre « Gabin demande 30 min de YouTube sur la
Télé salon ». Boutons :

| Action demandée | Boutons |
|---|---|
| Autoriser service / appareil | *Accepter 30 min* (la proposition), puis les autres durées parmi 15 min, 30 min, 1 h, 2 h, « Jusqu'au prochain changement », puis *Refuser* |
| Bonus (enfant ou Switch) | *Accepter* la proposition, les autres montants de bonus configurés pour cette carte, *Refuser* |
| Minuteur | *Accepter* la proposition, les autres durées du minuteur (15, 30, 60 min), *Refuser* |
| Devoirs terminés | *Accepter*, *Refuser* |

Une réponse applique l'action comme si le parent l'avait faite lui-même, sans code. Ensuite la
notification est retirée de tous les téléphones de la liste. Une réponse à une demande déjà
traitée ou expirée n'a aucun effet (au plus une notification « Demande déjà traitée »).

## Contraintes

- **Sécurité.** Une demande ne débloque rien en soi. Seule une réponse authentique d'un téléphone
  de la liste « Demandes » applique l'action. Un compte non admin (la tablette) ne doit pas pouvoir
  provoquer une acceptation, même en fabriquant un événement ou en appelant un service. Les
  identifiants d'action portés par la notification contiennent un jeton aléatoire propre à la
  demande, pour qu'une réponse ne soit pas devinable.
- Le moteur reste la seule source de vérité : les cartes ne font qu'afficher l'état qu'il publie
  (abonnement `parental_control/state/subscribe` existant).
- L'action acceptée passe par les mêmes méthodes du moteur que l'action débloquée par code
  (`add_exception`, `add_bonus`, `homework_done`, `start_timer`) : mêmes validations, même
  comportement en simulation.
- En simulation, les notifications de demande portent le même préfixe que les autres.
- Le code parental, son verrouillage et les actions admin sont inchangés.
- Ne jamais mettre le code parent dans un tableau de bord (règle existante) : la demande ne doit
  pas inciter à le faire.

## Non-objectifs

- Android (3 boutons au plus) : pas d'adaptation dans cette version.
- Demande depuis l'appareil de l'enfant lui-même (iPad, Chromebook) : seulement depuis les cartes HA.
- Relancer après une pause générale : ce n'est pas une action de carte aujourd'hui, donc pas
  demandable.
- Historique consultable des demandes dans le panneau : le journal HA suffit.
- Délai de refus, limites quotidiennes de demandes : hors sujet pour l'instant.

## Choix laissés au constructeur (et ceux que j'ai faits)

Mes choix (Claude), à valider à la lecture :

- **Liste de configuration** : nouveau champ `request_notify` (services `notify.mobile_app_…`) dans
  la config, à côté de `notify`, avec le même sélecteur de puces dans le panneau, intitulé
  « Demandes de temps (parents) ».
- **« Jusqu'au prochain changement »** n'est offert que pour autoriser un service ou un appareil, la
  seule action où il existe déjà (`minutes` absent). Bonus et minuteur gardent leurs montants.
- **Délai d'expiration** : 15 minutes, constante (pas de réglage).
- **Demandes en mémoire** du moteur : un redémarrage de HA les oublie. Une réponse arrivée après
  coup est traitée comme « déjà traitée ».
- Le résultat reste affiché sur la tablette 5 minutes.
- `request_notify` est un champ du modèle `Config` (`core/config_io.py`), comme `notify` : lu,
  écrit, importé par `importer_configuration`, testé en aller-retour. Ce n'est pas une option de
  l'entrée de configuration.
- **Montants proposés au parent** : la carte envoie avec la demande la liste des montants qu'elle
  offre (bonus configurés, durées du minuteur ou d'autorisation). Le moteur la valide : de 1 à
  240 minutes chacun, 6 valeurs au plus, et la proposition de l'enfant doit en faire partie.
  Comme la tablette ne fait que proposer, un montant inattendu ne débloque rien sans le parent.
- **Demandeur toujours connu** : toute demande porte un `kid_id`, y compris le bonus Switch sur
  une ressource. Sur une carte d'appareil, l'enfant est choisi parmi les propriétaires. Pour le
  dédoublonnage, la clé est (enfant, type d'action, cible : ressource, service). L'état
  « en attente » ou le résultat s'affiche sur la carte de l'enfant et sur celle de la ressource
  visée.
- **Aucun service public de réponse** : la réponse n'arrive que par l'écouteur d'événement des
  notifications, qui appelle directement les méthodes du moteur. La tablette n'a rien à appeler.
- L'état publié (`state/subscribe`) contient les demandes en cours et leurs résultats récents
  pour tous les abonnés, mais jamais les jetons.

Laissé au constructeur :

- Le nom du service (ex. `parental_control.demander`) et son schéma, qui reprend les données de
  l'action visée plus la proposition et l'enfant demandeur.
- Le détail de l'écoute de `mobile_app_notification_action` et du format des identifiants
  d'action, dans le respect de la section « Qui peut répondre ».
- Le retrait des notifications (`clear_notification` avec un `tag` par demande) et le texte exact des
  messages.
- La forme de la trace dans le journal (entrée logbook ou événement dédié).
- L'affichage précis dans les cartes, dans le style existant (`dialogs.js`, pastilles, thème clair).
- Les tests : moteur (cycle de vie, doublon, expiration, première réponse, réponse tardive, réponse
  non authentique), services, et `lib.js` pour l'affichage.
