# Demande de temps — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** depuis une carte, un enfant non admin envoie une demande (autoriser, bonus, minuteur, devoirs) que
les parents de la liste « Demandes » acceptent (avec une durée au choix) ou refusent depuis une notification
actionnable de l'application Home Assistant.

**Architecture :** un module pur `core/requests.py` tient le cycle de vie des demandes : création,
doublons, réponse, expiration et libellés. Le moteur garde un `RequestBook` en mémoire, envoie les
notifications, applique l'action acceptée par ses méthodes existantes et publie les demandes dans
l'état WebSocket. Un écouteur `mobile_app_notification_action` (`request_listener.py`) authentifie la
réponse par le jeton et par le propriétaire du téléphone. Côté cartes, la fenêtre d'action gagne un
bouton « Demander ».

**Tech Stack :** intégration HA en Python 3.14 (pytest, `pytest_homeassistant_custom_component`) et
cartes en JS natif (tests `node --test`).

**Spec :** `docs/superpowers/specs/2026-11-06-ha-parental-control-demande-de-temps-design.md`

## Global Constraints

- Délai d'expiration : 15 minutes (`REQUEST_TIMEOUT`). Résultat visible 5 minutes (`RESULT_DISPLAY`).
- Montants : entiers de 1 à 240 minutes, 6 options au plus. `None` signifie « Jusqu'au prochain
  changement » et n'est permis que pour `open`.
