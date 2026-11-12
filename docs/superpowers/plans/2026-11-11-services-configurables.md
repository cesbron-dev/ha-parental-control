# Services configurables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le catalogue de services (identifiants AdGuard bruts et `label:<id>`) par une liste de services définie par le parent, chaque service regroupant des services AdGuard et/ou des labels d'interrupteurs.

**Architecture:** Le modèle (`core/model.py`) gagne `Service` et `LabelLink` ; tout le moteur raisonne en identifiants de services du parent. L'adaptateur AdGuard traduit ces services en identifiants AdGuard (union) ; la découverte des interrupteurs passe par les labels rattachés aux services. Le panneau gère la liste dans Général ; les cartes lisent les noms dans l'état publié.

**Tech Stack:** Python 3.13 (Home Assistant custom integration, pytest), JS ES modules sans build (tests `node --test`).

**Spec:** `docs/superpowers/specs/2026-11-11-ha-parental-control-services-configurables-design.md`

## Global Constraints

- Textes d'interface, docstrings, commentaires et messages de commit en français.
- Commits terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Moteur pur dans `core/` (aucun import Home Assistant).
- Clé de config `services` : liste d'objets `{"id", "name", "icon"?, "adguard": [...], "labels": [{"label_id", "on_means_allowed"}]}`.
- Plus de préfixe `label:` ni de clé `label_services` (ignorée si présente au chargement).
- `DEFAULT_LEISURE` devient `()` : une config sans `default_leisure` a des loisirs vides.
- Un label rattaché à au plus un service ; jamais à la fois rattaché et label de cible.
- Un même identifiant AdGuard peut être dans plusieurs services ; bloqué dès qu'un service géré qui le contient est bloqué.
- « Concerne AdGuard » = `service.adguard` non vide ; « concerne des interrupteurs » = `service.labels` non vide.
- Chargement depuis le stockage (`parse_config`) : identifiants de service inconnus retirés des listes sans erreur. Config client (`parse_client_config`) : identifiant inconnu → `ConfigError`.
- Tests : `cd /Users/olivier/dev/github.com/cesbron-dev/ha-parental-control && python -m pytest -q` et `node --test tests/js/`.

## Review Focus

1. Config stockée v0.3 (loisirs = `youtube`, `roblox`… sans clé `services`) : se charge, listes vides, aucun appel AdGuard pour débloquer ces services → Task 1 et Task 3.
2. Service mixte (AdGuard + label) dans les loisirs d'un enfant fermé : AdGuard bloque ses identifiants ET l'interrupteur s'allume → Task 3.
3. Identifiant AdGuard partagé par deux services, l'un ouvert par exception, l'autre bloqué : reste bloqué → Task 3.
4. Suppression d'un service dans le panneau : retiré de `default_leisure`, `default_on_demand` et des ajouts / retraits de chaque enfant, sinon l'enregistrement serait refusé → Task 6.
5. Service sans aucun rattachement mis dans les loisirs : rien n'est appelé, aucune erreur → Task 3.

---

### Task 1: Modèle et configuration

**Files:**
- Modify: `custom_components/parental_control/core/model.py`
- Modify: `custom_components/parental_control/core/config_io.py`
- Test: `tests/core/test_config_io.py` (et fixtures dans `tests/fixtures.py` qui utilisent `label_services`)

**Interfaces:**
- Produces (dans `core/model.py`) :
  - `@dataclass(frozen=True) class LabelLink: label_id: str; on_means_allowed: bool = False`
  - `@dataclass(frozen=True) class Service: id: str; name: str; icon: str | None = None; adguard: tuple[str, ...] = (); labels: tuple[LabelLink, ...] = ()` avec propriétés `has_adguard: bool`, `has_labels: bool`.
  - `Config.services: tuple[Service, ...] = ()` (remplace `label_services`).
  - `Config.service(service_id: str) -> Service | None`
  - `Config.has_adguard(service_id: str) -> bool` / `Config.has_labels(service_id: str) -> bool` (faux si inconnu).
  - `Config.adguard_ids(service_ids: Iterable[str]) -> frozenset[str]` (union, inconnus ignorés).
  - `Config.service_for_label(label_id: str) -> tuple[Service, LabelLink] | None`
