# Mode simulation et appareils logiques — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un mode simulation (le moteur décide sans piloter, et trace ce qu'il aurait fait), puis des
appareils logiques (Télé → appareils physiques → intégrations) dans le moteur, la config, les
cartes et le panneau Règles.

**Architecture:** la simulation est une enveloppe d'adaptateur unique dans le moteur, commandée par
un drapeau persistant de `Decisions`. Les appareils logiques gardent `Resource` (id stable) et lui
donnent `devices[].integrations[]` ; le moteur ne voit qu'un adaptateur composite par ressource, et
l'évaluateur passe de `resource.kind` aux capacités (`resource.has(kind)`).

**Tech Stack:** intégration Home Assistant en Python (pytest + pytest-homeassistant-custom-component),
front en JavaScript sans compilation (`node --test`).

**Spec:** `docs/superpowers/specs/2026-11-02-ha-parental-control-appareils-logiques-design.md`

## Global Constraints

- Dépôt : `/Users/olivier/dev/github.com/cesbron-dev/ha-parental-control`, travail sur une branche, jamais directement sur `main`.
- Tests Python : `.venv/bin/pytest -W error -q tests` ; tests JS : `node --test tests/js/*.test.mjs` (pas la forme répertoire, cassée sous Node 24). Les deux restent verts à chaque commit.
- Commits en français, terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Textes visibles en français ; commentaires de code en français, densité du code existant.
- Front : modules ES dans `custom_components/parental_control/www/`, logique pure dans un module testé (`lib.js`, `panel-lib.js`, `editor-lib.js`), sans dépendance.
- Ne jamais pousser, fusionner, redémarrer HA ni toucher la prod : le jalon après la tâche 5 et la fin se terminent par une question à Olivier.
- Ids de ressource inchangés partout (exceptions, usage, modes, entités HA s'y rattachent).

## Review Focus

1. Config v1 déjà stockée (instance de test) au redémarrage après mise à jour : chargée et convertie, mêmes ids, mêmes modes, exceptions en cours conservées, aucun changement de comportement. → test `test_v1_stored_config_upgrades_without_behavior_change` (tâche 6).
2. Intégration absente (Chromecast VPN débranché) dans un appareil mixte : les autres intégrations sont pilotées, l'absence est journalisée une fois. → test `test_missing_integration_does_not_stop_siblings` (tâche 7).
3. Simulation et dérive : une télé allumée pendant une plage fermée ne remplit pas le journal de bord toutes les 30 s. → test `test_simulation_logs_each_action_once` (tâche 3).
4. Sortie de simulation : l'état voulu est appliqué tout de suite à tout. → test `test_leaving_simulation_resyncs` (tâche 3).
5. Exception de service sur un appareil mixte : le service s'ouvre sur chaque client AdGuard et la télé n'est pas éteinte si l'appareil est ouvert. → test `test_service_exception_opens_every_adguard_client` (tâche 7).

---

## Partie A — mode simulation (modèle actuel)

### Task 1: Drapeau `simulation` persistant

**Files:**
- Modify: `custom_components/parental_control/core/decisions.py` (champ + `to_dict`/`from_dict`)
- Modify: `custom_components/parental_control/store.py` (`load`)
- Test: `tests/core/test_decisions.py`, `tests/ha/test_engine.py`

**Interfaces:**
- Produces: `Decisions.simulation: bool` (défaut dataclass `False`), sérialisé sous la clé `"simulation"` ; `from_dict` sans la clé → `False` (installation existante). `ParentalStore.load()` : si **ni config ni état** n'ont jamais été enregistrés (nouvelle installation), les décisions renvoyées ont `simulation=True`.

- [ ] **Step 1: tests** — `test_simulation_roundtrip` (`Decisions(simulation=True)` → `to_dict()["simulation"] is True` → `from_dict` rend `True`) ; `test_simulation_missing_key_is_false` (`from_dict` d'un dict sans la clé → `False`) ; dans `tests/ha/test_engine.py` : `test_new_install_starts_in_simulation` (`ParentalStore(hass).load()` sur stockage vide → `dec.simulation is True`) et `test_existing_install_not_in_simulation` (après `save_config`, `load()` → `False`).
- [ ] **Step 2:** lancer ces tests, ils échouent.
- [ ] **Step 3:** implémenter.
- [ ] **Step 4:** suites complètes vertes.
- [ ] **Step 5:** commit `feat: drapeau simulation persistant`.

### Task 2: Description des actions par les adaptateurs

**Files:**
- Modify: `custom_components/parental_control/adapters/base.py`, `media_player.py`, `adguard.py`, `nintendo.py`
- Test: `tests/ha/test_adapters.py`

**Interfaces:**
- Produces, sur chaque adaptateur (et dans le `Protocol`) :
  - `describe(desired: ResourceState) -> list[str]` : ce que `apply(desired)` ferait **maintenant**, sans rien appeler ; liste vide si rien.
  - `describe_grant(minutes: int) -> list[str]` (Nintendo ; les autres renvoient `[]`).
- Textes exacts (`<nom>` = nom de l'adaptateur, aujourd'hui `resource.name`) :
  - lecteur fermé et en usage : `"éteindrait <nom> (<entity_id>)"` ;
  - AdGuard : `"bloquerait <s1>, <s2> sur <nom>"` (services triés) quand des services passeraient bloqués, `"débloquerait <s1>, … sur <nom>"` quand des services passeraient débloqués (les deux lignes si les deux) ; calcul identique à celui d'`apply` (même lecture du capteur, mêmes `_extra_blocked`) ;
  - Nintendo : ce qu'`apply` écrirait sur `limit_entity`, ex. `"remettrait la limite de <nom> à 0 min"` ; `describe_grant(15)` → `["accorderait 15 min sur <nom>"]`.

- [ ] **Step 1: tests** — pour chaque adaptateur, au moins : un cas où `describe` renvoie le texte exact ci-dessus, un cas où il renvoie `[]`, et la preuve qu'aucun service HA n'a été appelé (`calls` vide).
- [ ] **Step 2:** tests en échec.
- [ ] **Step 3:** implémenter ; factoriser avec `apply` (une méthode privée qui calcule l'action, utilisée par `apply` et `describe`) plutôt que dupliquer.
- [ ] **Step 4:** suites vertes.
- [ ] **Step 5:** commit `feat: les adaptateurs décrivent leurs actions`.

### Task 3: Simulation dans le moteur

**Files:**
- Create: `custom_components/parental_control/adapters/simulation.py`
- Modify: `custom_components/parental_control/engine.py`, `manifest.json` (`after_dependencies` + `"logbook"`)
- Test: `tests/ha/test_engine.py`

**Interfaces:**
- Consumes: `describe`, `describe_grant` (tâche 2), `Decisions.simulation` (tâche 1).
- Produces:
  - `class SimulatedAdapter` (même contrat `Adapter`) : `SimulatedAdapter(inner: Adapter, active: Callable[[], bool], record: Callable[[str, str], None])`. Si `active()` est faux, chaque appel passe à `inner`. Sinon `apply`/`force_close`/`grant`/`warn` n'appellent pas `inner` ; ils calculent les lignes (`inner.describe(desired)`, `describe` d'un état fermé pour `force_close`, `describe_grant`, `"afficherait « <message> » sur <nom>"` pour `warn`) et appellent `record(resource_name, ligne)` pour chacune. `entity_ids`, `in_use`, `drifted` passent toujours à `inner`. Dédoublonnage : une ligne n'est enregistrée que si elle diffère de la précédente ligne enregistrée pour ce même adaptateur ; `reset()` vide cette mémoire.
  - `ParentalEngine._build` enveloppe chaque adaptateur ; `record` écrit `homeassistant.components.logbook.async_log_entry(hass, name, f"Simulation : {ligne}", domain=DOMAIN)` et `_LOGGER.info`.
  - `ParentalEngine.simulation -> bool` (propriété) et `async set_simulation(on: bool) -> None` : met à jour `decisions.simulation` ; en passant à `False`, vide `_applied`, `_sent_at` et la mémoire des enveloppes (`reset()`), puis `async_evaluate("simulation")` (resynchronisation) ; en passant à `True`, `async_evaluate("simulation")`.
  - `_send_notify` : en simulation, message préfixé `"[Simulation] "`.
  - `add_bonus` Nintendo passe par l'enveloppe (rien n'est accordé en simulation).

- [ ] **Step 1: tests** (même style que les tests existants, fixture `services`) :
  - `test_simulation_does_not_touch_devices` : en simulation, mardi 16:00 (comme `test_tick_turns_off_tv_at_16`) → aucun `media_player.turn_off`, aucun appel AdGuard, aucun `number.set_value` ; le snapshot dit la TV fermée ; une entrée de journal de bord `"Simulation : éteindrait Télé salon (media_player.tv_salon)"` (capturer l'événement `logbook_entry`).
  - `test_simulation_logs_each_action_once` : TV rallumée à répétition pendant 3 min fermées → une seule entrée « éteindrait ».
  - `test_leaving_simulation_resyncs` : en simulation, TV allumée en plage fermée ; `set_simulation(False)` → `turn_off` envoyé immédiatement.
  - `test_simulation_prefixes_parent_notifications` : notification parent reçue avec message commençant par `"[Simulation] "`.
  - `test_simulation_nintendo_bonus_not_granted` : `add_bonus` Switch en simulation → aucun appel `add_bonus_time`, entrée « accorderait 15 min sur Switch ».
- [ ] **Step 2:** tests en échec.
- [ ] **Step 3:** implémenter.
- [ ] **Step 4:** suites vertes.
- [ ] **Step 5:** commit `feat: mode simulation du moteur`.

### Task 4: Interrupteur « Simulation » et état WebSocket

**Files:**
- Modify: `custom_components/parental_control/switch.py`, `serialize.py`, `strings.json`, `translations/fr.json`, `translations/en.json`
- Test: `tests/ha/test_entities.py`, `tests/ha/test_websocket.py`

**Interfaces:**
- Produces: `SimulationSwitch(GlobalEntity, SwitchEntity)`, clé `"simulation"`, unique_id `f"{entry.entry_id}_global_simulation"`, `is_on` = `engine.simulation`. **Activer** la simulation (cela cesse de piloter, donc ouvre tout de fait) exige le code d'un non-admin (`await self._check_unlock()` dans `async_turn_on`) ; la **désactiver** ne demande rien — l'inverse de « Pause ». Nom : fr « Simulation », en « Simulation ».
- `serialize_snapshot` : clé racine `"simulation": engine.decisions.simulation` (toujours, pas seulement en `display`).

- [ ] **Step 1: tests** — interrupteur présent et reflète l'état ; `turn_off` par un utilisateur non admin sans code passe ; `turn_on` non admin sans code est refusé (même mécanisme que les tests de « Pause ») ; `parental_control/state` contient `simulation`.
- [ ] **Step 2:** tests en échec. **Step 3:** implémenter. **Step 4:** suites vertes.
- [ ] **Step 5:** commit `feat: interrupteur Simulation`.

### Task 5: Simulation visible dans les cartes et le panneau

**Files:**
- Modify: `www/lib.js`, `www/style.js` (style du badge), `www/resource-card.js`, `www/switch-card.js`, `www/timeline-card.js`, `www/panel.js`, `README.md`
- Test: `tests/js/lib.test.mjs`

**Interfaces:**
- Produces: `simulationBadge(state) -> string` dans `lib.js` : `'<span class="sim">SIMULATION</span>'` si `state?.simulation`, sinon `""`. Chaque carte l'affiche dans son en-tête. Le panneau s'abonne à l'état (`subscribeState` de `connection.js`) et, si `simulation`, affiche en tête le bandeau exact `Simulation — aucun appareil n'est piloté`.
- README : section « Mode simulation » (interrupteur, journal de bord, nouvelle installation en simulation, code pour l'activer depuis un compte non admin).

- [ ] **Step 1: test** `simulationBadge` (vrai, faux, état nul).
- [ ] **Step 2–4:** échec, implémentation, suites vertes ; vérifier les cartes et le panneau dans les pages de démo `.superpowers/demo-cartes/*.html` (ajouter `simulation: true` à l'état simulé) avec le navigateur intégré.
- [ ] **Step 5:** commit `feat: simulation visible dans les cartes et le panneau`.

**Jalon :** la partie A est livrable seule. Le contrôleur s'arrête et demande à Olivier s'il faut fusionner, pousser et déployer sur l'instance de test avant la partie B.

---

## Partie B — appareils logiques

### Task 6: Modèle et configuration v2

**Files:**
- Modify: `core/model.py`, `core/config_io.py`
- Test: `tests/core/test_config_io.py`, `tests/ha/test_engine.py`

**Interfaces:**
- Produces (`core/model.py`) :
  - `Integration(kind: ResourceKind, options: Mapping[str, Any])` (frozen) ;
  - `PhysicalDevice(name: str, integrations: tuple[Integration, ...])` (frozen) ;
  - `Resource(id, name, owners, devices: tuple[PhysicalDevice, ...], quota_minutes, icon: str | None = None)` ; propriétés `integrations -> tuple[Integration, ...]` (aplaties, ordre de la config), `kinds -> frozenset[ResourceKind]`, `has(kind) -> bool`, `kind -> ResourceKind` **déduit** (`NINTENDO` si présent, sinon `MEDIA_PLAYER` si présent, sinon `ADGUARD`) ; propriété de transition `options` = options de la première intégration (retirée en tâche 7).
- `config_io` : `CONFIG_VERSION = 2`. `parse_config` accepte `version` 1 (chaque ressource plate → un appareil physique du même nom, une intégration du même `kind` et des mêmes options) et 2. Validation v2 (chemins d'erreur exacts) : `resources[i].devices` liste ; `resources[i].devices[j].name` texte ; `resources[i].devices[j].integrations[k].kind` et ses options obligatoires (`_REQUIRED_OPTIONS` actuels) ; au moins une intégration dans la ressource → erreur sur `resources[i].devices` « au moins une intégration » ; Nintendo : si une intégration est Nintendo, elle doit être la seule de la ressource → erreur sur `resources[i].devices` « une console Nintendo ne se regroupe pas ». `dump_config` écrit toujours du v2 (`icon` seulement s'il est défini).

- [ ] **Step 1: tests** — conversion v1→v2 (forme exacte du dump pour la TV de `EX`) ; parse d'une Télé mixte (Samsung : lecteur + AdGuard ; Google TV : lecteur + 2 AdGuard) → `kinds == {MEDIA_PLAYER, ADGUARD}`, `kind is MEDIA_PLAYER`, 5 intégrations ; refus Nintendo mélangé, refus deux Nintendo, refus zéro intégration, appareil physique vide accepté si un autre a une intégration ; aller-retour `dump_config`/`parse_config` ; version 3 refusée. `test_v1_stored_config_upgrades_without_behavior_change` (moteur) : config `EX` stockée en v1 (écrire directement `hass_storage`), démarrage, mêmes ids et même état qu'avant, et `config/get` renvoie du v2.
- [ ] **Step 2–4:** échec, implémentation, suites vertes (le code existant continue de marcher via `kind` et `options` de transition).
- [ ] **Step 5:** commit `feat: configuration v2 à appareils physiques et intégrations`.

### Task 7: Adaptateur composite

**Files:**
- Create: `custom_components/parental_control/adapters/composite.py`
- Modify: `adapters/__init__.py`, `adapters/media_player.py`, `adapters/adguard.py`, `adapters/nintendo.py`, `engine.py`, `core/model.py` (retrait de `options`)
- Test: `tests/ha/test_adapters.py`, `tests/ha/test_engine.py`

**Interfaces:**
- Consumes: `Resource.integrations`, `PhysicalDevice` (tâche 6) ; `describe`/`describe_grant` (tâche 2) ; `SimulatedAdapter` (tâche 3).
- Produces:
  - les trois adaptateurs prennent `(hass, label: str, options: Mapping[str, Any])` (+ `leisure` pour AdGuard) au lieu d'une `Resource` ; `label` = `"<appareil physique> (<entity_id>)"` pour un lecteur, `"<appareil physique>"` sinon — c'est le `<nom>` des textes de la tâche 2 ;
  - `CompositeAdapter(resource: Resource, members: list[Adapter])` : `entity_ids` = union ; `in_use` = un membre lecteur en usage ; `drifted` = un membre ; `apply`/`warn`/`force_close` = chaque membre dans un `try` séparé (une erreur est journalisée avec le label, les autres continuent) ; `describe` = concaténation ; `grant`/`describe_grant` = le membre Nintendo ; propriété `nintendo -> NintendoAdapter | None` ; `resource` exposé ;
  - `build_adapter(hass, resource, leisure) -> CompositeAdapter` ;
  - `engine._with_nintendo_sensors` utilise `adapter.nintendo` (plus d'`isinstance` sur l'adaptateur de ressource) ; l'enveloppe de simulation enveloppe le composite.
- Les textes de simulation passent au niveau intégration (ex. `"éteindrait Samsung (media_player.tv_salon)"`, `"bloquerait roblox, youtube sur Chromecast (VPN)"`) ; ajuster les attentes des tests de la tâche 3 en conséquence.

- [ ] **Step 1: tests** — `test_mixed_tv_closes_every_member` (Télé : Samsung lecteur + AdGuard, Google TV lecteur + 2 AdGuard, avec `FakeAdGuard` multi-appareils si besoin) : fermée → deux `turn_off`, trois écritures AdGuard ; `test_missing_integration_does_not_stop_siblings` ; `test_service_exception_opens_every_adguard_client` ; `in_use` vrai si un seul lecteur joue.
- [ ] **Step 2–4:** échec, implémentation, suites vertes (adapter les fabriques de `tests/ha/test_adapters.py` au nouveau constructeur).
- [ ] **Step 5:** commit `feat: un adaptateur composite par appareil logique`.

### Task 8: Évaluateur par capacités et quota de repli

**Files:**
- Modify: `core/evaluator.py`, `engine.py` (`_check_target`, `add_bonus`), `sensor.py`, `binary_sensor.py`
- Test: `tests/core/test_evaluator_quota.py`, `tests/core/test_evaluator_access.py`, `tests/ha/test_entities.py`

**Interfaces:**
- Remplacer chaque `resource.kind is X` par `resource.has(X)` (services : `has(ADGUARD)` ; compteur et budget d'appareil : `has(MEDIA_PLAYER)` ; Nintendo : `has(NINTENDO)`). `sensor.py` : capteurs de durée si `has(MEDIA_PLAYER) or has(NINTENDO)` ; `binary_sensor.py` : attribut `blocked_services` si `has(ADGUARD)`.
- Quota de repli (décision d'Olivier) : pour un appareil avec lecteur, le budget du compteur d'un enfant est `_resource_budget(...)` si `quota_minutes` définit le type de jour, sinon `_kid_budget(kid, …)` + bonus de ressource du jour (`dec.bonus_minutes(today, resource_id=…)`), `None` si l'enfant n'a pas de quota ; le reste affiché garde `max(budgets) - usage` (la plus généreuse). Le compteur reste `dec.usage(resource.id, …)`.

- [ ] **Step 1: tests** — `test_tv_without_device_quota_uses_most_generous_kid_quota` (samedi, TV sans `quota_minutes` pour `fin_de_semaine`, Gabin 120 min, Léo 60 min → `remaining_minutes == 120 - usage`, fermeture quand l'usage atteint 120) ; `test_tv_without_any_quota_is_unlimited` ; `test_device_quota_still_wins` (180 min d'appareil) ; `test_mixed_device_blocks_leisure_when_closed` (`blocked_services` non vide sur la Télé mixte fermée) ; `test_adguard_only_device_unchanged` (budget de l'enfant comme avant) ; capteurs de durée créés pour la Télé mixte, `blocked_services` en attribut.
- [ ] **Step 2–4:** échec, implémentation, suites vertes ; les tests existants qui supposaient « TV sans quota = illimitée » alors que l'enfant a un quota sont mis à jour en citant la décision d'Olivier dans le commit.
- [ ] **Step 5:** commit `feat: règles par capacités et quota de repli de l'appareil`.

### Task 9: État affiché et cartes

**Files:**
- Modify: `serialize.py`, `www/resource-card.js`, `www/editor-lib.js`, `README.md`
- Test: `tests/ha/test_websocket.py`, `tests/js/lib.test.mjs`, `tests/js/editor-lib.test.mjs`

**Interfaces:**
- `_add_display`, par ressource : `kind` (déduit), `kinds` (liste triée des valeurs), `icon` (ou `null`) ; pour Nintendo `used_entity`/`remaining_entity` lus sur l'intégration Nintendo.
- `resource-card.js` : icône = `config.icon` || `state.icon` || icône par `kind` ; « Autoriser un service » proposé si `kinds` contient `adguard_services` (aujourd'hui décidé par `kind`). Garder `lib.js` pur : y ajouter `resourceView(...).kinds` et `.icon`.
- `editor-lib.js` : libellé de la liste = nom seul ; `(Télé)`/`(AdGuard)` seulement pour un appareil à un seul type.

- [ ] **Step 1: tests** — payload WebSocket de la Télé mixte (`kind == "media_player"`, `kinds == ["adguard_services","media_player"]`) ; `resourceView` expose `kinds`/`icon` ; libellés de l'éditeur.
- [ ] **Step 2–4:** échec, implémentation, suites vertes.
- [ ] **Step 5:** commit `feat: cartes pour les appareils logiques`.

### Task 10: Opérations d'arbre du brouillon (panel-lib)

**Files:**
- Modify: `www/panel-lib.js`
- Test: `tests/js/panel-lib.test.mjs`

**Interfaces (toutes modifient le brouillon en place, forme `config/get` v2) :**
- `addResource(cfg, name)` → ressource `{id, name, owners: [], quota_minutes: {}, devices: [{name, integrations: []}]}` (remplace la version à `kind`) ;
- `addDevice(resource, name)` ; `removeDevice(resource, index)` ;
- `addIntegration(device, kind)` → `{kind, ...options vides}` selon `KINDS[].options` ; `removeIntegration(device, index)` ;
- `integrationKindsAllowed(resource) -> string[]` : types ajoutables ; si la ressource a une Nintendo → `[]` ; si elle a autre chose → sans `nintendo` ; vide → tous ;
- `moveDevice(cfg, fromIndex, deviceIndex, toIndex) -> string | null` : déplace l'appareil physique ; si la ressource source n'a plus d'appareil, elle est retirée via `removeResource` et son id est renvoyé (sinon `null`) ;
- `removeResource` inchangé (retire les modes).

- [ ] **Step 1: tests** — chaque fonction, dont : déplacer le dernier appareil de `tv_adguard` sous `tv` renvoie `"tv_adguard"`, retire la ressource et ses modes ; `integrationKindsAllowed` sur ressource vide, mixte, Nintendo.
- [ ] **Step 2–4:** échec, implémentation, suites vertes.
- [ ] **Step 5:** commit `feat: opérations d'arbre du brouillon`.

### Task 11: Arbre de l'onglet Appareils

**Files:**
- Modify: `www/panel.js`, `.superpowers/demo-cartes/panel.html` (démo locale, non versionnée)

**Interfaces:**
- Consumes: tâche 10.
- Maquette A de la spec : par appareil logique, en-tête (icône, nom, enfants, nombre d'intégrations) et réglages actuels (nom, icône `ha-icon-picker` ou texte `mdi:`, enfants, quota par type de jour) ; niveau 2 appareils physiques (nom, « Déplacer vers… » = `<select>` des autres appareils logiques, supprimer) ; niveau 3 intégrations (type, réglages par type comme aujourd'hui, supprimer, pastille verte si `entity_id` est dans `hass.states` ou si `device_id` est dans la liste des appareils chargée, rouge sinon) ; liens « + Ajouter une intégration » (types de `integrationKindsAllowed`), « + Ajouter un appareil physique », « + Ajouter un appareil ».
- Quand `moveDevice` renvoie un id, le bandeau du brouillon annonce : `« <nom> » sera supprimé à l'enregistrement : ses autorisations en cours et son temps du jour sont perdus.`
- Conserver les règles d'édition existantes : les saisies texte ne redessinent que l'en-tête ; ids neufs modifiables jusqu'à l'enregistrement.

- [ ] **Step 1:** mettre à jour `panel.html` avec une Télé mixte et une ressource `tv_adguard` séparée.
- [ ] **Step 2:** implémenter ; vérifier dans le navigateur intégré : arbre, ajout/suppression, déplacement de `tv_adguard` sous la Télé avec le bandeau, pastilles, enregistrement (le faux `config/set` reçoit du v2).
- [ ] **Step 3:** suites vertes.
- [ ] **Step 4:** commit `feat: arbre des appareils dans le panneau Règles`.

### Task 12: Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** section « Appareils logiques » (les trois niveaux, exemple JSON v2 de la Télé, conversion automatique de la v1, règles Nintendo, quota de repli) ; mettre à jour les exemples de config du README en v2.
- [ ] **Step 2:** commit `docs: appareils logiques`.

**Fin :** le contrôleur demande à Olivier s'il faut fusionner, pousser et déployer sur l'instance de test.