- Une réponse n'est acceptée que si elle porte le jeton de la demande en attente **et** si
  `event.context.user_id` est le propriétaire (`user_id` de l'entrée `mobile_app`) d'un téléphone
  de `request_notify`. Être admin ne suffit pas.
- Aucun service public de réponse. Les jetons ne figurent jamais dans l'état publié ni dans les
  journaux.
- Demandes en mémoire seulement (perdues au redémarrage).
- Le code parent et `check_unlock` sont inchangés. Une action acceptée passe par `add_exception`,
  `add_bonus`, `homework_done` et `start_timer`.
- Simulation : le texte des notifications de demande est préfixé par `SIMULATION_PREFIX`.
- Textes en français. Commits en français, terminés par
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Pas de push.
- Tests : `.venv/bin/pytest` (Python) et `node --test tests/js/` (JS) depuis la racine du dépôt.

## Review Focus

1. Le parent accepte, mais l'action n'est plus possible : la plage a changé, le quota est épuisé,
   ou un minuteur tourne déjà. La demande passe alors à l'état `failed`, avec la raison, et la
   tablette affiche « Impossible : … ». Rien ne plante et rien n'est accordé. Test : tâche 4.
2. Les deux parents répondent presque en même temps : seule la première réponse est appliquée,
   la seconde n'a aucun effet. Test : tâche 4.
3. La liste `request_notify` contient un service qui n'est pas `notify.mobile_app_…`, ou un
   téléphone retiré de HA : il est ignoré pour l'authentification, sans erreur. Test : tâche 4.
4. La config est rechargée et l'enfant ou la ressource de la demande disparaît : la demande expire
   proprement à l'échéance. L'accepter donne `failed` sans exception. Test : tâche 4.
5. `options` envoyées par la carte sans la proposition, avec doublons, ou avec `None` pour un bonus :
   les doublons sont retirés, la proposition est ajoutée en tête, `None` hors `open` est refusé.
   Test : tâche 2.

---

### Task 1 : champ de configuration `request_notify`

**Files :**
- Modify: `custom_components/parental_control/core/model.py` (`Config`)
- Modify: `custom_components/parental_control/core/config_io.py` (`parse_config`, `dump_config`)
- Modify: `custom_components/parental_control/www/panel-lib.js` (config vide)
- Modify: `custom_components/parental_control/www/panel.js` (`_general`, puces, actions `add-request-notify` / `del-request-notify`)
- Test: `tests/core/test_config_io.py`, `tests/js/panel-lib.test.mjs`

**Interfaces :**
- Produces: `Config.request_notify: tuple[str, ...] = ()` (champ avec défaut, placé après
  `default_on_demand`) ; clé JSON `"request_notify"` (liste de chaînes, absente → `[]`).

- [ ] **Step 1 : tests en échec.**
  - `test_request_notify_round_trip` : `parse_config(EX | {"request_notify": ["notify.mobile_app_iphone_de_manou"]})`
    donne `.request_notify == ("notify.mobile_app_iphone_de_manou",)`, et `dump_config(...)["request_notify"]`
    vaut la liste.
  - `test_request_notify_defaults_empty` : `parse_config(EX).request_notify == ()`.
  - `test_request_notify_must_be_strings` : `{"request_notify": [3]}` lève `ConfigError`.
  - JS : la config vide de `panel-lib.js` contient `request_notify: []`.
- [ ] **Step 2 :** `.venv/bin/pytest tests/core/test_config_io.py -k request_notify` → FAIL.
- [ ] **Step 3 : implémentation.** Lire avec `_str_list` comme `notify`. Dans le panneau, ajouter
  une deuxième carte sous « Notifications ».
  - Titre : `Demandes de temps (parents)`.
  - Puces : comme `_notifyChips`, même datalist `notifs`.
  - Aide : `Téléphones des parents (application Home Assistant) qui reçoivent les demandes et y répondent.`
  - Le texte d'aide de la carte « Notifications » devient :
    `Services prévenus des avertissements (fin de plage, etc.), par exemple les appareils des enfants.`
- [ ] **Step 4 :** `.venv/bin/pytest` et `node --test tests/js/` → PASS.
- [ ] **Step 5 : commit** `feat: liste des destinataires des demandes de temps`.

### Task 2 : module pur `core/requests.py`

**Files :**
- Create: `custom_components/parental_control/core/requests.py`
- Test: `tests/core/test_requests.py`

**Interfaces (Produces) :**
```python
REQUEST_TIMEOUT = timedelta(minutes=15)
RESULT_DISPLAY = timedelta(minutes=5)
MAX_OPTIONS = 6

class RequestKind(StrEnum): OPEN = "open"; BONUS = "bonus"; HOMEWORK = "homework"; TIMER = "timer"
class RequestStatus(StrEnum): PENDING = "pending"; ACCEPTED = "accepted"; REFUSED = "refused"; EXPIRED = "expired"; FAILED = "failed"

class RequestError(ValueError):  # .key : "invalid_request" | "request_pending"
    def __init__(self, key: str) -> None: ...

@dataclass
class TimeRequest:
    id: str; token: str; kind: RequestKind; kid_id: str
    resource_id: str | None; service: str | None
    proposed: int | None; options: tuple[int | None, ...]; replace: tuple[str, ...]
    created: datetime; expires: datetime
    status: RequestStatus = RequestStatus.PENDING
    granted: int | None = None; reason: str | None = None
    resolved_at: datetime | None = None; answered_by: str | None = None
    @property
    def key(self) -> tuple[str, str, str | None, str | None]: ...  # (kind, kid_id, resource_id, service)

def normalize_options(kind: RequestKind, proposed: int | None, options: Sequence[int | None]) -> tuple[int | None, ...]
class RequestBook:
    def create(self, kind, kid_id, *, resource_id, service, proposed, options, replace, now) -> TimeRequest
    def get(self, request_id: str) -> TimeRequest | None
    def claim(self, request_id: str, token: str, now: datetime) -> TimeRequest | None
    def finish(self, req: TimeRequest, status: RequestStatus, now: datetime, *, granted=None, reason=None, answered_by=None) -> None
    def expire(self, now: datetime) -> list[TimeRequest]
    def visible(self, now: datetime) -> list[TimeRequest]
def duration_label(minutes: int | None) -> str
def action_choices(req: TimeRequest) -> list[tuple[str, str]]
```

Règles :
- `normalize_options`
  - `HOMEWORK` : renvoie `()` ; `proposed` doit valoir `None`.
  - Les autres types : `proposed` en tête, puis `options` dans l'ordre, sans doublon. Coupé à
    `MAX_OPTIONS`.
  - Chaque valeur est un entier de 1 à 240, ou `None` seulement pour `OPEN`. `BONUS` et `TIMER`
    exigent un `proposed` entier.
  - En cas d'erreur : `RequestError("invalid_request")`.
- `create`
  - Lève `RequestError("request_pending")` si une demande `PENDING` a la même `key`.
  - Sinon : `id = uuid4().hex`, `token = secrets.token_urlsafe(16)`, `expires = now + REQUEST_TIMEOUT`.
- `claim`
  - Renvoie la demande si elle est `PENDING`, que `hmac.compare_digest` valide le jeton et que
    `now < expires`.
  - Sinon renvoie `None`.
  - Elle passe aussitôt la demande à `ACCEPTED` de façon provisoire : une seconde réponse renvoie
    alors `None`. `finish` fixe ensuite le statut définitif.
- `expire` : passe les demandes `PENDING` échues à `EXPIRED` et les renvoie.
- `visible` : renvoie les demandes en attente et celles résolues depuis moins de `RESULT_DISPLAY`.
  Au même appel, elle oublie les demandes résolues plus anciennes.
- `duration_label`
  - `15` → `"15 min"`, `60` → `"1 h"`, `90` → `"1 h 30"`, `120` → `"2 h"` ;
  - `None` → `"Jusqu'au prochain changement"`.
- `action_choices` donne des paires `(choix, titre)`. `choix` vaut l'indice dans `options` (en
  chaîne), `"accept"` ou `"refuse"`.
  - Si une proposition existe, le premier titre est `"Accepter " + duration_label(proposed)`, puis
    viennent les autres options (`duration_label`), puis `("refuse", "Refuser")`.
  - `OPEN` avec `proposed is None` : le premier titre est `"Accepter jusqu'au prochain changement"`.
  - `HOMEWORK` : `[("accept", "Accepter"), ("refuse", "Refuser")]`.