- Supprimés : `LABEL_PREFIX`, `label_service_id`, `is_label_service`, `LabelService`, `Config.label_services`.
- `config_io` : `parse_config(data)` (stockage, tolérant) ; `parse_client_config(data)` (strict) ; `dump_config` écrit `services` (sans `icon` s'il est `None`).

- [ ] **Step 1: Tests qui échouent** dans `tests/core/test_config_io.py` :
  - `test_services_round_trip` : config avec `services=[{"id":"jeux","name":"Jeux vidéo","icon":"mdi:gamepad-variant","adguard":["roblox","fortnite"],"labels":[{"label_id":"console","on_means_allowed":True}]}]`, `default_leisure=["jeux"]` → `parse_config` puis `dump_config` redonne la même liste `services` et `cfg.adguard_ids(["jeux"]) == {"roblox","fortnite"}`, `cfg.service_for_label("console")[0].id == "jeux"`.
  - `test_stored_config_drops_unknown_services` : `default_leisure=["youtube","jeux"]`, `default_on_demand=["tiktok"]`, enfant `leisure_add=["roblox"]`, aucun service `youtube/tiktok/roblox` → `cfg.default_leisure == ("jeux",)`, `cfg.default_on_demand == ()`, `kid.leisure_add == frozenset()`.
  - `test_client_config_rejects_unknown_service` : même données via `parse_client_config` → `ConfigError` dont le message contient `default_leisure`.
  - `test_legacy_label_services_key_ignored` : `label_services=[{"label_id":"internet"}]` présent → chargé sans erreur, `cfg.services == ()`.
  - `test_missing_default_leisure_is_empty` : pas de clé → `cfg.default_leisure == ()`.
  - Validation (`ConfigError`) : id en double ; `name` vide ; label dans deux services ; label rattaché ET `target_label` d'un enfant ; `adguard` non-liste ; `on_means_allowed` non booléen.
- [ ] **Step 2:** `python -m pytest tests/core/test_config_io.py -q` → échecs attendus (ImportError / AttributeError).
- [ ] **Step 3: Implémenter** le modèle puis `config_io` : `_parse_services`, `_check_labels(services, kids, resources)` adapté ; filtrage des identifiants inconnus via un paramètre interne `strict: bool` (`parse_config(data)` = non strict, `parse_client_config` = strict ; journaliser les retraits avec `logging.getLogger(__name__).info`). Mettre à jour toutes les fixtures / tests existants qui utilisent `label_services` ou `label:` pour la nouvelle forme (les tests de comportement par label des tâches suivantes les réécriront, ici seulement de quoi faire passer `tests/core/test_config_io.py`).
- [ ] **Step 4:** `python -m pytest tests/core/test_config_io.py -q` → PASS.
- [ ] **Step 5: Commit** `feat: services du parent dans le modèle et la configuration`.

Note : à l'issue de cette tâche d'autres tests (évaluateur, HA) peuvent échouer par import ; c'est attendu, les tâches 2 à 4 les rétablissent. Ne pas les corriger ici au-delà des imports.

### Task 2: Évaluateur et état des interrupteurs (core)

**Files:**
- Modify: `custom_components/parental_control/core/evaluator.py` (lignes ~335-345, ~418-428, ~483-487, ~512, ~665-678)
- Modify: `custom_components/parental_control/core/label_services.py`
- Modify: `custom_components/parental_control/core/requests.py` si elle utilise `is_label_service`
- Test: `tests/core/test_evaluator_access.py`, `tests/core/test_label_services.py`, `tests/core/test_display.py`, `tests/core/test_requests.py`

**Interfaces:**
- Consumes: Task 1 (`Config.service`, `has_adguard`, `has_labels`).
- Produces: `_service_exception_applies(e, resource, cfg) -> bool` (prend `cfg`) ; `switch_blocked(now, cfg, dec, snap, service, targets)` inchangé (service = id du parent).

Règles (remplacent chaque `is_label_service(s)`) :
- `_resource_state` : sans AdGuard sur la ressource, ne garder que les services `cfg.has_labels(s)` ; avec AdGuard, ne garder que les services connus (`cfg.service(s) is not None`).
- `_service_exception_applies` : service inconnu → `False` ; applicable si `(resource.has(ADGUARD) and cfg.has_adguard(s)) or cfg.has_labels(s)`, puis portée inchangée.
- `opened_services` : services ouverts par exception avec `cfg.has_adguard(s)`, seulement si la ressource a AdGuard.
- `rule_signature` : même condition que `_service_exception_applies`.
- `_service_keys` : seulement les services `cfg.has_adguard(s)`.

- [ ] **Step 1: Tests qui échouent** :
  - `test_label_only_service_kept_without_adguard` : ressource sans AdGuard, service `internet` (labels seulement) dans les loisirs, ressource fermée → `"internet" in blocked_services` ; service `youtube_svc` (AdGuard seulement) absent.
  - `test_mixed_service_exception_opens_on_non_adguard_resource` : service mixte, exception ouverte sur une ressource sans AdGuard → le service sort de `blocked_services`.
  - `test_opened_services_ignores_label_only` : exception ouverte sur `internet` (labels seuls) d'une ressource AdGuard → `opened_services == frozenset()`.
  - `test_unknown_service_exception_ignored` : exception sur `youtube` non déclaré → aucun effet, aucune erreur.
  - Adapter `tests/core/test_label_services.py` : services `label:internet` → service du parent `internet` avec `labels=(LabelLink("internet"),)` ; mêmes attentes qu'avant.
- [ ] **Step 2:** `python -m pytest tests/core -q` → échecs attendus.
- [ ] **Step 3: Implémenter** les règles ci-dessus.
- [ ] **Step 4:** `python -m pytest tests/core -q` → PASS.
- [ ] **Step 5: Commit** `feat: évaluateur sur les services du parent`.

### Task 3: Adaptateur AdGuard, interrupteurs labellisés et moteur

**Files:**
- Modify: `custom_components/parental_control/adapters/adguard.py`, `adapters/__init__.py`
- Modify: `custom_components/parental_control/label_switches.py`
- Modify: `custom_components/parental_control/engine.py` (construction des adaptateurs ~348, noms ~244 et ~711, validation ~989, `_on_registry_change` ~414)
- Test: `tests/ha/test_adapters.py`, `tests/ha/test_label_switches.py`, `tests/ha/test_engine.py`

**Interfaces:**
- Consumes: Task 1, Task 2.
- Produces:
  - `AdGuardAdapter(hass, label, options, leisure: frozenset[str], adguard_ids: Callable[[Iterable[str]], frozenset[str]])` : `_leisure = adguard_ids(leisure)`, `_wanted(desired) = adguard_ids(desired.blocked_services)`, `pause_state()` bloque `_leisure` (identifiants AdGuard) — garder la forme `ResourceState` en identifiants AdGuard pour `force_close`, ou convertir proprement : `apply` doit accepter l'état de pause sans double traduction.
  - `build_adapters(hass, resource, leisure, adguard_ids)` : passe `cfg.adguard_ids`.
  - `label_switches.discover(hass, cfg)` : pour chaque interrupteur actif, liens = `[cfg.service_for_label(l) for l in entry.labels]` non nuls ; premier lien dont le label existe dans le registre l'emporte (ordre : ordre de `cfg.services`, puis ordre des labels) ; `LabelSwitch(entity_id, service.id, link.on_means_allowed, targets)` ; problèmes `unknown_label` par label rattaché absent du registre (service = id du parent) ; `no_target` inchangé.
  - `ParentalEngine.service_name(service_id: str) -> str` : nom du service du parent, sinon l'id (remplace `label_service_name` et `_service_label`).
  - Validation d'une exception / demande : service inconnu → `invalid_target` ; valide si `(cfg.has_adguard(s) and any(r.has(ADGUARD) for r in scope)) or (cfg.has_labels(s) and scope)`.
  - `_on_registry_change` : ne rien faire si aucun service n'a de label.

- [ ] **Step 1: Tests qui échouent** :
  - `test_adguard_blocks_union_of_service_ids` : service `jeux` = `roblox,fortnite`, ressource fermée → appel `set_blocked_services` avec `block=["fortnite","roblox"]`.
  - `test_adguard_shared_id_blocked_wins` : `video`=`youtube`, `ecole`=`youtube,khan` ; `video` bloqué, `ecole` ouvert → `youtube` bloqué, `khan` débloqué.
  - `test_legacy_stored_ids_not_unblocked` : config stockée avec `default_leisure=["youtube"]` sans services, client bloquant `youtube` → aucun appel `unblock`.
  - `test_service_without_attachments_noop` : service vide dans les loisirs → aucun appel AdGuard ni interrupteur, pas d'erreur.
  - `test_mixed_service_drives_adguard_and_switch` : service mixte dans les loisirs d'un enfant fermé, interrupteur avec label rattaché + label de cible de l'enfant → AdGuard bloque et l'interrupteur s'allume.
  - `test_per_label_on_means_allowed` : deux labels du même service, l'un inversé → un interrupteur allumé, l'autre éteint quand le service est bloqué.
  - Adapter les tests existants de `test_label_switches.py` / `test_engine.py` à la nouvelle config.
- [ ] **Step 2:** `python -m pytest tests/ha/test_adapters.py tests/ha/test_label_switches.py tests/ha/test_engine.py -q` → échecs attendus.
- [ ] **Step 3: Implémenter.**
- [ ] **Step 4:** mêmes tests → PASS.
- [ ] **Step 5: Commit** `feat: AdGuard et interrupteurs pilotés par les services du parent`.

### Task 4: Catalogue, WebSocket, état publié et services HA

**Files:**
- Modify: `custom_components/parental_control/catalog.py`, `websocket.py`, `serialize.py`, `services.py` (si validation de service)
- Test: `tests/ha/test_websocket.py`, `tests/ha/test_services.py`, `tests/ha/test_entities.py`, `tests/ha/test_requests.py`

**Interfaces:**
- Consumes: Task 3 (`engine.service_name`).
- Produces:
  - `services_catalog(hass) -> dict[str, str]` : catalogue AdGuard seul (plus de `cfg`).
  - WS `parental_control/services/catalog` → `{"services": <catalogue AdGuard>}` (plus de `label_services`).
  - État publié (`display`) : `state["services"] = {id: {"name", "icon", "adguard": bool, "labels": bool}}` pour tous les services du parent, dans l'ordre de la config ; `service_names` supprimé. `kids[...].label_services` et `resources[...].label_services` gardés (ids du parent).
  - Les notifications et messages de demande utilisent `engine.service_name`.

- [ ] **Step 1: Tests qui échouent** :
  - `test_catalog_is_adguard_only` (WS) : `services` = catalogue AdGuard, pas de clé `label_services`.
  - `test_state_publishes_services` : `state["services"]["jeux"] == {"name":"Jeux vidéo","icon":"mdi:gamepad-variant","adguard":True,"labels":True}` ; pas de `service_names`.
  - `test_request_message_uses_service_name` : demande sur `jeux` → message contient « Jeux vidéo ».
  - Adapter les tests existants qui attendaient `service_names` ou `label:`.
- [ ] **Step 2:** `python -m pytest tests/ha -q` → échecs attendus.
- [ ] **Step 3: Implémenter.**
- [ ] **Step 4:** `python -m pytest -q` (suite complète Python) → PASS, sortie propre.
- [ ] **Step 5: Commit** `feat: état publié et catalogue pour les services du parent`.

### Task 5: Cartes (lib.js, editor-lib.js)

**Files:**
- Modify: `custom_components/parental_control/www/lib.js` (`serviceLabel`, `serviceToggles`, `allowChoices`, `kidServiceToggles`, `LABEL_PREFIX`), `www/editor-lib.js`, et tout appelant de `serviceLabel(…, state.service_names)` (`kid-card.js`, `resource-card.js`, `requests.js`, `dialogs.js`…).
- Test: `tests/js/lib.test.mjs`, `tests/js/editor-lib.test.mjs`

**Interfaces:**
- Consumes: Task 4 (`state.services`).
- Produces: `serviceLabel(id, services = null)` : `services?.[id]?.name`, sinon id capitalisé (plus de table `SERVICES` AdGuard codée en dur si elle n'a plus d'usage) ; `serviceIcon(id, services)` → `services?.[id]?.icon ?? null`. Les tests `startsWith("label:")` deviennent `state.services?.[s]?.adguard` / `?.labels` :
  - `serviceToggles` / `allowChoices` : un service est montré sur un appareil si `(adguard && svc.adguard) || labelled.includes(s)`.
  - `kidServiceToggles` : appareils des exceptions = tous les appareils de l'enfant si `svc.labels`, sinon ses appareils AdGuard.
  - `editor-lib` : « Services affichés » liste les services de `state.services` pertinents (mêmes filtres), libellés par `serviceLabel`.

- [ ] **Step 1: Tests qui échouent** (`lib.test.mjs`) :
  - `serviceLabel` lit `services.jeux.name` ; id inconnu → capitalisé.
  - `serviceToggles` : service mixte sur appareil AdGuard affiché ; service à labels seuls non ciblé sur appareil AdGuard non affiché.
  - `kidServiceToggles` : service à labels → exceptions de tous les appareils de l'enfant.
  - Adapter les tests existants qui utilisaient `label:` et `service_names`.
- [ ] **Step 2:** `node --test tests/js/` → échecs attendus.
- [ ] **Step 3: Implémenter.**
- [ ] **Step 4:** `node --test tests/js/` → PASS.
- [ ] **Step 5: Commit** `feat: cartes sur les services du parent`.

### Task 6: Panneau Règles — liste et édition des services

**Files:**
- Modify: `custom_components/parental_control/www/panel.js` (onglet Général : remplacer `_labelServicesCard` ; `_catalog` devient `_adguard` pour le sélecteur ; listes loisirs / sur demande ; `_targetLabelField` : labels pris = labels rattachés aux services + cibles), `www/panel-kids.js` (noms), `www/panel-lib.js`, `www/panel-style.js`
- Test: `tests/js/panel-lib.test.mjs`

**Interfaces:**
- Consumes: Task 4 (WS catalogue AdGuard seul ; `labels/list` ; `label_switches/list`).
- Produces (`panel-lib.js`, fonctions pures sur le brouillon `draft`) :
  - `serviceId(name, taken: string[]) -> string` : minuscules, accents retirés (`normalize("NFD")`), non-alphanumériques → `_`, `_` en trop retirés ; vide → `service` ; suffixe `_2`, `_3`… si pris.
  - `addService(draft, name) -> string` (ajoute `{id, name, adguard: [], labels: []}`, renvoie l'id).
  - `removeService(draft, id)` : retire le service et l'id de `default_leisure`, `default_on_demand`, et des `leisure_add/leisure_remove/on_demand_add/on_demand_remove` de chaque enfant.
  - `renameService(draft, id, name)`, `setServiceIcon(draft, id, icon)`.
  - `toggleServiceAdguard(draft, id, adguardId)`, `toggleServiceLabel(draft, id, labelId)`, `setServiceLabelInverted(draft, id, labelId, on)`.
  - `freeLabels(draft, labels, serviceId) -> label[]` : labels HA ni rattachés à un autre service, ni de cible.
  - `serviceNames(draft) -> {id: name}` : utilisé partout où le panneau utilisait `this._catalog` pour nommer un service.
  - Supprimer `toggleLabelService`, `setLabelInverted`, `isLabelService`.
- UI (style actuel, maquettes validées) :
  - Carte « Services » dans Général : une ligne par service (icône, nom, pastilles bleues des services AdGuard, violettes des labels avec « N interrupteur(s) » d'après `label_switches/list`), « Ajouter un service » ; un clic ouvre l'édition.
  - Édition : champ nom, sélecteur d'icône (`ha-icon-picker`), liste AdGuard avec ✕ et ajout par recherche dans le catalogue AdGuard (saisie libre si catalogue vide), liste de labels avec interrupteurs trouvés, bascule « Allumé = autorisé » et ✕, ajout parmi `freeLabels`, bouton « Supprimer » (confirmation en deux appuis, existante) et « OK ».
  - Listes loisirs / sur demande (communes et par enfant) : ajout parmi les services du parent seulement ; libellés via `serviceNames`.
  - Le récapitulatif « Interrupteurs pilotés » reste dans la carte Services.

- [ ] **Step 1: Tests qui échouent** (`panel-lib.test.mjs`) :
  - `serviceId("Jeux vidéo", [])` → `"jeux_video"` ; `serviceId("Jeux vidéo", ["jeux_video"])` → `"jeux_video_2"` ; `serviceId("!!", [])` → `"service"`.
  - `removeService` retire l'id de toutes les listes (défaut et enfants).
  - `toggleServiceLabel` puis `setServiceLabelInverted` → `labels == [{label_id:"console", on_means_allowed:true}]` ; re-toggle retire.
  - `freeLabels` exclut les labels d'un autre service et les labels de cible, garde ceux du service édité.
  - Adapter les tests des fonctions supprimées.
- [ ] **Step 2:** `node --test tests/js/panel-lib.test.mjs` → échecs attendus.
- [ ] **Step 3: Implémenter** `panel-lib.js` puis l'UI.
- [ ] **Step 4:** `node --test tests/js/` → PASS ; ouvrir le panneau n'est pas requis ici (vérifié au déploiement).
- [ ] **Step 5: Commit** `feat: panneau — liste et édition des services`.

### Task 7: Documentation

**Files:**
- Modify: `README.md` (remplacer la section « Services par label » par « Services » : création dans Général, rattachements AdGuard et labels, sens par label, labels de cible ; note de mise à jour : on repart d'une liste vide, les services AdGuard bloqués par l'ancienne configuration restent bloqués jusqu'à action du parent).

- [ ] **Step 1:** Rédiger.
- [ ] **Step 2:** `python -m pytest -q && node --test tests/js/` → PASS.
- [ ] **Step 3: Commit** `docs: services configurables dans le README`.
