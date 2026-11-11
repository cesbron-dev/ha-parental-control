# Services par label HA — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** piloter comme un service du contrôle parental tout `switch` HA désigné par des labels (un label de service + un label de cible enfant ou appareil).

**Architecture:** la config gagne les labels de service et les labels de cible. Le calcul des services du moteur pur (`core/`) ne dépend plus d'AdGuard. Un module pur décide l'état voulu d'un interrupteur labellisé. Un module HA (`label_switches.py`) trouve les interrupteurs dans le registre des entités et les pilote depuis le moteur. Le panneau et les cartes exposent ces services à côté des services AdGuard.

**Tech Stack:** Python 3.14 / Home Assistant 2026.11 (pytest-homeassistant-custom-component), JS vanilla (tests `node --test`).

**Spec:** `docs/superpowers/specs/2026-11-10-ha-parental-control-services-par-label-design.md`

## Global Constraints

- Branche `feat/services-par-label` (partie de `feat/parents-non-admin`).
- Tests Python : `.venv/bin/pytest` (toute la suite reste verte). Tests JS : `node --test tests/js/*.mjs`.
- Identifiant d'un service par label : `label:<label_id>` (préfixe `LABEL_PREFIX = "label:"`).
- Sens par défaut : allumé = bloqué ; option par label de service `on_means_allowed` (« Allumé = autorisé »).
- Sans label de service déclaré, le comportement est strictement identique à aujourd'hui.
- Un label est soit de service, soit de cible ; un label de cible désigne un seul enfant ou appareil.
- Seuls les parents (`_require_parent`) lisent et modifient ces réglages par WebSocket.
- Textes de l'interface, journal, README et commits en français ; commits terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Un label supprimé ou renommé dans HA : le nom suit le renommage ; un service d'un label supprimé est ignoré (avertissement), sans erreur de chargement ni plantage du moteur → tests en Tâche 1 (chargement) et Tâche 4 (découverte).
2. L'adaptateur AdGuard ne reçoit jamais un identifiant `label:…` (sinon `set_blocked_services` d'AdGuard échoue) → test en Tâche 2.
3. Une exception « jusqu'à la prochaine décision » posée avant la mise à jour garde sa signature (pas d'expiration fantôme) → test en Tâche 2.
4. Interrupteur indisponible, ou basculé à la main dans UniFi : pas d'exception, nouvelle tentative et correction de dérive au plus une fois par `DRIFT_COOLDOWN` → tests en Tâche 4.
5. Un appareil sans AdGuard, avec lecteur ou interrupteur d'appareil, ne reste pas allumé à cause d'une exception de service par label (`opened_services` vide hors AdGuard) → test en Tâche 2.

---

### Task 1: Modèle et configuration

**Files:**
- Modify: `custom_components/parental_control/core/model.py`
- Modify: `custom_components/parental_control/core/config_io.py`
- Test: `tests/core/test_config_io.py`

**Interfaces:**
- Produces (dans `core/model.py`) :
  - `LABEL_PREFIX: Final = "label:"`
  - `def label_service_id(label_id: str) -> str` → `"label:" + label_id`
  - `def is_label_service(service: str) -> bool`
  - `@dataclass(frozen=True) class LabelService: label_id: str; on_means_allowed: bool = False` avec propriété `service -> str` (= `label_service_id(label_id)`)
  - `Config.label_services: tuple[LabelService, ...] = ()`
  - `Kid.target_label: str | None = None` ; `Resource.target_label: str | None = None`
  - `Config.label_target(label_id: str) -> tuple[str, str] | None` : `("kid", kid_id)` ou `("resource", resource_id)`, `None` si le label ne cible rien.