- [ ] **Step 1 : tests en échec** dans `tests/core/test_requests.py`.
  - `test_normalize_puts_proposed_first_and_dedupes` : `(BONUS, 30, [15, 30, 60])` → `(30, 15, 60)`.
  - `test_normalize_caps_at_six` : `(OPEN, 15, [30, 60, 120, None, 45, 90, 10])` donne 6 valeurs,
    `15` en tête.
  - `test_normalize_rejects_none_outside_open` : `(BONUS, 30, [None])` lève une `RequestError`
    dont `.key == "invalid_request"`.
  - `test_normalize_rejects_out_of_range` : `(TIMER, 0, [])` et `(TIMER, 241, [])` lèvent une
    erreur.
  - `test_normalize_homework_has_no_options` : `(HOMEWORK, None, [15])` → `()`.
  - `test_create_rejects_duplicate_pending` : un second `create` avec la même clé lève
    `request_pending`. Avec un autre `service`, il passe.
  - `test_claim_once_with_token` : un mauvais jeton donne `None`. Le bon donne la demande, et le
    même appel répété donne `None`.
  - `test_claim_after_expiry_is_none` : `now = expires` → `None`.
  - `test_expire_marks_expired` : `expire(created + 15 min)` renvoie la demande, au statut
    `EXPIRED`.
  - `test_visible_keeps_results_five_minutes` : une demande résolue reste visible à
    `+4 min 59 s`, plus à `+5 min`.
  - `test_action_choices_open` : `proposed=30`, `options=(30, 15, None)` →
    `[("0", "Accepter 30 min"), ("1", "15 min"), ("2", "Jusqu'au prochain changement"), ("refuse", "Refuser")]`.
  - `test_action_choices_homework` : `[("accept", "Accepter"), ("refuse", "Refuser")]`.
  - `test_duration_label` : les valeurs ci-dessus.
- [ ] **Step 2 :** `.venv/bin/pytest tests/core/test_requests.py` → FAIL (module absent).
- [ ] **Step 3 :** implémenter `core/requests.py`, sans aucune dépendance HA.
- [ ] **Step 4 :** `.venv/bin/pytest tests/core/test_requests.py` → PASS.
- [ ] **Step 5 : commit** `feat: cycle de vie des demandes de temps`.

### Task 3 : moteur, service `demander` et état publié

**Files :**
- Modify: `custom_components/parental_control/engine.py`
- Modify: `custom_components/parental_control/services.py`, `services.yaml`, `strings.json`, `translations/*.json`
- Modify: `custom_components/parental_control/serialize.py`
- Test: `tests/ha/test_requests.py` (nouveau), `tests/ha/test_services.py` (liste `SERVICES`), `tests/ha/test_websocket.py`

**Interfaces :**
- Consumes : la tâche 2, plus `Config.request_notify` (tâche 1).
- Produces :
  - `ParentalEngine.requests: RequestBook` (propriété).
  - `async ParentalEngine.request_time(kind: RequestKind, kid_id: str, *, resource_id: str | None = None, service: str | None = None, proposed: int | None = None, options: Sequence[int | None] = (), replace: Sequence[str] = ()) -> str`,
    qui renvoie l'id.
  - `ParentalEngine.request_message(req: TimeRequest) -> str`.
  - Service `parental_control.demander`, avec réponse optionnelle `{"id": ...}`.
  - Payload `display=True` : `state["requests"]` et `state["requests_enabled"]`.
  - Tag de notification `f"parental_control_{req.id}"`.
  - Identifiant d'action `f"PARENTAL_REQ:{req.id}:{req.token}:{choix}"`.

