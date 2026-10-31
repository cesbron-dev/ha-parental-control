# Cartes Lovelace du contrôle parental — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer dans l'intégration `parental_control` trois cartes Lovelace (appareil, frise, Switch) qui ne lisent que le moteur, plus les deux changements moteur dont elles ont besoin, puis monter le dashboard tablette sur l'instance de test.

**Architecture:** Le moteur enrichit le message existant de `parental_control/state/subscribe` (non admin) avec les données d'affichage (noms, types, loisirs, frise du jour, fin effective des exceptions). L'intégration sert un dossier `www/` et l'injecte dans le frontend (`add_extra_js_url`) ; les cartes sont des web components natifs sans compilation, avec la logique pure isolée dans `lib.js` testée sous `node --test`.

**Tech Stack:** Python 3.14 / Home Assistant (pytest-homeassistant-custom-component), JavaScript ES modules (navigateur + Node 24 pour les tests).

**Spec:** `docs/superpowers/specs/2026-10-30-ha-parental-control-cards-design.md`

## Global Constraints

- Tests Python : `.venv/bin/pytest -W error -q tests` doit rester vert, sans avertissement.
- Tests JS : `node --test tests/js/` ; aucune dépendance npm (pas de `package.json`, pas de jsdom).
- Aucun code parent stocké dans une carte, une config de dashboard ou une action ; le code saisi est oublié après l'appel.
- Code demandé (compte non admin) **seulement** pour les actions qui ouvrent : `exception` avec `open: true`, `ajouter_bonus`. « Arrêter » (`exception open:false` sans durée) et ✕ sur une autorisation (`annuler_exception`) partent sans code, avec confirmation.
- Les cartes n'appellent que des services `parental_control.*` ; jamais AdGuard, `media_player.*` ni Nintendo.
- Ressource `kind: nintendo` : ni « Arrêter » ni « Autoriser… » ; pilules bonus `+15m +30m +1h` à la place.
- Textes d'interface en français ; style « verre » sombre repris du `BASE_CSS` des cartes inline de l'instance de test (fond `linear-gradient(135deg, rgba(255,255,255,.11), rgba(255,255,255,.03)), rgba(24,32,46,.78)`, bord `1px solid rgba(255,255,255,.18)`, rayon 18 px, titre en capitales `letter-spacing:.06em`, pilules rayon 8 px, confirmation « Confirmer ? » en deux appuis sous 3000 ms).
- Commits en français terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` ; pas de push sans accord d'Olivier.

## Review Focus

1. Payload d'état reçu avant que le moteur ait un snapshot (`snapshot is None`) : les cartes affichent « Contrôle parental indisponible », sans erreur JS → test `lib.test.mjs::resourceView handles empty state`.
2. `resource:` inconnu dans la config d'une carte (ressource supprimée du moteur) : message « Ressource inconnue : <id> » au lieu d'une carte vide → même fichier, `resourceView unknown resource`.
3. Exception sans durée (`until: null`) : la pilule affiche « jusqu'à HH:MM » à partir de `ends_at`, et `ends_at` peut lui-même être `null` (aucun changement aujourd'hui) → « jusqu'à nouvel ordre » ; tests `formatPill` et `test_exception_ends_without_change`.
4. Exception visant un enfant ou tout le monde (`resource_id: null`) : elle apparaît sur chaque carte appareil concernée, et ✕ l'annule partout — la pilule l'indique (« Gabin · tous ses appareils ») ; test `exceptionsForResource kid and global`.
5. Changement de fuseau / jour en cours de journée : la frise est recalculée par le moteur à chaque push, la carte ne fait que projeter `start`/`end` ISO sur 0–24 h de la date locale de `now` ; test `timelineGeometry clamps to day`.

---

### Task 1: « Arrêter » l'emporte sur les services autorisés

**Files:**
- Modify: `custom_components/parental_control/core/evaluator.py` (`_apply_exceptions`, `_service_overrides`)
- Test: `tests/core/test_evaluator_access.py`

**Interfaces:**
- Produces: même signature `_apply_exceptions(now, cfg, dec, states, ignored)` ; règle : pour une ressource, une exception de ressource `open=False` ignore toutes les exceptions de service qui s'y appliquent (`_service_exception_applies`) et dont `created` est antérieur. Les exceptions de service plus récentes continuent de s'appliquer. Rien n'est supprimé de `dec.exceptions`.

- [ ] **Step 1: Tests**

```python
def test_resource_close_beats_older_service_open(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_gabin", service="youtube"), True, id_="yt", created=at(19)),
        exc(Target(resource_id="iphone_gabin"), False, id_="stop", created=at(20)),
    ])
    snap = evaluate(at(20, 30), cfg, dec, ECOLE)
    assert snap.resources["iphone_gabin"].blocked_services == cfg.leisure_for_resource("iphone_gabin")