- JSON : `config.label_services = [{"label_id": "...", "on_means_allowed": false}]`, `kid.target_label`, `resource.target_label` (tous facultatifs ; `dump_config` n'écrit `target_label` que s'il n'est pas `None`, `on_means_allowed` toujours).

- [ ] **Step 1: tests qui échouent** dans `tests/core/test_config_io.py` :
  - `test_label_fields_absent_keep_defaults` : la config de famille actuelle → `cfg.label_services == ()`, tous les `target_label` à `None`, et `dump_config(parse_config(d))` ne contient pas la clé `target_label`.
  - `test_label_fields_roundtrip` : `label_services=[{"label_id":"internet","on_means_allowed":True}]`, `target_label="tablette_mael"` sur une ressource, `target_label="mael"` sur un enfant → relu identique après `dump_config` ; `cfg.label_services[0].service == "label:internet"` ; `cfg.label_target("mael") == ("kid", <id de Maël>)`.
  - `test_label_both_service_and_target_rejected` : `label_id` « internet » aussi `target_label` d'un enfant → `ConfigError` dont le chemin commence par `label_services`.
  - `test_target_label_used_twice_rejected` : même `target_label` sur un enfant et une ressource → `ConfigError`.
  - `test_label_service_duplicate_rejected` : deux fois le même `label_id` → `ConfigError`.
- [ ] **Step 2:** `.venv/bin/pytest tests/core/test_config_io.py -v` → les nouveaux tests échouent.
- [ ] **Step 3:** implémenter les champs, la lecture, l'écriture et la validation (messages en français, dans le style des `_fail` existants).
- [ ] **Step 4:** `.venv/bin/pytest tests/core -v` → PASS.
- [ ] **Step 5:** commit `feat: labels de service et de cible dans la configuration`.

### Task 2: Calcul des services indépendant d'AdGuard

**Files:**
- Modify: `custom_components/parental_control/core/evaluator.py` (`_resource_state`, `_service_exception_applies`, `_apply_exceptions`, `rule_signature`)
- Modify: `custom_components/parental_control/adapters/adguard.py`
- Modify: `custom_components/parental_control/engine.py` (`_check_target`)
- Test: `tests/core/test_evaluator_access.py`, `tests/ha/test_adapters.py`, `tests/ha/test_engine.py`

**Interfaces:**
- Consumes: `is_label_service` (Task 1).
- Produces : `ResourceState.blocked_services` est calculé pour **toute** ressource (sur demande ∪ loisirs si fermée), exceptions de service comprises ; `opened_services` reste vide pour une ressource sans AdGuard.

Règles :
- `_service_exception_applies` ne teste plus `ResourceKind.ADGUARD`.
- `_apply_exceptions` : `opened_services` n'est rempli que si `resource.has(ResourceKind.ADGUARD)`, sinon `frozenset()`.
- `rule_signature` : une ressource entre dans la signature d'un service si elle a AdGuard **ou** si `is_label_service(target.service)`. Les signatures des services AdGuard restent identiques.
- `_service_keys` (avertissements de fermeture) : inchangé, AdGuard seulement. Pas d'avertissement de fermeture pour les services par label dans cette version.
- `AdGuardAdapter` ignore tout identifiant `label:…`, dans l'ensemble géré passé au constructeur comme dans `desired.blocked_services`.
- `ParentalEngine._check_target` : un service `label:…` est une cible valide dès que la portée (enfant, ressource ou global) contient au moins une ressource ; un service AdGuard garde l'exigence d'une ressource AdGuard.

- [ ] **Step 1: tests qui échouent :**
  - `test_blocked_services_computed_without_adguard` (core) : ressource « TV » avec seulement un interrupteur, propriétaire dont les loisirs contiennent `label:internet`, frise fermée → `"label:internet" in snap.resources["tv"].blocked_services` ; frise ouverte → absent.
  - `test_label_service_exception_on_non_adguard_resource` (core) : exception ouverte sur `label:internet` pour cette ressource → retiré de `blocked_services`, et `opened_services == frozenset()`.
  - `test_adguard_signature_unchanged` (core) : enfant avec un appareil AdGuard et un appareil interrupteur ; `rule_signature(Target(kid_id=…, service="youtube"))` ne contient que l'appareil AdGuard.
  - `test_label_signature_covers_all_kid_resources` (core) : même enfant, `service="label:internet"` → les deux appareils.
  - `test_adguard_adapter_ignores_label_services` (ha) : ensemble géré `{"youtube","label:internet"}`, état voulu bloquant les deux → un seul appel `set_blocked_services` dont la liste ne contient pas `label:internet`.
  - `test_request_label_service_without_adguard_accepted` (ha, engine) : demande d'accès à `label:internet` pour un enfant sans appareil AdGuard → acceptée (pas de `invalid_target`).
- [ ] **Step 2:** lancer ces tests → FAIL.
- [ ] **Step 3:** implémenter les règles ci-dessus.
- [ ] **Step 4:** `.venv/bin/pytest` (suite complète) → PASS, sans modifier les tests existants.
- [ ] **Step 5:** commit `refactor: services calculés pour tout appareil, AdGuard ignore les labels`.

### Task 3: État voulu d'un interrupteur labellisé (pur)

**Files:**
- Create: `custom_components/parental_control/core/label_services.py`
- Test: `tests/core/test_label_services.py`

**Interfaces:**
- Consumes: Tasks 1-2, `Snapshot`, `Decisions`, `KidStatus`.
- Produces :
  - `LabelTarget = tuple[str, str]` (`("kid", id)` ou `("resource", id)`, comme `Config.label_target`)
  - `def switch_blocked(now: datetime, cfg: Config, dec: Decisions, snap: Snapshot, service: str, targets: Sequence[LabelTarget]) -> bool | None` : `None` si le service n'est géré pour aucune cible (interrupteur laissé tel quel) ; sinon `True` dès qu'une cible gérée le bloque.

Règles par cible :
- Ressource `rid` : gérée si `service in cfg.managed_services_for_resource(rid)` ; bloquée si `service in snap.resources[rid].blocked_services`.
- Enfant `kid` : gérée si `service in cfg.leisure_for(kid) | cfg.on_demand_for(kid)`. Base : bloqué si sur demande, ou si dans les loisirs et `snap.kids[kid].status is not KidStatus.AUTORISE`. Puis exceptions actives (`until` futur ou `None`, hors `snap.expired_exception_ids`), de la plus ancienne à la plus récente, la dernière gagne : celles dont `target.service == service` et qui visent l'enfant (`kid_id == kid`), un de ses appareils (`resource_id` d'une ressource dont il est propriétaire), ou tout le monde (ni enfant ni ressource). `open=True` débloque, `open=False` bloque.
- Cible inconnue (enfant ou ressource absents de la config) : ignorée.

