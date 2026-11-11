# Services par label HA — conception

Date : 2026-11-10. Statut : à valider.

## Intention

Aujourd'hui, un « service » du contrôle parental est un identifiant de service bloqué AdGuard
(YouTube, Fortnite…). Le catalogue vient de l'intégration `adguard_clients`, et le moteur applique
les services aux clients AdGuard des appareils de l'enfant. Tout autre moyen de blocage
demande une intégration dédiée.

L'objectif : pouvoir piloter, **comme un service**, n'importe quel interrupteur Home Assistant,
sans écrire d'intégration spécifique. Cas déclencheur : une règle de pare-feu UniFi qui coupe
internet pour un appareil, exposée par l'intégration UniFi sous forme de `switch`. Le parent la
désigne en posant des **labels HA** sur l'interrupteur.

« Comme un service » veut dire (décidé avec Olivier) : la règle se range dans les **loisirs** ou
**sur demande** d'un enfant, suit les plages horaires comme un service AdGuard, et peut être
ouverte par une **demande d'accès** ou une **exception** de service.

## Objectifs

- Un label HA peut être déclaré **label de service** dans le panneau Règles. Il devient un service
  du catalogue, à côté des services AdGuard, avec le nom du label.
- Un label HA peut être associé à un **enfant** ou à un **appareil logique** : c'est un **label
  de cible**.
- Un interrupteur qui porte un label de service et un label de cible est piloté par le moteur :
  il est dans l'état « bloqué » quand ce service doit être bloqué pour cette cible, et dans
  l'état « autorisé » sinon.
- Le service se gère partout où un service AdGuard se gère : loisirs et sur demande (par défaut
  et par enfant), demandes d'accès, exceptions, notifications, simulation.

## Non-objectifs

- Pas d'intégration UniFi dédiée : seuls les `switch` HA et leurs labels sont utilisés.
- Pas de coupure de l'appareil entier par ce mécanisme : l'interrupteur d'appareil existant
  (`ResourceKind.SWITCH`, éteint quand le temps est écoulé) reste tel quel.
- Pas de mesure du temps d'usage à partir de ces interrupteurs.
- Pas de remplacement des services AdGuard : les deux coexistent dans le même catalogue.

## Anti-objectifs

- Un label ou une convention de nommage qui changerait le comportement sans que le parent l'ait
  déclaré dans le panneau : seuls les labels désignés comme service ou associés à une cible
  comptent.
- Toucher à un interrupteur qui n'a pas été désigné ainsi.
- Casser les configurations existantes : sans label de service déclaré, rien ne change.

## Ce qui est décidé

### Rôles des labels (décidé avec Olivier)

- **Label de service** : choisi dans le panneau parmi les labels HA existants. Il définit le
  service (son nom affiché est le nom du label).
- **Label de cible** : associé dans le panneau à un enfant ou à un appareil logique. Un label ne
  peut cibler qu'un seul enfant ou appareil.
- Un interrupteur peut porter plusieurs labels. Exemple : règle UniFi « Couper internet tablette
  Maël » avec les labels « Internet » (service) et « Tablette de Maël » (cible).
- Pour une gestion fine, Olivier prévoit une règle par appareil ou par enfant.

### Identifiant du service (mon choix)

Un service par label a pour identifiant `label:<label_id>` (identifiant du registre des labels
HA, stable au renommage). Le préfixe évite toute collision avec un identifiant AdGuard. Le nom
affiché est lu dans le registre des labels à chaque fois, donc il suit les renommages.

### Sens de l'interrupteur (mon choix)

Par défaut, **allumé = bloqué**, comme une règle de pare-feu active. Une option par label de
service, « Allumé = autorisé », inverse le sens pour les interrupteurs qui ouvrent l'accès quand
ils sont allumés.

### Quand le service est bloqué

- **Cible appareil logique** : l'interrupteur suit l'état du service pour cet appareil, calculé
  comme pour AdGuard. Le service est bloqué s'il est sur demande pour un propriétaire, ou s'il
  est dans les loisirs d'un propriétaire et que l'appareil est fermé. Les exceptions de service
  sur cet appareil s'appliquent. Cela vaut même si l'appareil n'a aucun client AdGuard :
  aujourd'hui, `blocked_services` n'est calculé que pour un appareil qui a AdGuard.
- **Cible enfant** (mon choix) : l'interrupteur suit l'état de l'enfant, pas celui d'un de ses
  appareils. Le service est bloqué s'il est sur demande pour l'enfant, ou s'il est dans ses
  loisirs et que l'enfant est hors temps autorisé (état de l'enfant fermé). Les exceptions de
  service qui visent l'enfant s'appliquent.