def test_newer_service_open_beats_resource_close(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_gabin"), False, id_="stop", created=at(19)),
        exc(Target(resource_id="iphone_gabin", service="youtube"), True, id_="yt", created=at(20)),
    ])
    assert "youtube" not in evaluate(at(20, 30), cfg, dec, ECOLE).resources["iphone_gabin"].blocked_services

def test_resource_close_keeps_kid_service_open_on_other_devices(make_cfg):
    # même montage que test_kid_service_exception_applies_to_all_kid_devices (ipad_gabin en plus)
    # exceptions : kid_id="gabin", service="youtube", open, created=at(19) ;
    #              resource_id="iphone_gabin", open=False, created=at(20)
    # attendu : "youtube" bloqué sur iphone_gabin, débloqué sur ipad_gabin
```

- [ ] **Step 2:** `.venv/bin/pytest -W error -q tests/core/test_evaluator_access.py` → les 2 premiers échouent (le 2ᵉ peut déjà passer : il fixe le comportement).
- [ ] **Step 3:** Dans `_apply_exceptions`, retenir par ressource le `created` de la dernière exception de ressource fermante ; passer à `_service_overrides` le seuil et ignorer les exceptions de service `created` ≤ seuil.
- [ ] **Step 4:** Suite complète `.venv/bin/pytest -W error -q tests` → vert.
- [ ] **Step 5:** Commit `feat: « Arrêter » une ressource l'emporte sur les services autorisés avant`.

### Task 2: Frise du jour et fin effective des exceptions (cœur pur)

**Files:**
- Create: `custom_components/parental_control/core/display.py`
- Test: `tests/core/test_display.py`

**Interfaces:**
- Consumes: `_timeline` de l'évaluateur — la rendre publique sous le nom `timeline(kid, day_type, day, tz) -> list[Slot]` (renommer `_Slot` en `Slot`, mettre à jour les usages internes).
- Produces:
  - `kid_timeline(cfg: Config, snap: Snapshot, kid_id: str, now: datetime) -> list[dict]` → `[{"start": iso, "end": iso, "type": SegmentType.value}]` pour la date locale de `now`, avec le `day_type` du `snap.kids[kid_id]`.
  - `exception_end(cfg: Config, snap: Snapshot, exc: ManualException) -> datetime | None` → `exc.until` s'il existe ; sinon le plus proche `segment_end` parmi les enfants concernés (cible enfant : cet enfant ; cible ressource : ses propriétaires ; cible globale : tous les enfants) ; `None` si aucun enfant concerné.

- [ ] **Step 1: Tests** (avec `cfg` et `at` des tests cœur, mardi école)

```python
def test_kid_timeline_covers_day(cfg):
    snap = evaluate(at(16, 30), cfg, Decisions(), ECOLE)
    tl = kid_timeline(cfg, snap, "gabin", at(16, 30))
    assert tl[0]["start"] == at(0, 0).isoformat()
    assert tl[-1]["end"] == (at(0, 0) + timedelta(days=1)).isoformat()
    assert all(a["end"] == b["start"] for a, b in zip(tl, tl[1:]))
    assert {s["type"] for s in tl} <= {t.value for t in SegmentType}

def test_exception_end_uses_until(cfg): ...       # until=at(21) → at(21)
def test_exception_end_falls_back_to_segment_end(cfg):
    # exception tv open sans durée à 20:00 → snap.kids["gabin"].segment_end
def test_exception_ends_without_change(cfg): ...  # cible kid_id inconnu → None
```

- [ ] **Step 2:** lancer `tests/core/test_display.py` → échec (module absent).
- [ ] **Step 3:** implémenter `core/display.py` (pur, sans import HA).
- [ ] **Step 4:** suite complète verte.
- [ ] **Step 5:** Commit `feat: frise du jour et fin effective des exceptions pour l'affichage`.

### Task 3: Données d'affichage dans l'état WebSocket (non admin)