- [ ] **Step 1: tests qui échouent** (`tests/core/test_label_services.py`) :
  - `test_resource_target_follows_blocked_services`
  - `test_kid_target_leisure_blocked_when_kid_not_autorise` et `..._open_when_autorise`
  - `test_kid_target_on_demand_always_blocked`
  - `test_kid_target_opened_by_exception_on_one_of_his_devices`
  - `test_kid_target_paused_blocks_leisure` (`dec.paused = True`)
  - `test_unmanaged_service_returns_none`
  - `test_any_target_blocking_wins` (enfant autorisé + ressource fermée → `True`)
  - `test_expired_exception_ignored`
- [ ] **Step 2:** FAIL. **Step 3:** implémenter. **Step 4:** `.venv/bin/pytest tests/core -v` → PASS.
- [ ] **Step 5:** commit `feat: état voulu des interrupteurs labellisés`.

### Task 4: Découverte et pilotage dans Home Assistant

**Files:**
- Create: `custom_components/parental_control/label_switches.py`
- Modify: `custom_components/parental_control/engine.py` (`_build`, `_apply`, écoute des registres, simulation)
- Test: `tests/ha/test_label_switches.py`

**Interfaces:**
- Consumes: `switch_blocked` (Task 3), `Config.label_services`, `Config.label_target`.
- Produces :
  - `@dataclass(frozen=True) class LabelSwitch: entity_id: str; service: str; on_means_allowed: bool; targets: tuple[LabelTarget, ...]`
  - `@dataclass(frozen=True) class LabelSwitchIssue: entity_id: str; service: str; problem: str` (`"no_target"`, `"unknown_label"`)
  - `def discover(hass: HomeAssistant, cfg: Config) -> tuple[list[LabelSwitch], list[LabelSwitchIssue]]` : entités du registre de domaine `switch`, non désactivées, portant un label de service déclaré ; cibles = leurs autres labels qui ciblent un enfant ou un appareil. Un `label_id` de `cfg.label_services` absent du registre des labels donne un `LabelSwitchIssue(problem="unknown_label")` (service ignoré).
  - `ParentalEngine.label_switches -> list[dict]` : pour le WebSocket, chaque interrupteur `{entity_id, name, service, targets, blocked, state}` plus les problèmes.