- **Plusieurs cibles sur un même interrupteur** (mon choix) : bloqué dès qu'une des cibles
  l'exige, comme pour un appareil partagé.
- **Interrupteur avec un label de service sans label de cible** : ignoré, avec un avertissement
  dans le journal et dans le panneau.
- **Un label est soit de service, soit de cible**, jamais les deux : le panneau refuse le
  cumul. Un interrupteur dont les cibles désignent un enfant et un de ses appareils suit la
  règle « bloqué dès qu'une cible l'exige ».
- **Service géré seulement** (mon choix) : le moteur ne touche un interrupteur que si son
  service figure dans les loisirs ou sur demande d'au moins une cible (par défaut ou pour
  l'enfant). Sinon l'interrupteur est laissé tel quel, comme les services AdGuard non gérés.
  La pause et la fermeture d'urgence bloquent les services gérés, pas les autres.

### Cible enfant : état et exceptions (mon choix)

- « Enfant fermé » est l'état calculé de l'enfant (`KidState`), qui tient déjà compte de la
  frise, du quota, de la pause et de la fermeture d'urgence.
- Une exception ou une demande acceptée sur ce service ouvre l'interrupteur à cible enfant si
  elle vise l'enfant, ou un de ses appareils. L'enfant fait sa demande depuis un appareil, et
  la règle à cible enfant couvre tous ses appareils : l'ouvrir pour la demande d'un appareil
  est le comportement attendu.
- Une exception sur un appareil ouvre aussi l'interrupteur à cible de cet appareil, comme pour
  AdGuard.

### Calcul des services (mon choix)

Le calcul des services bloqués (`blocked_services`), des exceptions de service et des clés de
services pour les notifications ne dépend plus de la présence d'AdGuard : il est fait pour
tout appareil logique. Chaque adaptateur n'applique que ce qui le concerne : l'adaptateur
AdGuard ses services, le nouvel adaptateur ses services par label. Pas de nouveau type
d'intégration d'appareil : les interrupteurs labellisés ne sont pas rangés dans l'arbre des
appareils, ils sont trouvés par leurs labels. Le comportement des appareils AdGuard existants
doit rester identique (tests de non-régression).
- **Interrupteur indisponible ou absent** : même traitement que les autres adaptateurs
  (journalisé, nouvelle tentative au prochain calcul).

### Application

- Le moteur repère les interrupteurs par le registre des entités (labels de l'entité). Il
  réagit aux changements du registre : ajout ou retrait de label, nouvel interrupteur.
- Écart d'état (quelqu'un a basculé la règle dans UniFi) : le moteur la remet dans l'état voulu,
  comme il le fait pour AdGuard.
- Mode simulation : décrit l'action sans l'exécuter, comme les autres adaptateurs.
- Fermeture d'urgence / pause : bloque aussi ces services.

### Panneau Règles

- **Réglages** : liste des labels HA, avec une case « label de service » et l'option de sens.
- **Enfants** et **Appareils** : un champ « Label de cible » (sélecteur de label HA).
- Les listes loisirs / sur demande et les écrans de demande montrent les services par label
  avec le nom du label, mélangés aux services AdGuard. Un repère visuel discret indique leur
  origine.
- Un récapitulatif « Interrupteurs pilotés » montre, pour chaque label de service, les
  interrupteurs trouvés, leur cible et leur état, avec les avertissements (sans cible, cible
  inconnue, indisponible).

### Configuration

- Nouveaux champs dans la configuration stockée existante (`core/config_io.py`, celle que le
  panneau lit et enregistre) : la liste des labels de service (avec l'option de sens), le label
  de cible d'un enfant, le label de cible d'un appareil logique.
- Tous facultatifs : une configuration existante se charge sans changement.
- Un label supprimé du registre HA : le service disparaît du catalogue, et ses entrées dans les
  loisirs ou sur demande sont ignorées, avec un avertissement dans le panneau ; pas d'erreur
  de chargement.

## Contraintes

- Même architecture que l'existant : moteur pur dans `core/`, adaptateurs dans `adapters/`,
  WebSocket et panneau existants.
- Seuls les parents (au sens de la v0.3.0) modifient ces réglages.
- Les textes de l'interface et la documentation sont en français.
- Tests : pytest pour le moteur, la configuration et l'adaptateur ; tests JS pour le panneau,
  comme aujourd'hui.

## Laissé au constructeur

- La structure exacte des nouveaux champs de configuration et leur validation.
- La façon d'abonner le moteur aux changements du registre des entités et des labels.
- La disposition précise des nouveaux champs dans le panneau, dans le style actuel.
- La forme du repère visuel des services par label.
