# Parents non administrateurs — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un compte HA non administrateur, propriétaire mémorisé d'un téléphone de `request_notify`, agit sans code, ouvre le panneau « Règles » et répond aux demandes ; les autres comptes n'ont rien de plus.

**Architecture:** Un module `parents.py` centralise « qui est parent » (propriétaire mémorisé == propriétaire actuel du téléphone, ou administrateur). Le modèle `Config` gagne `request_notify_owners` (téléphone → user_id), rempli **par le serveur** à l'enregistrement et une fois à la migration. Tous les contrôles serveur (code, services, entités, WebSocket, panneau) passent par ce module ; les cartes et le panneau apprennent leur statut par une commande WebSocket `whoami`.

**Tech Stack:** Python 3.14 / Home Assistant 2026.11 (pytest-homeassistant-custom-component), JS vanilla (tests `node --test`).

**Spec:** `docs/superpowers/specs/2026-11-08-ha-parental-control-parents-design.md`

## Global Constraints

- Branche `feat/parents-non-admin` ; messages de commit en français, terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tests Python : `.venv/bin/pytest` (toute la suite doit rester verte). Tests JS : `node --test tests/js/`.
- Chaque contrôle se fait **côté serveur** ; cacher un bouton n'est jamais une protection.
- Le propriétaire d'un téléphone est **déterminé par le serveur** ; une valeur `request_notify_owners` envoyée par un client (WebSocket, service d'import) est ignorée.
- Un téléphone ne donne de droits que si le propriétaire **actuel** de l'appareil `mobile_app` de ce nom est **unique** et **égal** au propriétaire mémorisé — pour les droits de parent **et** pour la réponse aux demandes.
- « Est parent » = administrateur HA **ou** propriétaire de confiance d'un téléphone. « Peut répondre à une demande » = propriétaire de confiance d'un téléphone **seulement** (un admin sans téléphone listé ne répond pas, comme aujourd'hui).
- Appel sans `user_id` (automatisation, système) : pas de code, inchangé.
- Statut évalué à chaque appel depuis la configuration courante (retrait d'un téléphone = perte immédiate du droit).
- Ancien format (pas de `request_notify_owners`) toujours accepté au chargement.
- Ne pas affaiblir : verrouillage après codes faux, jeton secret des notifications, revérification de chaque réponse.

## Review Focus

1. Appareil `mobile_app` supprimé puis recréé sous le même nom par un autre compte → ni droits de parent ni réponse aux demandes (Task 2).
2. Client qui envoie `request_notify_owners` forgé dans `config/set` ou `importer_configuration` → ignoré, propriétaire recalculé (Task 4).
3. Non-parent non admin qui appelle `config/get` / `config/set` / `services/catalog` directement → `unauthorized`, aucune donnée de configuration renvoyée (Task 4).
4. Ajout d'un téléphone sans appareil ou avec deux appareils de ce nom → enregistrement refusé avec une erreur qui nomme le téléphone ; la configuration en place reste intacte (Task 4).
5. Cible non `mobile_app` dans `request_notify` (ex. `notify.famille`) → acceptée, ne donne aucun droit, pas d'erreur (Task 2).

---

### Task 1: Modèle et format — `request_notify_owners`

**Files:**
- Modify: `custom_components/parental_control/core/model.py` (classe `Config`)
- Modify: `custom_components/parental_control/core/config_io.py` (`parse_config`, `dump_config`)
- Test: `tests/core/test_config_io.py`

**Interfaces:**
- Produces: `Config.request_notify_owners: Mapping[str, str] = field(default_factory=dict)` — clé = cible complète `notify.mobile_app_<x>`, valeur = `user_id`. JSON : clé `"request_notify_owners"` (objet), omise ⇒ `{}`.

- [ ] **Step 1: Tests** — `test_request_notify_owners_round_trip` (parse puis dump conserve `{"notify.mobile_app_ipad": "u1"}`), `test_request_notify_owners_absent_defaults_empty` (ancien JSON sans la clé ⇒ `{}`), `test_request_notify_owners_unknown_target_rejected` (clé absente de `request_notify` ⇒ `ConfigError` dont le chemin commence par `request_notify_owners`), `test_request_notify_owners_empty_user_rejected` (valeur `""` ⇒ `ConfigError`).
- [ ] **Step 2:** `.venv/bin/pytest tests/core/test_config_io.py -k owners -v` → FAIL.
- [ ] **Step 3:** Ajouter le champ (après `request_notify`), le parser avec les helpers existants (`_expect_dict`, `_str`, `_fail`), le sérialiser dans `dump_config` après `request_notify`. Mettre à jour le gabarit vide de `www/panel-lib.js` (`request_notify_owners: {}`).
- [ ] **Step 4:** `.venv/bin/pytest tests/core -v` et `node --test tests/js/` → PASS.
- [ ] **Step 5:** Commit `feat: propriétaires mémorisés des téléphones de demandes dans la configuration`.

### Task 2: Module `parents.py` — qui est parent

**Files:**
- Create: `custom_components/parental_control/parents.py`
- Modify: `custom_components/parental_control/request_listener.py` (supprimer `parent_user_ids`, utiliser `trusted_phone_owners`)
- Modify: `custom_components/parental_control/websocket.py` (`_is_parent` → `trusted_phone_owners`)
- Test: `tests/ha/test_parents.py` (nouveau) ; adapter `tests/ha/test_requests.py` (les 3 tests de `parent_user_ids` migrent vers `trusted_phone_owners`)

**Interfaces:**
- Consumes: `Config.request_notify_owners` (Task 1).
- Produces:
  - `current_phone_owners(hass, targets: Iterable[str]) -> dict[str, list[str]]` — cible `notify.mobile_app_<slug(device_name)>` → liste des `user_id` des entrées `mobile_app` de ce nom (cibles non mobile_app absentes du résultat).
  - `trusted_phone_owners(hass, cfg: Config | None) -> set[str]` — `user_id` mémorisés dont le propriétaire actuel est unique et identique ; journalise l'avertissement « plusieurs appareils » existant.
  - `async is_parent(hass, cfg: Config | None, user_id: str | None) -> bool` — `user_id is None` ⇒ `False` (l'appelant gère le cas système) ; admin ⇒ `True` ; sinon `user_id in trusted_phone_owners`.
  - `phone_status(hass, cfg: Config) -> dict[str, dict]` — pour chaque cible mobile_app : `{"owner": user_id | None, "status": "ok" | "unbound" | "missing" | "changed" | "ambiguous"}` (`unbound` = pas de propriétaire mémorisé ; `missing` = aucun appareil ; `changed` = propriétaire actuel différent ; `ambiguous` = plusieurs appareils).
  - `bind_owners(hass, new: Config, old: Config | None, rebind: Iterable[str] = ()) -> Config` — part des propriétaires de `old` (jamais de `new`) pour les cibles conservées et hors `rebind` ; pour les autres cibles mobile_app, propriétaire actuel unique, sinon `ConfigError(f"request_notify : {cible} — appareil introuvable ou en double")` ; cibles non mobile_app sans propriétaire ; renvoie `dataclasses.replace(new, request_notify_owners=...)`.

- [ ] **Step 1: Tests** (`tests/ha/test_parents.py`, avec de vraies entrées `MockConfigEntry(domain="mobile_app", data={"device_name": ..., "user_id": ...})` et des utilisateurs `hass.auth`):
  - `test_trusted_owner_matches` ; `test_device_recreated_by_other_user_not_trusted` (Review Focus 1) ; `test_ambiguous_device_not_trusted` ; `test_unbound_phone_not_trusted` ; `test_non_mobile_app_target_ignored` (Review Focus 5) ;
  - `test_is_parent_admin_without_phone` → True ; `test_is_parent_none_user` → False ; `test_is_parent_removed_phone` (cible retirée de la config ⇒ False) ;
  - `test_phone_status_each_state` (les 5 statuts) ;
  - `test_bind_owners_keeps_old_owner`, `test_bind_owners_ignores_client_owner` (`new` porte un faux propriétaire ⇒ remplacé), `test_bind_owners_rebind`, `test_bind_owners_missing_device_raises` (message contient la cible), `test_bind_owners_non_mobile_target`.
  - Dans `test_requests.py` : `test_answer_from_recreated_device_refused` (notification d'un appareil recréé par un autre compte ⇒ réponse ignorée).
- [ ] **Step 2:** `.venv/bin/pytest tests/ha/test_parents.py tests/ha/test_requests.py -v` → FAIL.
- [ ] **Step 3:** Implémenter `parents.py` (reprendre la logique de `parent_user_ids`) ; brancher `request_listener` et `websocket._is_parent` sur `trusted_phone_owners(hass, cfg)`.
- [ ] **Step 4:** `.venv/bin/pytest` → toute la suite PASS.
- [ ] **Step 5:** Commit `feat: parents reconnus par propriétaire mémorisé du téléphone`.

### Task 3: Migration des configurations existantes

**Files:**
- Modify: `custom_components/parental_control/parents.py` (ajout)
- Modify: `custom_components/parental_control/__init__.py` (`async_setup_entry`, après `engine.async_start()`)
- Test: `tests/ha/test_parents.py`

**Interfaces:**
- Consumes: `current_phone_owners`, `ParentalEngine.config`, `ParentalEngine.set_config`.
- Produces: `async migrate_phone_owners(hass, engine) -> None` — pour chaque cible mobile_app **sans** propriétaire mémorisé et dont le propriétaire actuel est unique : l'associer, `_LOGGER.info("Téléphone %s associé à l'utilisateur %s", cible, nom)` ; enregistre via `engine.set_config` seulement si quelque chose a changé ; ne touche jamais une cible déjà associée.

- [ ] **Step 1: Tests** — `test_migration_binds_unique_owner` (+ journal), `test_migration_skips_ambiguous_and_missing`, `test_migration_keeps_existing_owner`, `test_migration_noop_does_not_save`, `test_setup_entry_runs_migration` (config stockée à l'ancien format ⇒ après setup, `engine.config.request_notify_owners` rempli).
- [ ] **Step 2:** FAIL. **Step 3:** implémenter, appeler dans `async_setup_entry`. **Step 4:** `.venv/bin/pytest` PASS.
- [ ] **Step 5:** Commit `feat: association des téléphones existants à la mise à jour`.

### Task 4: Contrôles serveur — code, services, entités, WebSocket, panneau

**Files:**
- Modify: `security.py` (`check_unlock`), `entity.py` (`_check_unlock`), `services.py` (`unlock`, `import_config`), `websocket.py` (`config/get`, `config/set`, `services/catalog`, nouveau `whoami`), `frontend.py` (panneau « Règles » `require_admin=False`)
- Test: `tests/ha/test_config_flow.py`, `tests/ha/test_services.py`, `tests/ha/test_entities.py`, `tests/ha/test_websocket.py`, `tests/ha/test_frontend.py`

**Interfaces:**
- Consumes: `is_parent`, `bind_owners`, `phone_status` (Task 2).
- Produces:
  - `check_unlock(hass, context, code, stored_hash, cfg: Config | None) -> None` — pas de code si `user_id is None` ou `await is_parent(hass, cfg, user_id)`.
  - WebSocket `parental_control/whoami` → `{"admin": bool, "parent": bool, "user_id": str}` (ouvert à tous).
  - `config/get`, `config/set`, `services/catalog` : réservés à `is_parent` ; sinon `send_error(id, "unauthorized", "Réservé aux parents")`.
  - `config/get` renvoie en plus `"phones": phone_status(...)`.
  - `config/set` accepte `vol.Optional("rebind", default=[]): [str]` ; applique `bind_owners(hass, cfg, engine.config, rebind)` avant `engine.set_config` ; une `ConfigError` ⇒ `invalid_config` et la configuration en place est intacte.
  - `importer_configuration` : autorisé à un parent (`Unauthorized` inchangé pour les autres) ; applique `bind_owners(hass, cfg, engine.config)`.

- [ ] **Step 1: Tests** — pour chaque point (code via service, bouton Devoirs, arrêt de pause, activation de simulation, import, `config/get`, `config/set`, `services/catalog`) : parent non admin accepté sans code, non-parent non admin refusé/code exigé, admin inchangé. Plus :
  - `test_check_unlock_parent_loses_right_when_phone_removed` ;
  - `test_config_set_ignores_forged_owners` (Review Focus 2) ; `test_import_ignores_forged_owners` ;
  - `test_config_get_non_parent_gets_no_config` (Review Focus 3) ;
  - `test_config_set_missing_device_rejected_config_unchanged` (Review Focus 4) ;
  - `test_config_set_rebind` ; `test_config_get_includes_phone_status` ;
  - `test_whoami` (admin, parent, enfant) ;
  - `test_rules_panel_not_admin_only` (`require_admin` False dans l'enregistrement du panneau).
- [ ] **Step 2:** FAIL. **Step 3:** implémenter (un seul helper `_require_parent(hass, connection, msg, engine) -> bool` dans `websocket.py`). **Step 4:** `.venv/bin/pytest` PASS.
- [ ] **Step 5:** Commit `feat: droits de parent pour les comptes non administrateurs`.

### Task 5: Cartes — pas de code ni de « Demander » pour un parent

**Files:**
- Modify: `www/lib.js` (`needsCode`, `canRequest`), `www/connection.js` (`fetchWhoami`), `www/card-base.js`, `www/kid-card.js`, `www/resource-card.js`, `www/switch-card.js`, `www/style.js`, `www/dialogs.js` (appels de `needsCode`/`canRequest`)
- Test: `tests/js/lib.test.mjs`, `tests/js/connection.test.mjs`

**Interfaces:**
- Consumes: WebSocket `parental_control/whoami` (Task 4).
- Produces:
  - `needsCode(hass, action, parent = false)` : `false` si admin **ou** `parent` ; sinon règle actuelle.
  - `canRequest(hass, state, parent = false)` : `false` si admin ou `parent`.
  - `fetchWhoami(hass) -> Promise<{admin, parent, user_id} | null>` dans `connection.js` : résultat mis en cache par `hass.connection` pendant 60 s (deux appels rapprochés = une seule requête ; au-delà, nouvelle requête) ; erreur ⇒ `null` (traité comme non-parent).
  - `card-base.js` : propriété `this._parent` (booléen, `false` tant que inconnu), re-rendu quand elle change ; toutes les cartes passent `this._parent` à `needsCode`/`canRequest`.

- [ ] **Step 1: Tests** — `needsCode` (admin, parent, enfant × actions), `canRequest` (parent ⇒ false même si `requests_enabled`), `fetchWhoami` (une seule requête pour deux appels sur la même connexion ; erreur ⇒ `null`).
- [ ] **Step 2:** FAIL. **Step 3:** implémenter. **Step 4:** `node --test tests/js/` et `.venv/bin/pytest` PASS.
- [ ] **Step 5:** Commit `feat: les cartes reconnaissent les parents non administrateurs`.

### Task 6: Panneau « Règles » — accès, statut des téléphones, réassociation

**Files:**
- Modify: `www/panel.js`, `www/panel-lib.js`
- Test: `tests/js/panel-lib.test.mjs`

**Interfaces:**
- Consumes: `whoami`, `config/get` (`phones`), `config/set` (`rebind`) (Task 4).
- Produces (fonctions pures de `panel-lib.js`) :
  - `phoneBadge(status) -> {label, tone}` : `ok` → « Associé » ; `unbound` → « À associer » ; `missing` → « Appareil introuvable » ; `changed` → « Changé de compte » ; `ambiguous` → « Nom en double ».
  - `losesParentOnSave(draft, phones, userId, isAdmin) -> boolean` : vrai si l'utilisateur non admin n'aura plus aucun téléphone `ok` à son nom dans `draft.request_notify`.
- Comportement : au chargement, `whoami` ; non-parent ⇒ seul le message « Réservé aux parents » (aucun appel `config/get` ni `services/catalog`). Parent ⇒ panneau actuel ; chaque pastille de `request_notify` affiche `phoneBadge` ; un bouton « Réassocier » sur les statuts autres que `ok` ajoute la cible à `draft.rebind` (envoyé à `config/set`, jamais stocké dans la configuration) ; avant « Enregistrer », si `losesParentOnSave` ⇒ confirmation « Vous ne serez plus parent après l'enregistrement. Continuer ? ».

- [ ] **Step 1: Tests** de `phoneBadge` (5 statuts) et `losesParentOnSave` (admin ⇒ false ; dernier téléphone retiré ⇒ true ; autre téléphone `ok` restant ⇒ false ; téléphone restant `changed` ⇒ true).
- [ ] **Step 2:** FAIL. **Step 3:** implémenter. **Step 4:** `node --test tests/js/` PASS.
- [ ] **Step 5:** Commit `feat: panneau Règles ouvert aux parents et statut des téléphones`.

### Task 7: Documentation et version

**Files:**
- Modify: `README.md` (« Le code parent », « Panneau Règles », « Demandes de temps » — le passage « le panneau Règles leur est fermé » —, tableaux « administrateur seulement », section bouton « Devoirs terminés » et interrupteurs), `custom_components/parental_control/manifest.json` (`"version": "0.3.0"`)

- [ ] **Step 1:** Rédiger : qui est parent, propriétaire mémorisé, réassociation après réinstallation de l'app, entrée « Règles » visible de tous mais réservée, migration automatique à la mise à jour.
- [ ] **Step 2:** `.venv/bin/pytest` et `node --test tests/js/` PASS.
- [ ] **Step 3:** Commit `docs: parents non administrateurs`.