Comportement du moteur :
- `_build` appelle `discover`, ajoute les `entity_id` aux entités écoutées (dérive) et journalise chaque problème une fois.
- Abonnement à `er.EVENT_ENTITY_REGISTRY_UPDATED` et `lr.EVENT_LABEL_REGISTRY_UPDATED` : reconstruction puis évaluation.
- Dans `_apply`, après les ressources : pour chaque interrupteur, `switch_blocked(...)` ; `None` → rien ; sinon état voulu `on = blocked != on_means_allowed` ; `switch.turn_on`/`turn_off` si l'état diffère, avec le même mécanisme `_applied`/`_sent_at`/`DRIFT_COOLDOWN` que les ressources (clé par `entity_id`). Entité absente ou `unavailable` : rien, avertissement journalisé une fois après le démarrage (`ha_started`). Une erreur d'appel est journalisée sans arrêter les autres.
- Simulation : au lieu d'appeler, `_record_simulation` avec une ligne « <nom> : allumer (bloquer <service>) » ou l'équivalent.

- [ ] **Step 1: tests qui échouent** (`tests/ha/test_label_switches.py`, avec registres de labels et d'entités réels de `pytest-homeassistant-custom-component`) :
  - `test_discover_service_and_kid_target`
  - `test_discover_without_target_reports_issue`
  - `test_discover_unknown_label_reports_issue`
  - `test_engine_turns_switch_on_when_blocked` et `..._off_when_allowed`
  - `test_on_means_allowed_inverts`
  - `test_unmanaged_switch_untouched` (service dans aucune liste → aucun appel)
  - `test_drift_corrected_once_per_cooldown` (basculé à la main → un appel, pas un second avant `DRIFT_COOLDOWN`)
  - `test_unavailable_switch_no_crash`
  - `test_label_added_triggers_rebuild` (label posé après le démarrage → piloté sans recharger)
  - `test_simulation_records_without_calling`
- [ ] **Step 2:** FAIL. **Step 3:** implémenter. **Step 4:** `.venv/bin/pytest` → PASS.
- [ ] **Step 5:** commit `feat: pilotage des interrupteurs labellisés`.

### Task 5: Catalogue, WebSocket et messages

**Files:**
- Modify: `custom_components/parental_control/catalog.py`, `websocket.py`, `engine.py` (`_service_label`)
- Test: `tests/ha/test_websocket.py`, `tests/ha/test_requests.py`

**Interfaces:**
- Produces :
  - `services_catalog(hass, cfg: Config | None = None) -> dict[str, str]` : services AdGuard plus `label:<id>` → nom du label (registre), pour chaque label de service de `cfg` encore présent. Tri par nom inchangé.
  - Réponse de `parental_control/services/catalog` : `{"services": {...}, "label_services": ["label:…", …]}`.
  - Nouvelle commande `parental_control/labels/list` (parents) → `{"labels": [{"label_id", "name", "icon", "color"}]}` triés par nom.
  - Nouvelle commande `parental_control/label_switches/list` (parents) → `{"switches": [...], "issues": [...]}` (`ParentalEngine.label_switches`).

- [ ] **Step 1: tests qui échouent :** `test_catalog_includes_label_services` (nom du label, renommage pris en compte), `test_labels_list_parent_only` (non-parent → erreur `unauthorized`), `test_label_switches_list`, `test_request_message_uses_label_name` (message de demande « … Internet … »).
- [ ] **Step 2:** FAIL. **Step 3:** implémenter. **Step 4:** `.venv/bin/pytest tests/ha -v` → PASS.
- [ ] **Step 5:** commit `feat: services par label dans le catalogue et le WebSocket`.

### Task 6: Panneau Règles

**Files:**
- Modify: `custom_components/parental_control/www/panel.js`, `panel-lib.js`, `panel-kids.js`, `panel-devices.js`, `panel-style.js`
- Test: `tests/js/panel-lib.test.mjs`

**Interfaces:**
- Consumes: commandes de la Task 5.
- Produces (`panel-lib.js`) :
  - `toggleLabelService(cfg, labelId)` : ajoute `{label_id, on_means_allowed:false}` ou le retire ; refuse (retourne `false`, ne change rien) un label déjà `target_label`.
  - `setLabelInverted(cfg, labelId, inverted)`
  - `setTargetLabel(entity, labelId | null, cfg)` : refuse un label de service ou un label déjà cible d'un autre enfant ou appareil ; `null` retire.
  - `isLabelService(id)` (préfixe `label:`).

Interface :
- Onglet **Général** : carte « Services par label » : liste des labels HA, case « Service » et case « Allumé = autorisé » ; dessous, le récapitulatif « Interrupteurs pilotés » (`label_switches/list`) avec, par interrupteur, nom, service, cibles, état, et les problèmes (« sans cible », « label introuvable »).
- Onglets **Enfants** et **Appareils** : champ « Label de cible » (menu des labels HA qui ne sont pas des services, plus « Aucun »).
- Listes loisirs et sur demande : les services par label sont proposés via le catalogue, avec une classe CSS `label` sur la pastille pour un repère discret ; un service par label absent du catalogue s'affiche comme inconnu (comme aujourd'hui pour AdGuard).