Comportement de `request_time` :
1. `_require_config()`.
2. Si `cfg.request_notify` est vide : `_invalid("requests_disabled")`.
3. `_check_kid`. Si `resource_id` est donné : `_check_resource`, et `kid_id` doit être dans
   `owners`, sinon `_invalid("invalid_target")`.
4. `RequestBook.create(...)`. Une `RequestError` est convertie en `_invalid(err.key)`.
5. Envoyer `notify.<service>` à chaque cible de `request_notify`, sans attendre (`_schedule`, comme
   `_send_notify`). Données :
   - `title` : `NOTIFY_TITLE` ;
   - `message` : `request_message(req)`, avec le préfixe de simulation si besoin ;
   - `data` : `{"tag": tag, "actions": [{"action": id, "title": titre} for choix, titre in action_choices(req)]}`.
6. `async_dispatcher_send(SIGNAL_UPDATE)`, puis renvoyer `req.id`.

`request_message` (enfant `Gabin`, ressource `Télé salon`, service `youtube`, nom lu dans
`services_catalog(hass)`, sinon l'id) :
- `OPEN` + service + ressource : `"Gabin demande 30 min de YouTube sur Télé salon"`.
- `OPEN` + service, sans ressource : `"Gabin demande 30 min de YouTube"`.
- `OPEN` + ressource, sans service : `"Gabin demande 30 min sur Télé salon"`.
- Avec `proposed=None`, `"30 min"` est remplacé par `"jusqu'au prochain changement"`, placé en
  fin de phrase : `"Gabin demande YouTube sur Télé salon jusqu'au prochain changement"`.
- `BONUS` : `"Gabin demande un bonus de 30 min"`, avec `" sur Switch"` si la demande vise une
  ressource.
- `TIMER` : `"Gabin demande un minuteur de 30 min"`.
- `HOMEWORK` : `"Gabin dit avoir terminé ses devoirs"`.

Expiration : dans `_on_tick`, appeler `requests.expire(now)`. Pour chaque demande expirée :
- envoyer `clear_notification` (`message: "clear_notification"`, `data: {"tag": tag}`) à toutes
  les cibles ;
- inscrire au journal (événement `logbook_entry`, `name: "Contrôle parental"`, `domain: DOMAIN`) :
  `"Demande de Gabin sans réponse"` ;
- `SIGNAL_UPDATE` si au moins une demande a expiré.

Sérialisation (`display=True` seulement) :
- `state["requests_enabled"] = bool(cfg.request_notify)` ;
- `state["requests"] = [{id, kind, kid_id, resource_id, service, proposed, status, granted, reason, expires}]`
  pour `requests.visible(now)`, sans `token`, `options`, `replace` ni `answered_by`.

Schéma du service :
```python
REQUEST_SCHEMA = vol.Schema({
    vol.Required("kind"): vol.In([k.value for k in RequestKind]),
    vol.Required(ATTR_KID_ID): cv.string,
    vol.Optional(ATTR_RESOURCE_ID): cv.string,
    vol.Optional(ATTR_SERVICE): cv.string,
    vol.Optional(ATTR_MINUTES): _MINUTES,
    vol.Optional("options", default=list): vol.All(cv.ensure_list, [vol.Any(None, _MINUTES)]),
    vol.Optional("replace", default=list): vol.All(cv.ensure_list, [cv.string]),
})
```
Pas de `check_unlock` : tout utilisateur peut demander. Nouvelles clés de traduction :
- `requests_disabled` : « Aucun parent ne reçoit les demandes. » ;
- `request_pending` : « Une demande identique est déjà en attente. » ;
- `invalid_request` : « Demande invalide. »

- [ ] **Step 1 : tests en échec** dans `tests/ha/test_requests.py`. Réutiliser `make_env` en le
  déplaçant dans `tests/ha/conftest.py`. La config est `EX` avec
  `"request_notify": ["notify.mobile_app_iphone_de_olivier", "notify.mobile_app_iphone_de_manou"]`,
  et ces deux services `notify` sont enregistrés comme services simulés qui capturent leurs appels.
  - `test_request_sends_actionable_notification_to_each_parent` : une demande `open` de
    `kid_ctx` (gabin, `resource_id: "tv"`, `service: "youtube"`, `minutes: 30`,
    `options: [15, 30, 60, 120, None]`) produit deux appels. Leur message vaut
    `"Gabin demande 30 min de YouTube sur Télé salon"` (adapter les noms à `EX`). Le premier
    titre d'action vaut `"Accepter 30 min"`, le dernier `"Refuser"`. Chaque action commence par
    `"PARENTAL_REQ:"`.
  - `test_request_needs_no_code` : un appel de `kid_ctx` sans `code` réussit, et
    `engine.decisions.exceptions` reste vide.
  - `test_request_disabled_without_parents` : avec `request_notify` vide → `requests_disabled`.
  - `test_duplicate_request_rejected` : un second appel identique → `request_pending`.
  - `test_request_kid_must_own_resource` : un enfant qui n'est pas propriétaire → `invalid_target`.
  - `test_request_expires_after_15_minutes` : on avance de 15 min et on déclenche le tick. Le
    statut devient `expired`, un `clear_notification` est envoyé avec le tag, et une entrée
    logbook est émise.
  - `test_state_exposes_requests_without_token` : le payload `display=True` contient la demande
    sans clé `token`, et la chaîne du jeton n'apparaît nulle part dans `json.dumps(payload)`.
  - `test_simulation_prefixes_request_message`.
  - Ajouter `"demander"` à `SERVICES` dans `test_services.py`.
- [ ] **Step 2 :** `.venv/bin/pytest tests/ha/test_requests.py` → FAIL.
- [ ] **Step 3 :** implémenter le moteur, le service, la sérialisation et les traductions.
- [ ] **Step 4 :** `.venv/bin/pytest` → PASS (la suite entière).
- [ ] **Step 5 : commit** `feat: service demander et notifications de demande`.

### Task 4 : réponse depuis la notification

**Files :**
- Create: `custom_components/parental_control/request_listener.py`
- Modify: `custom_components/parental_control/__init__.py` (branchement, désabonnement via `entry.async_on_unload`)
- Modify: `custom_components/parental_control/engine.py` (`answer_request`)
- Modify: `custom_components/parental_control/manifest.json` (`"after_dependencies": ["mobile_app"]` si absent)
- Test: `tests/ha/test_requests.py`

**Interfaces :**
- Produces :
  - `parent_user_ids(hass: HomeAssistant, targets: Sequence[str]) -> set[str]` : pour chaque cible
    `notify.mobile_app_<x>`, chercher l'entrée `mobile_app` telle que
    `"mobile_app_" + slugify(entry.data["device_name"]) == <service>`, et prendre
    `entry.data["user_id"]`. Les autres cibles sont ignorées.
  - `parse_action(action: str) -> tuple[str, str, str] | None` : `"PARENTAL_REQ:id:token:choix"` →
    `(id, token, choix)`, sinon `None`.
  - `async_setup_request_listener(hass, entry) -> CALLBACK_TYPE`.
  - `async ParentalEngine.answer_request(request_id: str, token: str, choice: str, user_id: str) -> RequestStatus | None` :
    renvoie `None` quand la réponse est ignorée.

Écouteur `mobile_app_notification_action` :
1. `parse_action(event.data.get("action", ""))`. Renvoie `None` → ignorer.
2. Si `event.context.user_id` n'est pas dans `parent_user_ids(hass, cfg.request_notify)` :
   journaliser un avertissement (sans le jeton), puis ignorer.
3. Appeler `engine.answer_request(...)`.

`answer_request` :
1. `requests.claim(id, token, now)` renvoie `None` → renvoyer `None`.
2. Si `choice == "refuse"` → `REFUSED`.
3. Sinon, si `choice` vaut `"accept"` (devoirs) ou un indice valide de `options`, appliquer
   l'action :
   - `OPEN` : annuler chaque id de `replace` encore présent (`cancel_exception`), puis
     `add_exception(Target(resource_id=req.resource_id, kid_id=None if req.resource_id else req.kid_id, service=req.service), True, minutes)` ;
   - `BONUS` : `add_bonus(minutes, kid_id=None if req.resource_id else req.kid_id, resource_id=req.resource_id)` ;
   - `TIMER` : `start_timer(req.kid_id, minutes)` ;
   - `HOMEWORK` : `homework_done(req.kid_id)`.

   Une `ServiceValidationError` donne `FAILED`, avec `reason` = message traduit, à défaut la
   `translation_key`. Toute autre `KeyError` ou `ValueError` donne `FAILED`, avec la raison
   `"Action impossible"`.
4. Un choix invalide donne `FAILED`, avec la raison `"Choix inconnu"`.
5. `finish(...)`, avec `answered_by` = le nom de l'utilisateur HA.
6. Envoyer `clear_notification` à toutes les cibles.
7. Inscrire au journal :
   - `"Demande de Gabin acceptée par Olivier : 30 min"` ;
   - `"Demande de Gabin refusée par Manou"` ;
   - `"Demande de Gabin acceptée par Olivier, mais impossible : <raison>"`.
8. `SIGNAL_UPDATE`, puis renvoyer le statut.

- [ ] **Step 1 : tests en échec.** Créer deux `MockConfigEntry(domain="mobile_app", data={"device_name": "iPhone de Manou", "user_id": manou.id, ...})`,
  avec `manou` non admin. Déclencher l'événement avec
  `hass.bus.async_fire("mobile_app_notification_action", {"action": ...}, context=Context(user_id=...))`.
  - `test_parent_non_admin_accepts_with_other_duration` : Manou choisit l'indice de `60`. Une
    exception ouverte de 60 min existe, le statut est `accepted`, `granted == 60`, et
    `clear_notification` est envoyé aux deux cibles.
  - `test_tablet_user_cannot_answer` : le bon jeton, mais `kid_ctx` → rien n'est appliqué, la
    demande reste `pending`.
  - `test_admin_without_phone_in_list_cannot_answer` : `admin_ctx` alors qu'aucun téléphone de la
    liste ne lui appartient → ignoré.
  - `test_wrong_token_ignored`.
  - `test_first_answer_wins` : Manou accepte puis Olivier refuse → `accepted`, une seule exception.
  - `test_refuse` → `refused`, aucune exception, journal « refusée par Manou ».
  - `test_accept_until_change` : choix `None` → exception avec `minutes=None` (signature de règle).
  - `test_accept_replaces_listed_exceptions` : un id de fermeture dans `replace` est annulé avant
    l'ouverture.
  - `test_accept_bonus_on_switch_resource`, `test_accept_timer`, `test_accept_homework`.
  - `test_accept_impossible_marks_failed` (Review Focus 1) : demande de minuteur, puis on passe
    hors de la plage quota avant d'accepter → `failed`, `reason` non vide, aucun minuteur.
  - `test_non_mobile_app_target_ignored` (Review Focus 3) : `request_notify` contient
    `notify.persistent_notification`, et `parent_user_ids` ne lève pas d'erreur.
  - `test_answer_after_config_removed_kid` (Review Focus 4) : l'enfant est retiré par
    `set_config`, puis la réponse arrive → `failed`, sans exception.
  - `test_late_answer_after_expiry_ignored`.
- [ ] **Step 2 :** `.venv/bin/pytest tests/ha/test_requests.py` → FAIL.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** `.venv/bin/pytest` → PASS.
- [ ] **Step 5 : commit** `feat: réponse aux demandes depuis la notification`.

### Task 5 : cartes, fenêtre « Demander » et état des demandes

**Files :**
- Modify: `custom_components/parental_control/www/lib.js`
- Modify: `custom_components/parental_control/www/dialogs.js`
- Modify: `custom_components/parental_control/www/kid-card.js`, `resource-card.js`, `switch-card.js`
- Test: `tests/js/lib.test.mjs`

**Interfaces :**
- Consumes : `state.requests` et `state.requests_enabled` (tâche 3), le service `demander`.
- Produces (`lib.js`) :
  - `canRequest(hass, state) -> boolean` : vrai si le compte n'est pas admin et que
    `requests_enabled` est vrai.
  - `findRequest(state, {kind, kid_id, resource_id = null, service = null}) -> request | null` :
    la plus récente qui correspond.
  - `requestsFor(state, {kid_id} | {resource_id}) -> request[]`.
  - `requestLine(req, state) -> string` :
    - `pending` → `"Demande envoyée · en attente"` ;
    - `accepted` → `"Accepté : 30 min"` (avec `granted == null` et `kind == "open"` :
      `"Accepté : jusqu'au prochain changement"` ; `kind == "homework"` : `"Accepté"`) ;
    - `refused` → `"Refusé"` ;
    - `expired` → `"Pas de réponse"` ;
    - `failed` → `"Impossible : " + reason`.
  - Le libellé de durée suit `duration_label` de la tâche 2.
- Produces (`dialogs.js`) : `openActionDialog` reçoit l'option
  `request: { kids: [{value, label}] | null, pending: boolean, onRequest({choice, duration, kid}) -> Promise<{ok}|{ok:false,error}> } | null`.
  - Le bouton `Demander` (classe `pill`) s'affiche à gauche de `Annuler`.
  - Il est actif quand la durée est choisie (si `durations`) et l'enfant aussi (si `kids`), sans
    attendre le code.
  - Si `kids` est fourni, une rangée `Qui demande ?` (pastilles) apparaît.
  - Si `pending` est vrai, le bouton affiche `En attente…` et reste désactivé.
  - Après un succès, la fenêtre se ferme. Une erreur s'affiche comme pour `onSubmit`.
  - `runBonus` reçoit `request` et le transmet.

Branchement des cartes (comptes non admin avec `canRequest`) :
- **Carte enfant.**
  - `_withCode` : `homework` → `kind: "homework"` ; `timer` →
    `kind: "timer", minutes, options: TIMER_MINUTES` ; `bonus` →
    `kind: "bonus", minutes, options: bonusMinutes(config)`. `kid_id` est celui de la carte,
    `kids: null`.
  - `_toggleService` : `kind: "open"`, `kid_id`, `service`, `minutes: duration`,
    `options: DURATIONS.map(d => d.value)`, `replace: t.exceptions`.
- **Carte ressource.**
  - `_openAllow` : `kind: "open"`, `resource_id`, `service: choice`. `kids` vient des propriétaires
    (`v.owners`, avec le nom lu dans `state.kids`).
  - `_toggleService` : même chose, avec `replace: t.exceptions`.
  - Bonus Switch (`runBonus`) : `kind: "bonus"`, `resource_id`, `minutes`,
    `options: bonusMinutes(config)`, `kids` = propriétaires.
- **Carte Switch.** Bonus, comme sur la carte ressource.
- `minutes` est omis quand la durée choisie vaut `null` (jusqu'au prochain changement).
- `pending` vaut `findRequest(...)?.status === "pending"` pour les fenêtres à cible fixe. Pour
  `_openAllow` (choix libre), il vaut `false` : le moteur refuse le doublon et la fenêtre affiche
  l'erreur.
- Affichage : chaque carte montre, sous ses pastilles et dans le style de la ligne d'erreur
  existante, une ligne `requestLine` par demande de `requestsFor` (enfant de la carte, ou
  ressource de la carte).

- [ ] **Step 1 : tests en échec** dans `lib.test.mjs`.
  - `canRequest` : faux pour un admin, faux si `requests_enabled` est faux, vrai sinon.
  - `findRequest` : distingue le `service` et le `resource_id`, et renvoie la plus récente.
  - `requestLine` : les six cas ci-dessus, dont `"Accepté : 1 h"` pour `granted: 60`.
  - `requestsFor` : filtre par enfant et par ressource.
- [ ] **Step 2 :** `node --test tests/js/` → FAIL.
- [ ] **Step 3 :** implémenter `lib.js`, puis `dialogs.js` et les cartes.
- [ ] **Step 4 :** `node --test tests/js/` et `.venv/bin/pytest` → PASS.
- [ ] **Step 5 : commit** `feat: bouton Demander et état des demandes dans les cartes`.

### Task 6 : documentation

**Files :**
- Modify: `README.md` (nouvelle section « Demandes de temps »)

- [ ] **Step 1 :** rédiger la section :
  - ce que voient l'enfant et le parent ;
  - la liste « Demandes » dans le panneau ;
  - la condition d'authentification (téléphone de la liste, jeton) ;
  - l'expiration à 15 min ;
  - la perte des demandes au redémarrage ;
  - iPhone recommandé (Android affiche 3 boutons au plus) ;
  - le service `parental_control.demander` et ses champs.
- [ ] **Step 2 :** `.venv/bin/pytest` et `node --test tests/js/` → PASS.
- [ ] **Step 3 : commit** `docs: demandes de temps`.