**Files:**
- Modify: `custom_components/parental_control/serialize.py` (`serialize_snapshot`, `serialize_exception`)
- Test: `tests/ha/test_websocket.py`

**Interfaces:**
- Consumes: Task 2 (`kid_timeline`, `exception_end`), `engine.config`.
- Produces (ajouts au payload de `parental_control/state` et `state/subscribe`, rien de retiré) :
  - `kids[id]` + `name`, `emoji`, `color`, `timeline` (liste Task 2) ;
  - `resources[id]` + `name`, `kind` (valeur `ResourceKind`), `owners` (liste), `leisure` (liste triée de `cfg.leisure_for_resource`) ; pour `kind == "nintendo"` en plus `used_entity`, `remaining_entity` ;
  - chaque exception + `ends_at` (ISO ou `null`) ;
  - racine + `now` (ISO, heure locale du moteur).
  - Jamais : `code_hash`, `calendar`, `calendar_map`, `notify`, autres `options`.

- [ ] **Step 1: Tests**

```python
async def test_state_has_display_data_for_non_admin(hass, entry, hass_ws_client):
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state"})
    res = (await client.receive_json())["result"]
    assert res["kids"]["gabin"]["name"] == "Gabin"
    assert res["kids"]["gabin"]["timeline"]
    assert res["resources"]["iphone_gabin"]["kind"] == "adguard_services"
    assert "youtube" in res["resources"]["iphone_gabin"]["leisure"]
    assert set(res["resources"]["switch"]) >= {"used_entity", "remaining_entity"}
    assert "now" in res

async def test_state_leaks_no_secret(hass, entry, hass_ws_client):
    # sérialiser le résultat en texte : ni "code", ni "calendar", ni "device_id", ni "limit_entity"
```

- [ ] **Step 2:** échec attendu (clés absentes).
- [ ] **Step 3:** compléter `serialize_snapshot` ; le push existant sur `SIGNAL_UPDATE` couvre déjà les changements de config (`set_config` → `async_evaluate`).
- [ ] **Step 4:** suite complète verte.
- [ ] **Step 5:** Commit `feat: données d'affichage des cartes dans l'état WebSocket`.

### Task 4: Servir et injecter les cartes

**Files:**
- Create: `custom_components/parental_control/frontend.py`, `custom_components/parental_control/www/parental-cards.js` (point d'entrée vide pour l'instant : `import './lib.js';` + `console.info`)
- Modify: `__init__.py` (appel dans `async_setup_entry`), `manifest.json` (`"dependencies": ["http", "frontend"]`)
- Test: `tests/ha/test_frontend.py`

**Interfaces:**
- Produces: `async_register_frontend(hass) -> None` idempotente (drapeau dans `hass.data`) : `hass.http.async_register_static_paths([StaticPathConfig("/parental_control_static", <dossier www>, True)])` puis `frontend.add_extra_js_url(hass, "/parental_control_static/parental-cards.js?v=<version manifest>")`. URL publique des modules : `/parental_control_static/<fichier>.js`.

- [ ] **Step 1: Test** : après setup de l'entrée, l'URL `?v=0.1.0` (version du manifest) figure dans `hass.data["frontend_extra_module_url"]` ; un 2ᵉ setup (reload) ne l'ajoute pas deux fois. Si `hass.http` est absent dans l'environnement de test, mocker `async_register_static_paths` et vérifier l'appel.
- [ ] **Step 2:** échec attendu.
- [ ] **Step 3:** implémenter ; lire la version dans `manifest.json` une fois au chargement.
- [ ] **Step 4:** suite complète verte.
- [ ] **Step 5:** Commit `feat: l'intégration sert et charge ses cartes Lovelace`.

### Task 5: Logique partagée des cartes (`lib.js`)

**Files:**
- Create: `custom_components/parental_control/www/lib.js`, `custom_components/parental_control/www/connection.js`
- Test: `tests/js/lib.test.mjs`