- [ ] **Step 1: tests JS qui échouent** pour les quatre fonctions (cas : ajout, retrait, refus du cumul service/cible, refus d'une cible déjà prise, `null` retire).
- [ ] **Step 2:** `node --test tests/js/*.mjs` → FAIL. **Step 3:** implémenter fonctions et interface. **Step 4:** `node --test tests/js/*.mjs` et `.venv/bin/pytest tests/ha/test_frontend.py` → PASS.
- [ ] **Step 5:** commit `feat: réglages des services par label dans le panneau`.

### Task 7: Cartes, documentation et version

**Files:**
- Modify: `custom_components/parental_control/serialize.py`, `www/lib.js`, `README.md`, `manifest.json`
- Test: `tests/ha/test_entities.py` ou `tests/ha/test_websocket.py` (état sérialisé), `tests/js/lib.test.mjs`

**Interfaces:**
- Produces : dans l'état sérialisé, chaque ressource gagne `label_services: [service…]` (services des interrupteurs qui la ciblent), chaque enfant gagne `label_services: [{"service", "blocked"}]` (interrupteurs qui le ciblent, `blocked` d'après `switch_blocked`).
- `serviceToggles` (lib.js) : en plus d'AdGuard, une ressource montre les services sur demande présents dans ses `label_services`. `kidServiceToggles` : ajoute les services sur demande de l'enfant présents dans son `label_services`, `open = !blocked`. Le nom vient du catalogue de l'état (`serviceLabel`).

- [ ] **Step 1: tests qui échouent :** `test_state_exposes_label_services` (Python), `serviceToggles shows label service on non-AdGuard device` et `kidServiceToggles includes kid-targeted label service` (JS).
- [ ] **Step 2:** FAIL. **Step 3:** implémenter ; README : section « Services par label » (exemple UniFi : labels « Internet » et « Tablette de Maël », sens, cas ignorés) ; `manifest.json` version `0.4.0`.
- [ ] **Step 4:** `.venv/bin/pytest` et `node --test tests/js/*.mjs` → PASS.
- [ ] **Step 5:** commit `feat: services par label sur les cartes, documentation`.
