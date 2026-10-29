# ha-parental-control — moteur de règles : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Une intégration HACS `parental_control` qui calcule et applique, par enfant, des règles (frise horaire, devoirs, quotas, minuteurs, exceptions, pause) sur la TV, les services AdGuard et la Switch, en pilotant uniquement des entités HA.

**Architecture:** Un **noyau pur** (`core/`, aucun import HA) qui transforme « heure + config + décisions + usage + types de jour » en un instantané d'états, entièrement testé avec pytest. Une **couche HA** fine : stockage, adaptateurs de ressources, un moteur qui réévalue toutes les 60 s et à chaque événement, applique les différences et émet les avertissements, plus les services, entités et l'API WebSocket.

**Tech Stack:** Python 3.14, Home Assistant core 2026.10 (version de l'instance de test : `core-2026.10.2`), pytest, `pytest-homeassistant-custom-component` (version alignée sur HA 2026.10), `freezegun` (fourni par ce dernier).

**Spec:** `docs/superpowers/specs/2026-10-28-ha-parental-control-engine-design.md` (déplacée dans le nouveau repo à la tâche 1).

## Global Constraints

- Repo : `ha-parental-control` (dossier `/Users/olivier/dev/github.com/cesbron-dev/ha-parental-control`), domaine HA `parental_control`, code sous `custom_components/parental_control/`.
- Le noyau `custom_components/parental_control/core/` n'importe **jamais** `homeassistant`.
- Aucun appel direct aux API AdGuard/Nintendo/TV : uniquement des services et entités HA.
- Switch AdGuard du bridge : `switch.adguard_<client>_svc_<service>`, **ON = bloqué**.
- Nintendo : `nintendo_parental_controls.add_bonus_time` avec `{device_id, bonus_time}`, **30 min max par appel**, **5 s** entre deux appels.
- Avertissement par défaut : **5 minutes** avant toute fermeture prévisible.
- Heures de la frise = heure locale murale (`hass.config.time_zone`, ici `America/Toronto`).
- Textes visibles par l'utilisateur en français (raisons, notifications, `translations/fr.json` ; `strings.json` en anglais).
- Les clients AdGuard ne sont jamais codés en dur : ils viennent de la config.
- Commits : messages conventionnels (`feat:`, `test:`, `chore:`), terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Redémarrage de HA pendant une fenêtre fermée ou un minuteur** : au démarrage, décisions et minuteur restaurés, rien ne se rouvre, un minuteur expiré pendant l'arrêt reste expiré → test `test_restart_restores_decisions_and_keeps_closed` (tâche 8).
2. **TV `unavailable`/`standby`** (la Samsung passe `unavailable` éteinte) : comptée comme éteinte, pas de `turn_off` envoyé, pas de temps décompté → `test_media_player_unavailable_is_not_in_use` (tâche 6).
3. **Entité de la config absente** (client AdGuard renommé après la reconfiguration) : avertissement dans le journal, les autres ressources continuent d'être appliquées → `test_missing_entity_does_not_stop_other_resources` (tâche 8).
4. **Jour de changement d'heure** (1er novembre 2026, fin de l'heure d'été à Toronto) : les segments restent calés sur l'heure murale → `test_dst_end_day_uses_wall_clock` (tâche 4).
5. **Calendrier indisponible ou en erreur** : retour au type de jour par défaut (semaine/fin de semaine), pas d'exception levée → `test_calendar_failure_falls_back_to_weekday` (tâche 8).

---

## File Structure

```
ha-parental-control/
  hacs.json                       # {"name": "Contrôle parental", "render_readme": true, "homeassistant": "2026.10.0"}
  README.md
  pyproject.toml                  # config pytest + dépendances de dev
  requirements_test.txt
  docs/superpowers/specs/…  docs/superpowers/plans/…
  custom_components/parental_control/
    __init__.py                   # async_setup_entry / unload : crée store, moteur, plateformes, services, websocket
    manifest.json
    const.py                      # DOMAIN, SIGNAL_UPDATE, EVENT_WARNING, valeurs par défaut
    config_flow.py                # instance unique, saisie du code parent ; options flow : changer le code
    store.py                      # persistance (config + état) via helpers.storage.Store
    security.py                   # hash/vérif du code, contrôle « admin ou code »
    engine.py                     # ParentalEngine : boucle, usage, application, avertissements, actions
    calendar_source.py            # lecture des événements journée entière d'une entité calendar
    services.py  services.yaml    # services HA
    websocket.py                  # parental_control/config/get|set, parental_control/state
    sensor.py binary_sensor.py button.py switch.py
    strings.json translations/fr.json
    adapters/__init__.py          # build_adapter(hass, resource) -> Adapter
    adapters/base.py              # protocole Adapter
    adapters/media_player.py adapters/adguard.py adapters/nintendo.py
    core/__init__.py
    core/model.py                 # dataclasses et enums
    core/config_io.py             # parse/validate/dump de la config JSON
    core/daytype.py               # type de jour
    core/decisions.py             # décisions parent + usage, (dé)sérialisation, purge
    core/evaluator.py             # evaluate() -> Snapshot, closures
  tests/
    core/test_config_io.py test_daytype.py test_decisions.py test_evaluator_access.py test_evaluator_quota.py
    ha/conftest.py test_config_flow.py test_adapters.py test_engine.py test_services.py test_entities.py test_websocket.py
```

---

### Task 1: Repo, modèle et configuration JSON

**Files:**
- Create : `pyproject.toml`, `requirements_test.txt`, `hacs.json`, `README.md`, `.gitignore`, `custom_components/parental_control/core/{__init__,model,config_io}.py`
- Move : la spec et ce plan depuis `adguard-parental-card/docs/superpowers/` vers le nouveau repo (même chemin relatif)
- Test : `tests/core/test_config_io.py`

**Interfaces:**
- Produces (`core/model.py`, dataclasses `frozen=True`, enums `StrEnum`) :
  - `DayType`: `ECOLE="ecole"`, `FIN_DE_SEMAINE="fin_de_semaine"`, `CONGE_PEDA="conge_peda"`, `VACANCES="vacances"`
  - `SegmentType`: `BLOQUE="bloque"`, `LIBRE="libre"`, `APRES_DEVOIRS="apres_devoirs"`, `QUOTA="quota"`, `SUR_DEMANDE="sur_demande"`
  - `ResourceMode`: `SUIT_FRISE="suit_frise"`, `SUR_DEMANDE="sur_demande"`, `BLOQUE="bloque"`, `LIBRE="libre"`
  - `ResourceKind`: `MEDIA_PLAYER="media_player"`, `ADGUARD="adguard_services"`, `NINTENDO="nintendo"`
  - `Segment(start: datetime.time, type: SegmentType, warn_minutes: int = 5)` — se termine au début du suivant ou à 24:00
  - `Profile(segments: tuple[Segment, ...], quota_minutes: int | None = None)` — quota = budget journalier de l'enfant
  - `Kid(id: str, name: str, emoji: str | None, color: str | None, calendar: str | None, profiles: Mapping[DayType, Profile], resource_modes: Mapping[str, ResourceMode], leisure_add: frozenset[str], leisure_remove: frozenset[str])` + méthode `profile_for(day: DayType) -> Profile` (repli : `CONGE_PEDA`/`VACANCES` absents → `FIN_DE_SEMAINE`)
  - `Resource(id: str, name: str, kind: ResourceKind, owners: tuple[str, ...], options: Mapping[str, Any], quota_minutes: Mapping[DayType, int])`
  - `Config(kids: tuple[Kid, ...], resources: tuple[Resource, ...], default_leisure: tuple[str, ...], calendar_map: Mapping[str, DayType], notify: tuple[str, ...])` + `kid(id)`, `resource(id)`, `leisure_for(kid_id) -> frozenset[str]`, `leisure_for_resource(resource_id) -> frozenset[str]` (union des listes des propriétaires)
- Produces (`core/config_io.py`) : `class ConfigError(ValueError)`, `parse_config(data: dict) -> Config`, `dump_config(cfg: Config) -> dict`, `DEFAULT_LEISURE = ("youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch")`

Format JSON (exact, utilisé par l'import, le WebSocket et le stockage) :

```json
{
  "version": 1,
  "default_leisure": ["youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch"],
  "calendar_map": {"pédagogique": "conge_peda", "vacances": "vacances", "relâche": "vacances"},
  "notify": ["notify.mobile_app_iphone_de_olivier"],
  "kids": [{
    "id": "gabin", "name": "Gabin", "emoji": "🎮", "color": "#FF6B6B", "calendar": "calendar.ecole_primaire",
    "leisure_add": [], "leisure_remove": [],
    "resource_modes": {"switch": "sur_demande"},
    "profiles": {
      "ecole": {"segments": [{"start": "00:00", "type": "bloque"}, {"start": "15:25", "type": "libre"},
                             {"start": "16:00", "type": "apres_devoirs"}, {"start": "19:00", "type": "bloque"}]},
      "fin_de_semaine": {"quota_minutes": 120,
                         "segments": [{"start": "00:00", "type": "bloque"}, {"start": "08:00", "type": "quota"},
                                      {"start": "20:00", "type": "bloque"}]}
    }
  }],
  "resources": [
    {"id": "tv", "name": "Télé salon", "kind": "media_player", "owners": ["gabin"],
     "entity_id": "media_player.tv_salon", "notify_service": null, "quota_minutes": {"fin_de_semaine": 180}},
    {"id": "iphone_gabin", "name": "iPhone Gabin", "kind": "adguard_services", "owners": ["gabin"], "client": "iphone_gabin"},
    {"id": "switch", "name": "Switch", "kind": "nintendo", "owners": ["gabin"],
     "device_id": "b64d274dc045916f9a6de862a104fbb5",
     "limit_entity": "number.switch_papa_temps_d_ecran_max_aujourd_hui",
     "remaining_entity": "sensor.switch_papa_temps_d_ecran_restant",
     "used_entity": "sensor.switch_papa_temps_d_ecran_utilise"}
  ]
}
```

Les clés propres à un `kind` (`entity_id`, `notify_service`, `client`, `device_id`, `*_entity`) vont dans `Resource.options`.

- [ ] **Step 1: Créer le repo** — `git init` dans `/Users/olivier/dev/github.com/cesbron-dev/ha-parental-control`, déplacer spec et plan (`git mv` impossible entre repos : copier puis `git rm` côté `adguard-parental-card` dans un commit séparé de ce repo-là), `.gitignore` (`__pycache__/`, `.venv/`, `.pytest_cache/`, `.superpowers/`), `pyproject.toml` (`[tool.pytest.ini_options] asyncio_mode = "auto"`, `testpaths = ["tests"]`), `requirements_test.txt` (`pytest-homeassistant-custom-component` version compatible HA 2026.10), venv Python 3.14.

- [ ] **Step 2: Écrire les tests qui échouent** (`tests/core/test_config_io.py`)
  - `test_parse_example_config` : l'exemple ci-dessus → `cfg.kid("gabin").profile_for(DayType.ECOLE).segments[1] == Segment(time(15, 25), SegmentType.LIBRE)` ; `cfg.resource("tv").options["entity_id"] == "media_player.tv_salon"` ; `cfg.resource("tv").quota_minutes[DayType.FIN_DE_SEMAINE] == 180`.
  - `test_round_trip` : `parse_config(dump_config(parse_config(EX))) == parse_config(EX)`.
  - `test_profile_must_start_at_midnight` : premier segment `"00:30"` → `ConfigError`.
  - `test_segments_strictly_increasing` : `16:00` puis `15:25` → `ConfigError`.
  - `test_ecole_and_fin_de_semaine_required` : profil `ecole` absent → `ConfigError`.
  - `test_profile_fallback` : `kid.profile_for(DayType.VACANCES) is kid.profile_for(DayType.FIN_DE_SEMAINE)`.
  - `test_unknown_owner_rejected` : owner `"zoe"` inexistant → `ConfigError`.
  - `test_resource_mode_unknown_resource_rejected` : `resource_modes: {"xbox": "libre"}` → `ConfigError`.
  - `test_kind_options_required` : `adguard_services` sans `client` → `ConfigError` ; `media_player` sans `entity_id` → `ConfigError` ; `nintendo` sans `device_id` → `ConfigError`.
  - `test_leisure_for` : `leisure_add=["minecraft"]`, `leisure_remove=["twitch"]` → contient `minecraft`, pas `twitch`, contient `youtube`.
  - `test_leisure_for_resource_is_union_of_owners`.

- [ ] **Step 3: Lancer** `pytest tests/core/test_config_io.py -v` → FAIL (`ModuleNotFoundError`).
- [ ] **Step 4: Implémenter** `core/model.py` et `core/config_io.py` (validation à la main, sans voluptuous : le noyau reste pur ; messages d'erreur en français citant le chemin, ex. `kids[0].profiles.ecole.segments[1]`).
- [ ] **Step 5: Lancer** les tests → PASS.
- [ ] **Step 6: Commit** `feat: modèle et configuration JSON du moteur`.

---

### Task 2: Type de jour

**Files:** Create `core/daytype.py` · Test `tests/core/test_daytype.py`

**Interfaces:**
- Consumes : `DayType`, `Config.calendar_map`.
- Produces : `AllDayEvent(summary: str, start: date, end: date)` (`end` exclusif, comme HA) ; `day_type(day: date, events: Sequence[AllDayEvent], calendar_map: Mapping[str, DayType]) -> DayType`.

Correspondance : une clé de `calendar_map` correspond si elle est contenue dans le titre, comparaison **insensible à la casse et aux accents** (`unicodedata` NFKD). Priorité : `VACANCES` > `CONGE_PEDA` > défaut (lun–ven `ECOLE`, sam–dim `FIN_DE_SEMAINE`). Un mapping vers `ECOLE` ou `FIN_DE_SEMAINE` est autorisé et a la priorité la plus basse parmi les événements.

- [ ] **Step 1: Tests**
  - `test_weekday_default` : mardi 2026-10-27 sans événement → `ECOLE` ; samedi 2026-10-31 → `FIN_DE_SEMAINE`.
  - `test_conge_peda_matches_accent_insensitive` : `"Congé PEDAGOGIQUE"` le 2026-10-27 → `CONGE_PEDA`.
  - `test_multi_day_vacation_covers_weekend` : `"Vacances de Noël"` du 2026-12-21 au 2027-01-05 → le samedi 2026-12-26 est `VACANCES`.
  - `test_end_is_exclusive` : événement 27→28 : le 28 n'est pas couvert.
  - `test_vacances_beats_conge_peda` : les deux le même jour → `VACANCES`.
  - `test_unmapped_event_ignored` : `"Photo scolaire"` → `ECOLE`.
- [ ] **Step 2:** `pytest tests/core/test_daytype.py -v` → FAIL.
- [ ] **Step 3:** Implémenter `day_type`.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat: calcul du type de jour`.

---

### Task 3: Décisions parent et usage

**Files:** Create `core/decisions.py` · Test `tests/core/test_decisions.py`

**Interfaces:**
- Produces :
  - `Target(resource_id: str | None = None, kid_id: str | None = None, service: str | None = None)` — cas valides : `resource_id` seul (ressource entière) ; `resource_id + service` (un service sur un appareil) ; `kid_id + service` (un service sur tous les appareils AdGuard de l'enfant) ; `service` seul (sur tous les appareils AdGuard).
  - `ManualException(id: str, target: Target, open: bool, created: datetime, until: datetime | None, signature: tuple | None)` — `until=None` ⇒ « jusqu'à la prochaine décision », expirée quand la signature de la règle change (calculée par l'évaluateur, tâche 5).
  - `Timer(kid_id: str, start: datetime, end: datetime)` ; arrêt anticipé = `end` ramené à l'heure d'arrêt.
  - `Bonus(day: date, minutes: int, kid_id: str | None = None, resource_id: str | None = None)`.
  - `Decisions` (mutable) : `homework_done: dict[str, date]`, `bonuses: list[Bonus]`, `exceptions: list[ManualException]`, `timers: list[Timer]`, `paused: bool`, `resource_usage: dict[tuple[str, date], float]` (minutes), et méthodes :
    - `homework_done_on(kid_id, day) -> bool`
    - `bonus_minutes(day, *, kid_id=None, resource_id=None) -> int`
    - `active_timer(kid_id, now) -> Timer | None`
    - `kid_timer_minutes(kid_id, day, now) -> float` (somme de `min(now, end) - start` des minuteurs du jour)
    - `add_usage(resource_id, day, minutes)` / `usage(resource_id, day) -> float`
    - `purge(now: datetime) -> None` : retire devoirs, bonus, usage et minuteurs **d'avant aujourd'hui** ; retire les exceptions avec `until <= now`. Garde une exception avec durée qui franchit minuit.
    - `to_dict() -> dict` / `Decisions.from_dict(d: dict) -> Decisions` (datetimes ISO avec fuseau ; dates ISO).

- [ ] **Step 1: Tests**
  - `test_round_trip_all_fields` (une instance de chaque, `paused=True`).
  - `test_purge_drops_yesterday_homework_and_bonus`.
  - `test_purge_keeps_exception_crossing_midnight` : créée 23:50 avec `until` 00:20, purge à 00:05 → conservée ; purge à 00:21 → retirée.
  - `test_purge_keeps_until_next_decision_exception` (`until=None`).
  - `test_kid_timer_minutes_counts_elapsed_only` : minuteur 14:00→14:30, `now=14:10` → `10.0` ; `now=15:00` → `30.0`.
  - `test_bonus_minutes_filters_target_and_day`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat: décisions parent et usage persistables`.

---

### Task 4: Évaluateur — accès (frise, modes, devoirs, partage, pause)

**Files:** Create `core/evaluator.py` · Test `tests/core/test_evaluator_access.py`

**Interfaces:**
- Consumes : `Config`, `Decisions`, `DayType`.
- Produces :
  - `KidStatus(StrEnum)` : `AUTORISE="autorise"`, `BLOQUE="bloque"`, `ATTENTE_DEVOIRS="attente_devoirs"`, `ATTENTE_MINUTEUR="attente_minuteur"`, `QUOTA_EPUISE="quota_epuise"`, `SUR_DEMANDE="sur_demande"`, `PAUSE="pause"`
  - `KidState(status: KidStatus, reason: str, day_type: DayType, segment: SegmentType, segment_end: datetime, until: datetime | None, remaining_minutes: float | None, timer_end: datetime | None)`
  - `ResourceState(open: bool, reason: str, until: datetime | None, used_minutes: float | None, remaining_minutes: float | None, blocked_services: frozenset[str])` — pour `adguard_services`, `open` = « les loisirs sont ouverts » et `blocked_services` = services loisirs à bloquer (+/− exceptions de service) ; pour les autres `blocked_services` est vide.
  - `Snapshot(kids: dict[str, KidState], resources: dict[str, ResourceState], expired_exception_ids: frozenset[str])`
  - `evaluate(now: datetime, cfg: Config, dec: Decisions, day_types: Mapping[str, DayType], *, apply_exceptions: bool = True) -> Snapshot` — `now` est conscient du fuseau ; le segment courant se trouve en comparant `now.time()` (heure murale) aux `Segment.start`.

Règles d'accès d'un couple (enfant, ressource), dans l'ordre :
1. `dec.paused` → fermé (`PAUSE`), y compris contre les exceptions.
2. mode de la ressource pour l'enfant ≠ `SUIT_FRISE` → le mode remplace le type de segment.
3. type `BLOQUE` → fermé ; `LIBRE` → ouvert ; `APRES_DEVOIRS` → ouvert ssi `homework_done_on(kid, today)` ; `SUR_DEMANDE` → fermé (seule une exception l'ouvre) ; `QUOTA` → voir tâche 5 (ici : fermé, pour que les tests de cette tâche ne dépendent pas des quotas).
4. Ressource : ouverte ssi au moins un propriétaire y a accès (OU). Ressource `nintendo` : `open` reflète la règle à titre informatif (l'adaptateur ne ferme pas, tâche 7).
5. Exceptions (si `apply_exceptions`) : une exception sur la ressource ou sur un de ses services remplace le résultat pour sa cible.

Statut de l'enfant = le résultat de la frise (sans mode par ressource), raisons en français, ex. `"Devoirs à terminer"`, `"Écrans autorisés jusqu'à 19:00"`, `"Écrans en pause"`.

- [ ] **Step 1: Tests** (fixture : config d'exemple de la tâche 1 complétée par Léo, même profil que Gabin, et Maël `00:00 bloque → 16:15 apres_devoirs → 19:00 bloque` ; `tz = ZoneInfo("America/Toronto")`)
  - `test_gabin_free_window` : mardi 15:40 → Gabin `AUTORISE`, `until` = 16:00 du jour.
  - `test_gabin_waits_homework_at_1630` : → `ATTENTE_DEVOIRS`, TV fermée si personne n'y a droit.
  - `test_homework_done_opens_until_19` : `homework_done["gabin"] = today`, 16:30 → `AUTORISE`, `until` 19:00.
  - `test_after_19_blocked_even_with_homework`.
  - `test_shared_tv_open_if_any_owner_allowed` : Gabin devoirs faits, Léo non, 16:30 → TV `open=True`, iPhone de Léo fermé.
  - `test_switch_sur_demande_mode_overrides_timeline` : `resource_modes={"switch": "sur_demande"}`, 15:40 → Switch fermée alors que Gabin est `AUTORISE`.
  - `test_pause_beats_everything` : `paused=True` + exception d'ouverture → tout fermé, statut `PAUSE`.
  - `test_adguard_blocked_services_are_leisure_only` : iPhone fermé → `blocked_services == cfg.leisure_for_resource("iphone_gabin")`.
  - `test_service_exception_opens_one_service` : exception `Target(resource_id="iphone_gabin", service="youtube"), open=True` → `youtube` absent de `blocked_services`, `roblox` présent.
  - `test_kid_service_exception_applies_to_all_kid_devices` : `Target(kid_id="gabin", service="youtube")`.
  - `test_dst_end_day_uses_wall_clock` : dimanche 2026-11-01, Gabin en `fin_de_semaine` modifié en `libre` dès 08:00 → à 08:30 heure locale `AUTORISE` ; `segment_end` = 20:00 locale du même jour (*Review Focus 4*).
- [ ] **Step 2:** → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat: évaluateur d'accès (frise, devoirs, partage, pause)`.

---

### Task 5: Évaluateur — quotas, minuteurs, exceptions « jusqu'à la prochaine décision », fermetures à venir

**Files:** Modify `core/evaluator.py` · Test `tests/core/test_evaluator_quota.py`

**Interfaces:**
- Consumes : tâche 4.
- Produces :
  - segment `QUOTA` (complète la règle 3 de la tâche 4) :
    - ressource **mesurable** (`media_player` avec `quota_minutes[day_type]`) : ouverte ssi `quota + bonus_minutes(resource_id=…) - usage(resource) > 0` ; sans quota pour ce type de jour → ouverte jusqu'à la fin du segment.
    - ressource **non mesurable** (`adguard_services`) : ouverte ssi minuteur actif pour l'enfant **et** reste enfant > 0, où reste enfant = `profile.quota_minutes + bonus_minutes(kid_id=…) - kid_timer_minutes(…)`.
    - statut enfant : reste ≤ 0 → `QUOTA_EPUISE` ; minuteur actif → `AUTORISE` (`until` = min(fin minuteur, épuisement, fin de segment)) ; sinon `ATTENTE_MINUTEUR`.
  - `rule_signature(target: Target, snap: Snapshot, cfg: Config) -> tuple` : l'état de la règle (sans exceptions) pour chaque couple (ressource, service) couvert par la cible, dans un ordre stable.
  - `evaluate` : calcule d'abord sans exceptions ; une exception `until=None` dont `signature != rule_signature(...)` actuelle est listée dans `expired_exception_ids` et ignorée.
  - `upcoming_closures(now, cfg, dec, day_types) -> dict[str, datetime]` : pour chaque cible actuellement ouverte (clés `"kid:<id>"` et `"resource:<id>"`), la prochaine heure où elle se ferme. Candidats : débuts de segment du jour et minuit, fin de minuteur, `until` d'exception, épuisement de quota projeté (uniquement si la ressource est en usage — l'appelant passe `in_use: Mapping[str, bool]`). Méthode : réévaluer à chaque candidat en projetant l'usage, retenir le premier où la cible est fermée.
  - signature finale : `upcoming_closures(now, cfg, dec, day_types, in_use: Mapping[str, bool]) -> dict[str, datetime]`.

- [ ] **Step 1: Tests** (samedi 2026-10-31, profil `fin_de_semaine` quota 120 min de la tâche 1)
  - `test_tv_quota_open_until_exhausted` : TV quota 180, usage 170 → ouverte, `remaining_minutes == 10` ; usage 180 → fermée.
  - `test_tv_bonus_extends_resource_quota` : usage 180 + `Bonus(resource_id="tv", minutes=30)` → ouverte, reste 30.
  - `test_adguard_closed_without_timer` : 10:00, pas de minuteur → iPhone fermé, Gabin `ATTENTE_MINUTEUR`.
  - `test_timer_opens_adguard_and_counts_quota` : minuteur 10:00→10:30, `now=10:10` → ouvert, reste Gabin `110`, `until` 10:30.
  - `test_timer_cut_by_quota_exhaustion` : 110 min déjà consommées, minuteur 30 min → `until` = début + 10 min.
  - `test_timer_cut_by_segment_end` : minuteur 19:45→20:15 → `until` 20:00.
  - `test_quota_exhausted_status` : 120 consommées → `QUOTA_EPUISE`.
  - `test_until_next_decision_expires_on_rule_change` : mardi 15:40, exception fermeture TV `until=None` avec signature calculée à 15:40 ; à 16:30 (Gabin attente devoirs → règle change) → id dans `expired_exception_ids`.
  - `test_until_next_decision_holds_while_rule_unchanged` : même exception à 15:55 → toujours appliquée.
  - `test_upcoming_closure_at_segment_end` : mardi 15:40 → `"kid:gabin"` = 16:00.
  - `test_upcoming_closure_quota_projection_only_when_in_use` : TV reste 10 min, `in_use={"tv": True}` → `now+10 min` ; `False` → fin de segment.
- [ ] **Step 2:** → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS, et `pytest tests/core -v` tout vert.
- [ ] **Step 5: Commit** `feat: quotas, minuteurs et fermetures à venir`.

---

### Task 6: Squelette d'intégration, stockage, code parent, adaptateurs TV et AdGuard

**Files:** Create `manifest.json`, `const.py`, `__init__.py` (setup minimal), `config_flow.py`, `store.py`, `security.py`, `adapters/{__init__,base,media_player,adguard}.py`, `strings.json`, `translations/fr.json` · Test `tests/ha/conftest.py`, `tests/ha/test_config_flow.py`, `tests/ha/test_adapters.py`

**Interfaces:**
- `manifest.json` : `{"domain": "parental_control", "name": "Contrôle parental", "version": "0.1.0", "config_flow": true, "iot_class": "calculated", "integration_type": "service", "dependencies": [], "after_dependencies": ["calendar", "media_player", "notify"], "requirements": [], "codeowners": ["@cesbron-dev"], "documentation": "https://github.com/cesbron-dev/ha-parental-control"}`
- `const.py` : `DOMAIN = "parental_control"`, `SIGNAL_UPDATE = "parental_control_update"`, `EVENT_WARNING = "parental_control_warning"`, `TICK_SECONDS = 60`, `STORE_VERSION = 1`.
- `security.py` : `hash_code(code: str) -> str` (`pbkdf2_hmac("sha256", …, 200_000)`, sel aléatoire, format `"pbkdf2$<sel hex>$<hash hex>"`) ; `verify_code(code: str, stored: str) -> bool` (`hmac.compare_digest`) ; `async check_unlock(hass, context: Context, code: str | None, stored_hash: str) -> None` lève `ServiceValidationError` (clé de traduction `code_required` / `code_invalid`) si l'utilisateur n'est pas admin et que le code manque ou est faux ; contexte sans `user_id` (automatisation) → autorisé.
- `config_flow.py` : instance unique (`async_set_unique_id(DOMAIN)`), étape `user` avec `code` (4 à 8 chiffres) → `entry.data = {"code_hash": hash_code(code)}` ; options flow : changer le code.
- `store.py` : `class ParentalStore` avec `async load() -> tuple[Config | None, Decisions]`, `async save_config(cfg: Config)`, `async save_state(dec: Decisions)` (deux `Store` : `parental_control.config`, `parental_control.state` ; `save_state` via `async_delay_save` 1 s).
- `adapters/base.py` :
  ```python
  class Adapter(Protocol):
      resource: Resource
      def entity_ids(self) -> list[str]: ...           # entités à écouter (dérive)
      def in_use(self) -> bool: ...                    # pour le décompte d'usage ; False si non mesurable
      def drifted(self, desired: ResourceState) -> bool: ...  # l'état réel contredit un état fermé attendu
      async def apply(self, desired: ResourceState) -> None: ...
      async def warn(self, message: str) -> None: ...
      async def grant(self, minutes: int) -> None: ...  # NotImplementedError sauf nintendo
      async def force_close(self) -> None: ...         # utilisé par la pause
  ```
  `build_adapter(hass, resource) -> Adapter`.
- `media_player` : `in_use` ⇔ état ∈ `{"on", "playing", "paused", "idle", "buffering"}` ; `apply(closed)` → `media_player.turn_off` seulement si `in_use` ; `apply(open)` → rien ; `drifted` ⇔ fermé attendu et `in_use` ; `warn` → `notify_service` s'il est configuré (`{"message": …}`), sinon rien ; `force_close` = `apply(closed)`.
- `adguard` : entité = `f"switch.adguard_{client}_svc_{service}"` ; `apply(desired)` : pour chaque service de `leisure_for_resource ∪ services visés par une exception`, `switch.turn_on` si le service doit être bloqué et que l'état est `off`, `switch.turn_off` si débloqué et `on` ; entité absente → `_LOGGER.warning` une fois par entité, on continue ; `in_use` → False ; `drifted` ⇔ un service de `blocked_services` est `off` ; `warn` → rien (l'événement est émis par le moteur).

- [ ] **Step 1: Tests**
  - `test_config_flow_creates_entry_with_hashed_code` ; `test_config_flow_single_instance` (abort `already_configured`) ; `test_options_flow_changes_code`.
  - `test_verify_code` (bon/mauvais) ; `test_check_unlock_admin_needs_no_code` ; `test_check_unlock_non_admin_requires_code` (sans code → `ServiceValidationError`, mauvais code → idem, bon code → OK) — utilisateurs créés avec `hass.auth.async_create_user`, groupe `system-users` pour le non-admin.
  - `test_media_player_turn_off_when_closed_and_on` (`async_mock_service(hass, "media_player", "turn_off")` appelé une fois avec `entity_id`).
  - `test_media_player_unavailable_is_not_in_use` : état `unavailable` → `in_use()` False, `apply(closed)` n'appelle rien, `drifted` False (*Review Focus 2*).
  - `test_adguard_blocks_only_leisure_services` : switches `youtube`, `roblox` à `off`, `khanacademy` à `off` hors loisirs → `turn_on` pour youtube et roblox seulement.
  - `test_adguard_no_call_when_already_in_state`.
  - `test_adguard_missing_entity_logs_and_continues` (`caplog` contient l'entity_id, les autres services sont appliqués).
- [ ] **Step 2:** `pytest tests/ha -v` → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat: squelette d'intégration, code parent, adaptateurs TV et AdGuard`.

---

### Task 7: Adaptateur Nintendo

**Files:** Create `adapters/nintendo.py` · Modify `adapters/__init__.py` · Test `tests/ha/test_adapters.py`

**Interfaces:**
- `grant(minutes)` : découpe en tranches de 30 max (`45` → `30`, `15`), appels `nintendo_parental_controls.add_bonus_time` `{"device_id": …, "bonus_time": n}` séparés de `asyncio.sleep(5)` (délai injectable par attribut `_slice_delay` pour les tests) ; une erreur (`HomeAssistantError`) sur une tranche est réessayée une fois après 5 s, puis l'erreur remonte.
- `apply(desired)` → **rien** (le moteur ne coupe jamais une partie) ; `drifted` → False ; `in_use` → False (l'usage vient des capteurs Nintendo) ; `warn` → rien (la console avertit).
- `force_close()` (pause) → `number.set_value` `{"entity_id": limit_entity, "value": 0}`. **À vérifier sur l'instance de test** que cela coupe bien un bonus en cours ; sinon, documenter la limite dans le README (la pause ne coupe pas la Switch) — pas de contournement par API.
- `used_minutes()` / `remaining_minutes()` lisent `used_entity` / `remaining_entity` (float, `None` si indisponible) : le moteur les reporte dans `ResourceState` de la Switch.

- [ ] **Step 1: Tests** `test_nintendo_grant_slices_30_min` (45 → deux appels `30` puis `15`) ; `test_nintendo_grant_waits_between_slices` (`_slice_delay` mocké, `asyncio.sleep` appelé avec 5 en vrai délai par défaut) ; `test_nintendo_retries_once_on_error` ; `test_nintendo_apply_never_touches_limit` ; `test_nintendo_force_close_sets_limit_zero`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat: adaptateur Nintendo`.

---

### Task 8: Moteur (boucle, usage, application, dérive, avertissements, calendrier)

**Files:** Create `engine.py`, `calendar_source.py` · Modify `__init__.py` · Test `tests/ha/test_engine.py`

**Interfaces:**
- `calendar_source.py` : `async fetch_all_day_events(hass, entity_id: str, day: date) -> list[AllDayEvent]` via `calendar.get_events` (`return_response=True`, fenêtre = le jour local) ; ne garde que les événements dont `start` est une date (journée entière) ; toute erreur → `[]` + `_LOGGER.warning`.
- `class ParentalEngine` :
  - `__init__(hass, entry, store)` ; `async async_start()` : charge, construit les adaptateurs, purge, réapplique tout (resynchronisation), démarre `async_track_time_interval(TICK_SECONDS)`, écoute `async_track_state_change_event` sur `entity_ids()` de tous les adaptateurs, et recalcule les types de jour au démarrage, à minuit local (`async_track_time_change(hour=0, minute=0, second=5)`) et toutes les 15 min.
  - `async async_evaluate(reason: str) -> None` : (1) ajoute au compteur d'usage les minutes écoulées depuis le dernier passage pour chaque adaptateur `in_use()` ; (2) `dec.purge(now)` ; (3) `evaluate(...)` ; retire `expired_exception_ids` ; pour la ressource `nintendo`, remplace `used_minutes`/`remaining_minutes` du `ResourceState` par les valeurs des capteurs Nintendo (tâche 7) ; (4) pour chaque ressource, `apply` si l'état voulu diffère du dernier appliqué **ou** `drifted()` ; une exception d'adaptateur est journalisée et n'arrête pas les autres ; (5) `upcoming_closures(...)` : pour chaque clé dont la fermeture tombe dans `warn_minutes` et pas encore avertie (`self._warned: set[tuple[str, datetime]]`) → `hass.bus.async_fire(EVENT_WARNING, {"target": key, "closes_at": iso, "message": …})`, `adapter.warn(message)` pour les ressources, `notify.*` de `cfg.notify` avec le message ; (6) `save_state` ; (7) `async_dispatcher_send(hass, SIGNAL_UPDATE)`.
  - Propriétés lues par les entités : `snapshot: Snapshot | None`, `config: Config | None`, `decisions: Decisions`, `closures: dict[str, datetime]`.
  - Actions (appelées par les services, tâche 9 ; aucune vérification de code ici) : `async homework_done(kid_id)`, `async add_bonus(minutes, *, kid_id=None, resource_id=None)` (ressource `nintendo` → `adapter.grant`), `async add_exception(target: Target, open: bool, minutes: int | None) -> str` (calcule la `signature` si `minutes is None`), `async cancel_exception(exc_id)`, `async start_timer(kid_id, minutes)` (plafonné au reste du quota ; `ServiceValidationError` si reste ≤ 0 ou si l'enfant n'est pas dans un segment `QUOTA`), `async stop_timer(kid_id)`, `async set_pause(on: bool)` (on → `force_close()` sur tous les adaptateurs), `async set_config(cfg: Config)` (reconstruit adaptateurs et écoutes). Chacune modifie `decisions` puis appelle `async_evaluate`.
  - Message d'avertissement : `f"{nom} : fin des écrans dans {n} min"` (enfant) / `f"{nom ressource} : coupure dans {n} min"` (ressource).

- [ ] **Step 1: Tests** (`freezer` de pytest-homeassistant-custom-component, `async_fire_time_changed`, services mockés, config de la tâche 1 chargée dans le store)
  - `test_tick_turns_off_tv_at_16` : mardi 15:59 TV `on`, avancer à 16:01 → `media_player.turn_off` appelé.
  - `test_warning_fired_5_min_before` : 15:54 → aucun événement ; 15:55 → un `parental_control_warning` pour `kid:gabin` ; 15:56 → pas de second.
  - `test_tv_usage_accumulates_only_when_on` : samedi, 10 ticks TV `on` puis 10 `off` → `usage("tv") == 10`.
  - `test_tv_turned_back_on_is_turned_off_again` (dérive) : 16:30 sans devoirs, état TV passe `on` → `turn_off` rappelé sans attendre le tick.
  - `test_no_duplicate_commands` : 5 ticks en état stable → au plus un appel par entité.
  - `test_restart_restores_decisions_and_keeps_closed` : devoirs faits + minuteur 30 min enregistrés, déchargement puis rechargement de l'entrée 40 min plus tard → devoirs toujours faits, minuteur expiré, services AdGuard bloqués (*Review Focus 1*).
  - `test_missing_entity_does_not_stop_other_resources` : client AdGuard inexistant + TV valide → TV appliquée, avertissement journalisé (*Review Focus 3*).
  - `test_calendar_failure_falls_back_to_weekday` : `calendar.get_events` lève → mardi évalué `ECOLE` (*Review Focus 5*).
  - `test_calendar_conge_peda_switches_profile` : événement journée entière « Congé pédagogique » → `snapshot.kids["gabin"].day_type == CONGE_PEDA`.
  - `test_start_timer_capped_to_remaining_quota` : reste 20, demande 30 → minuteur de 20 min.
  - `test_pause_force_closes_all` : `set_pause(True)` → `turn_off` TV, `number.set_value` 0, loisirs AdGuard bloqués.
  - `test_nintendo_bonus_goes_through_grant`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat: moteur d'application des règles`.

---

### Task 9: Services HA avec code parent

**Files:** Create `services.py`, `services.yaml` · Modify `__init__.py`, `strings.json`, `translations/fr.json` · Test `tests/ha/test_services.py`

**Interfaces:**
- Services du domaine `parental_control` (schémas voluptuous ; `code` optionnel partout) :
  | Service | Champs | Débloque ? |
  |---|---|---|
  | `devoirs_termines` | `kid_id` | oui |
  | `ajouter_bonus` | `minutes` (1–240), `kid_id` **ou** `resource_id` | oui |
  | `exception` | `open` (bool), `resource_id?`, `kid_id?`, `service?`, `minutes?` (absent = jusqu'à la prochaine décision) ; renvoie `{"id": …}` (`SupportsResponse.OPTIONAL`) | oui si `open` |
  | `annuler_exception` | `exception_id` | oui si l'exception annulée fermait |
  | `demarrer_minuteur` | `kid_id`, `minutes` (1–240) | oui |
  | `arreter_minuteur` | `kid_id` | non |
  | `pause` | `active` (bool) | oui si `active=false` |
  | `importer_configuration` | `config` (dict, format tâche 1) | **admin uniquement** (`Unauthorized` sinon) |
- Chaque service « débloque » appelle `security.check_unlock(hass, call.context, call.data.get("code"), entry.data["code_hash"])` avant l'action du moteur. Ids inconnus → `ServiceValidationError` (clé `unknown_kid` / `unknown_resource`). `ConfigError` à l'import → `ServiceValidationError` avec le message.

- [ ] **Step 1: Tests** `test_homework_requires_code_for_non_admin` ; `test_homework_admin_without_code` ; `test_close_exception_never_requires_code` ; `test_unpause_requires_code_pause_does_not` ; `test_exception_returns_id_and_can_be_cancelled` ; `test_import_configuration_admin_only` ; `test_import_invalid_config_raises_validation_error` ; `test_unknown_kid_rejected`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat: services du contrôle parental`.

---

### Task 10: Entités

**Files:** Create `sensor.py`, `binary_sensor.py`, `button.py`, `switch.py` · Modify `__init__.py` (plateformes), traductions · Test `tests/ha/test_entities.py`

**Interfaces:** (entités sous un appareil par enfant et par ressource, `has_entity_name=True`, `unique_id = f"{entry_id}_{kind}_{id}_{clé}"`, mises à jour sur `SIGNAL_UPDATE`)
- Par enfant : `sensor` « Statut » (état = `KidStatus`, `device_class=ENUM`, attributs `reason`, `until`, `remaining_minutes`, `day_type`, `segment`, `segment_end`, `timer_end`, `closes_at`, `exceptions` (liste `{id, target, open, until}`)) ; `button` « Devoirs terminés ».
- Par ressource : `binary_sensor` « Autorisée » ; `sensor` « Temps utilisé » et « Temps restant » (`device_class=DURATION`, `min`, absent si non mesurable) ; pour AdGuard, attribut `blocked_services` sur « Autorisée ».
- Global : `switch` « Pause générale ».
- **Code sur les entités** : `button.async_press` et `switch.async_turn_off` appellent `check_unlock` avec `self._context` et `code=None` → un utilisateur non admin ne peut pas les déclencher (il doit passer par le service avec `code`, ce que feront les cartes). `switch.async_turn_on` (pause) ne demande rien.
- Les entités sont recréées quand la config change (`set_config`) : enfants/ressources retirés → entités retirées du registre.

- [ ] **Step 1: Tests** `test_kid_status_sensor_reflects_snapshot` ; `test_resource_binary_sensor_and_durations` ; `test_button_press_non_admin_rejected` ; `test_button_press_admin_marks_homework` ; `test_pause_switch_turn_off_non_admin_rejected` ; `test_entities_follow_config_change`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS.
- [ ] **Step 5: Commit** `feat: entités enfants, ressources et pause`.

---

### Task 11: API WebSocket

**Files:** Create `websocket.py` · Modify `__init__.py` · Test `tests/ha/test_websocket.py`

**Interfaces:**
- `parental_control/config/get` → `{"config": dump_config(cfg) | None}` (tout utilisateur authentifié).
- `parental_control/config/set` `{"config": {...}}` → admin uniquement (`require_admin`), `parse_config` puis `engine.set_config` ; erreur `invalid_config` avec le message de `ConfigError`.
- `parental_control/state` → `{"kids": {id: KidState sérialisé}, "resources": {...}, "closures": {...}, "paused": bool, "exceptions": [...]}` ; et `parental_control/state/subscribe` qui pousse le même message à chaque `SIGNAL_UPDATE`.
- Sérialisation partagée avec les attributs d'entités : fonction `serialize_snapshot(engine) -> dict` dans `websocket.py`, réutilisée par `sensor.py`.

- [ ] **Step 1: Tests** `test_config_get_set_round_trip` ; `test_config_set_non_admin_rejected` ; `test_config_set_invalid_returns_error` ; `test_state_subscribe_pushes_on_update`.
- [ ] **Step 2:** → FAIL. **Step 3:** Implémenter. **Step 4:** → PASS ; `pytest -v` complet vert.
- [ ] **Step 5: Commit** `feat: API WebSocket de configuration et d'état`.

---

### Task 12: Déploiement sur l'instance de test et bascule

Pas de code produit : vérification réelle, à faire avec le MCP `home-assistant-test-addon` et avec Olivier pour les étapes physiques.

- [ ] **Step 1: README** : installation HACS (dépôt personnalisé), ajout de l'intégration, format JSON (renvoi vers la tâche 1), services, utilisateur tablette non admin, limites connues (résultat de la vérification Nintendo de la tâche 7). Commit `docs: README`.
- [ ] **Step 2: Pousser** le repo sur GitHub (`cesbron-dev/ha-parental-control`) — **demander confirmation à Olivier avant le push** — et l'ajouter comme dépôt personnalisé HACS sur l'instance de test, installer, redémarrer HA.
- [ ] **Step 3: Bascule** (demander confirmation avant chaque désactivation) : désactiver les scripts `script.mode_devoirs`, `script.mode_dodo`, `script.mode_libre`, `script.mode_tout_bloquer`, `script.switch_ajouter_bonus` et toute automatisation qui pilote `media_player.tv_salon` ou les switches `svc_*`. Laisser les helpers `tele_*` en place.
- [ ] **Step 4: Config** : ajouter l'intégration (code parent choisi par Olivier), puis `parental_control.importer_configuration` avec la config des trois enfants et des clients AdGuard **après** la reconfiguration AdGuard d'Olivier (un client par appareil).
- [ ] **Step 5: Vérifier** sur l'instance : `sensor.<enfant>_statut` cohérent avec l'heure ; `devoirs_termines` débloque les services AdGuard de l'enfant (switch `svc_*` à `off`) ; la TV allumée hors fenêtre est éteinte en moins d'une minute ; un `parental_control_warning` part 5 min avant une fin de fenêtre ; `ajouter_bonus` sur la Switch augmente `sensor.switch_papa_temps_d_ecran_restant` ; `pause` puis reprise (avec code depuis un utilisateur non admin). Noter tout écart dans le README ou en issue.