**Interfaces:**
- Produces (exports de `lib.js`, purs, sans DOM) :
  - `fmtDuration(minutes) -> "1h 05m"` (format des cartes actuelles, négatif → `"0h 00m"`).
  - `exceptionsForResource(state, resourceId) -> Array<{id, label, service|null, scope: "resource"|"kid"|"all", endsAt|null}>` : exceptions `open: true` qui touchent la ressource (cible ressource ; cible enfant propriétaire ; cible globale ; une exception de service ne touche que les ressources `adguard_services`).
  - `formatPill(exc, now) -> string` : `"YouTube · 42 min"`, `"Tout l'appareil · jusqu'à 22:45"` (sans `until` mais avec `endsAt`), `"… · jusqu'à nouvel ordre"` (`endsAt` null) ; suffixe `" · Gabin · tous ses appareils"` / `" · tout le monde"` selon `scope`.
  - `resourceView(state, resourceId) -> {status: "unavailable"|"unknown"|"ok", name, kind, owners, open, reason, until, used, remaining, leisure, nintendo}`.
  - `timelineGeometry(segments, now) -> {bars: [{left%, width%, type}], nowPct}` ; bornes ramenées à [0, 100] sur la journée locale de `now`.
  - `needsCode(hass, action) -> boolean` : `false` si `hass.user.is_admin` ; sinon `true` pour `"open"` et `"bonus"`, `false` pour `"stop"` et `"cancel"`.
  - `serviceLabel(id) -> string` : table `{youtube: "YouTube", tiktok: "TikTok", disneyplus: "Disney+", netflix: "Netflix", roblox: "Roblox", twitch: "Twitch", snapchat: "Snapchat", instagram: "Instagram", discord: "Discord", fortnite: "Fortnite", reddit: "Reddit", facebook: "Facebook"}`, à défaut id capitalisé.
- `connection.js` : `subscribeState(hass, callback) -> Promise<unsubscribe>` partagé entre toutes les cartes (une seule souscription `parental_control/state/subscribe` par connexion, compteur de références) ; `callAction(hass, service, data, code?)` qui ajoute `code` seulement s'il est fourni et renvoie l'erreur du moteur.

- [ ] **Step 1:** écrire `tests/js/lib.test.mjs` (`node:test` + `node:assert/strict`) couvrant chaque export ci-dessus, dont les cas de la Review Focus 1–5 (noms de tests indiqués là).
- [ ] **Step 2:** `node --test tests/js/` → échec (module absent).
- [ ] **Step 3:** implémenter `lib.js` puis `connection.js` (ce dernier non testé sous Node : il dépend de `hass.connection`).
- [ ] **Step 4:** `node --test tests/js/` vert.
- [ ] **Step 5:** Commit `feat: logique partagée des cartes du contrôle parental`.

### Task 6: Carte appareil `parental-resource-card`

**Files:**
- Create: `custom_components/parental_control/www/resource-card.js`, `custom_components/parental_control/www/style.js` (export `BASE_CSS`, `pill()` et le mécanisme de confirmation en deux appuis), `custom_components/parental_control/www/dialogs.js` (fenêtre « Autoriser… » et saisie du code)
- Modify: `www/parental-cards.js` (importe les cartes, `window.customCards`)

**Interfaces:**
- Consumes: Task 5 (`resourceView`, `exceptionsForResource`, `formatPill`, `needsCode`, `serviceLabel`, `subscribeState`, `callAction`, `fmtDuration`).
- Produces: élément `parental-resource-card` ; config `{resource: string, name?: string, icon?: string}` ; `setConfig` lève une erreur si `resource` manque ; `getStubConfig()` → `{resource: ""}` ; `getGridOptions()` → `{columns: 12, min_columns: 6}`.
- Comportement (spec 4.1, 4.4) : en-tête (icône par type `mdi:television` / `mdi:cellphone` / `mdi:nintendo-switch`, nom, propriétaires, badge Autorisé/Bloqué/Pause), raison + prochain changement, pilules d'autorisations avec ✕ (`annuler_exception {exception_id}`), barre utilisé/autorisé si `used` ou `remaining` non nuls, « ＋ Autoriser… » (dialogue : Quoi = « Tout l'appareil » + `leisure` pour AdGuard ; Pendant = 15, 30, 60, 120 min ou « jusqu'au prochain changement » sans `minutes` → `exception {resource_id, open: true, service?, minutes?}`), « ⏻ Arrêter » rouge (`exception {resource_id, open: false}`). Ressource nintendo : pilules bonus (`ajouter_bonus {resource_id, minutes}`) à la place d'Autoriser, pas d'Arrêter. Cadenas `mdi:lock` sur les boutons où `needsCode` est vrai ; saisie du code avant l'appel, code effacé ensuite ; erreur du moteur affichée dans le dialogue.

- [ ] **Step 1:** implémenter ; rafraîchir le compte à rebours chaque minute (timer arrêté dans `disconnectedCallback`).
- [ ] **Step 2:** `node --check` sur chaque fichier `www/*.js` ; `node --test tests/js/` toujours vert.
- [ ] **Step 3:** Commit `feat: carte appareil du contrôle parental`.

### Task 7: Frise `parental-timeline-card`

**Files:**
- Create: `custom_components/parental_control/www/timeline-card.js`
- Modify: `www/parental-cards.js`

**Interfaces:**
- Consumes: Task 5 (`timelineGeometry`, `subscribeState`), `style.js`.
- Produces: élément `parental-timeline-card` ; config `{kids?: string[]}` (tous par défaut, ordre de la config) ; `getGridOptions()` → `{columns: 12}`.
- Comportement (spec 4.2) : en-tête « Aujourd'hui » + type de jour (`ecole` → « Jour d'école », `fin_de_semaine` → « Fin de semaine », `conge_peda` → « Congé pédago », `vacances` → « Vacances ») + heure ; par enfant : nom, statut (`reason`) et prochaine étape (`segment_end`), barre colorée (`libre` vert, `apres_devoirs` orange, `quota` bleu, `sur_demande` gris clair, `bloque` rouge — un seul rouge, nuit et école comprises), trait « maintenant », hachuré bleu de `now` à `ends_at` pour chaque exception qui touche l'enfant, graduation 0/6/12/18/24 h, légende. Toucher une barre : `hass-more-info` sur `sensor.<kid_id>_statut` (détail natif de HA, qui montre raison et exceptions en attributs).

- [ ] **Step 1:** implémenter.
- [ ] **Step 2:** `node --check` + `node --test tests/js/`.
- [ ] **Step 3:** Commit `feat: frise de la journée du contrôle parental`.

### Task 8: Carte Switch `parental-switch-card`

**Files:**
- Create: `custom_components/parental_control/www/switch-card.js`
- Modify: `www/parental-cards.js`

**Interfaces:**
- Consumes: Task 5, `style.js`, entités `used_entity` / `remaining_entity` du payload (lues dans `hass.states`).
- Produces: élément `parental-switch-card` ; config `{resource: string, title?: string = "Nintendo Switch", bonus_minutes?: number[] = [15, 30, 60]}`.
- Comportement (spec 4.3) : reprise visuelle de `controle-parental-switch-card` de l'instance de test (jauge en arc SVG dégradé rouge→vert, « Temps de jeu », temps utilisé, pilules bleues `+15m +30m +1h`) ; accordé = utilisé + restant ; ligne d'état de la règle (« autorisée jusqu'à 20:00 » / « bloquée · reprise 7:00 ») ; bonus via `ajouter_bonus {resource_id, minutes}` avec code si `needsCode(hass, "bonus")` ; ni Arrêter ni Autoriser.

- [ ] **Step 1:** implémenter.
- [ ] **Step 2:** `node --check` + `node --test tests/js/` ; suite Python verte.
- [ ] **Step 3:** mettre à jour le `README.md` (section « Cartes » : les trois types, leur config, règle du code) ; Commit `feat: carte Switch du contrôle parental`.

### Task 9: Déploiement et dashboards sur l'instance de test (opérations, avec accord d'Olivier)

Aucune modification du dépôt. **Demander l'accord avant chaque étape à effet externe** (push, mise à jour HACS, redémarrage, écriture de dashboard).

- [ ] **Step 1:** pousser `main` (accord), mettre à jour `parental_control` via HACS sur l'instance de test, redémarrer (accord).
- [ ] **Step 2:** vérifier dans le navigateur (console) le message de chargement de `parental-cards.js` et l'absence d'erreur.
- [ ] **Step 3:** créer le dashboard `tablette` (titre « Tablette », icône `mdi:tablet`, `require_admin: false`, vue `sections`) : frise en pleine largeur, une `parental-resource-card` par ressource du moteur sauf la Switch, une `parental-switch-card`.
- [ ] **Step 4:** passer `controle-parental` en `require_admin: true`.
- [ ] **Step 5:** avec un compte non admin : « Autoriser… » demande le code, un code faux affiche l'erreur, « Arrêter » et ✕ passent sans code ; avec un admin, aucun code.
- [ ] **Step 6 (accord) :** retirer la ressource inline `controle-parental-*` et la vue « Télé (proposition) ».
