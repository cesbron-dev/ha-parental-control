"""Moteur : relie le noyau pur à Home Assistant.

Chaque évaluation (`async_evaluate`, sérialisée par un verrou) :
1. ajoute l'usage écoulé (plafonné à 5 min) aux ressources en usage ;
2. purge les décisions échues ;
3. évalue la règle et retire les exceptions « jusqu'à la prochaine décision » échues ;
4. applique chaque ressource dont l'état voulu a changé ou qui a dérivé ;
5. avertit avant les fermetures prévisibles ;
6. enregistre les décisions et prévient les entités (`SIGNAL_UPDATE`).
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Coroutine, Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from homeassistant.components import persistent_notification
from homeassistant.components.logbook import async_log_entry
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    CoreState,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .adapters import build_adapter
from .adapters.simulation import SimulatedAdapter
from .calendar_source import fetch_all_day_events
from .const import DOMAIN, EVENT_WARNING, REQUESTS_PANEL_PATH, SIGNAL_UPDATE, TICK_SECONDS
from .core.daytype import AllDayEvent, day_type
from .core.decisions import Bonus, Decisions, ManualException, Target, Timer
from .core.evaluator import Snapshot, evaluate, rule_signature, upcoming_closures
from .core.label_services import switch_blocked
from .core.model import (
    Config,
    DayType,
    Kid,
    Resource,
    ResourceKind,
    SegmentType,
)
from .core.requests import (
    RequestBook,
    RequestError,
    RequestKind,
    RequestStatus,
    TimeRequest,
    action_choices,
    duration_label,
)
from .label_switches import LabelSwitch, LabelSwitchIssue, discover
from .store import INVALID_CONFIG_NOTIFICATION, ParentalStore
from .texts import server_language, text

_LOGGER = logging.getLogger(__name__)

MAX_ELAPSED = timedelta(minutes=5)
CALENDAR_REFRESH = timedelta(minutes=15)
DEFAULT_WARN_MINUTES = 5
DRIFT_COOLDOWN = timedelta(seconds=30)


def request_tag(request_id: str) -> str:
    """Étiquette de la notification d'une demande (remplacée ou retirée par `clear_notification`)."""
    return f"parental_control_{request_id}"


def _invalid(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


def _local(moment: datetime) -> datetime:
    """Heure locale (`dt_util.as_local`) au décalage UTC figé.

    Avec le fuseau lui-même, Python compare deux instants du même fuseau à l'heure
    murale : pendant l'heure répétée du passage à l'heure normale, 01:20 (heure normale)
    passerait avant 01:50 (heure d'été). Un décalage fixe garde l'heure murale locale
    (dates, affichage) et une comparaison sur l'instant réel.
    """
    local = dt_util.as_local(moment)
    return local.replace(tzinfo=timezone(local.utcoffset() or timedelta(0)))


def _after(now: datetime, minutes: float) -> datetime:
    """`now` + `minutes` de temps réel (calcul en UTC), en heure locale : une durée qui
    franchit un changement d'heure garde sa longueur réelle."""
    return _local(dt_util.as_utc(now) + timedelta(minutes=minutes))


def _localize(dec: Decisions) -> None:
    """Ramène à l'heure locale les instants relus (décalages quelconques de l'ISO)."""
    dec.timers = [replace(t, start=_local(t.start), end=_local(t.end)) for t in dec.timers]
    dec.exceptions = [
        replace(
            e,
            created=_local(e.created),
            until=None if e.until is None else _local(e.until),
        )
        for e in dec.exceptions
    ]


def _segment_warn_minutes(kid: Kid, dtype: DayType, now: datetime) -> int:
    """`warn_minutes` du segment courant de l'enfant."""
    wall = now.time().replace(tzinfo=None)
    segments = kid.profile_for(dtype).segments
    current = segments[0]
    for segment in segments:
        if segment.start <= wall:
            current = segment
    return current.warn_minutes


class ParentalEngine:
    """Boucle d'évaluation et actions parentales (sans vérification de code)."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, store: ParentalStore
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._store = store
        self._config: Config | None = None
        self._decisions = Decisions()
        self._snapshot: Snapshot | None = None
        self._closures: dict[str, datetime] = {}
        self._adapters: dict[str, SimulatedAdapter] = {}
        # Dernier état appliqué par ressource : (ouvert, services bloqués).
        self._applied: dict[str, tuple[bool, frozenset[str], frozenset[str]]] = {}
        # Entité pilotée -> ressources qui l'utilisent.
        self._entity_owners: dict[str, set[str]] = {}
        self._warned: set[tuple[str, datetime]] = set()
        # Événements par enfant, avec le jour local pour lequel ils ont été lus.
        self._events: dict[str, tuple[date, list[AllDayEvent]]] = {}
        # Dernier envoi de commande par ressource (anti-rafale des corrections de dérive).
        self._sent_at: dict[str, datetime] = {}
        # Interrupteurs labellisés : découverte, état voulu appliqué (allumé ?), bloqué ou non
        # au dernier passage, problèmes et avertissements déjà journalisés.
        self._label_switches: list[LabelSwitch] = []
        self._label_issues: list[LabelSwitchIssue] = []
        self._label_applied: dict[str, bool] = {}
        self._label_blocked: dict[str, bool | None] = {}
        self._label_reported: set[tuple[str, str, str]] = set()
        self._label_unavailable: set[str] = set()
        self._label_state_unsub: CALLBACK_TYPE | None = None
        self._last_eval: datetime | None = None
        self._requests = RequestBook()
        self._lock = asyncio.Lock()
        self._unsubs: list[CALLBACK_TYPE] = []
        self._state_unsub: CALLBACK_TYPE | None = None
        self._stopped = False
        # Faux tant que le premier calendrier et la première évaluation ne sont pas faits.
        self._ready = False

    # ------------------------------------------------------------------ lecture

    @property
    def store(self) -> ParentalStore:
        return self._store

    @property
    def snapshot(self) -> Snapshot | None:
        return self._snapshot

    @property
    def config(self) -> Config | None:
        return self._config

    @property
    def decisions(self) -> Decisions:
        return self._decisions

    @property
    def simulation(self) -> bool:
        return self._decisions.simulation

    @property
    def requests(self) -> RequestBook:
        return self._requests

    @property
    def closures(self) -> dict[str, datetime]:
        return self._closures

    @property
    def label_switches(self) -> list[dict[str, Any]]:
        """Interrupteurs labellisés pilotés, pour l'interface des parents."""
        result = []
        for ls in self._label_switches:
            state = self._hass.states.get(ls.entity_id)
            result.append({
                "entity_id": ls.entity_id,
                "name": self._switch_name(ls.entity_id),
                "service": ls.service,
                "service_name": self.service_name(ls.service),
                "targets": [{"kind": kind, "id": ident} for kind, ident in ls.targets],
                "blocked": self._label_blocked.get(ls.entity_id),
                "state": None if state is None else state.state,
            })
        return result

    @property
    def label_issues(self) -> list[dict[str, str]]:
        """Interrupteurs labellisés ignorés, avec la raison."""
        return [
            {
                "entity_id": i.entity_id,
                "service": i.service,
                "service_name": self.service_name(i.service),
                "problem": i.problem,
            }
            for i in self._label_issues
        ]

    def service_name(self, service_id: str) -> str:
        """Nom d'un service du parent, à défaut son identifiant."""
        service = self._config.service(service_id) if self._config is not None else None
        return service.name if service is not None else service_id

    def _switch_name(self, entity_id: str) -> str:
        state = self._hass.states.get(entity_id)
        if state is not None and state.name:
            return state.name
        entry = er.async_get(self._hass).async_get(entity_id)
        return (entry.name or entry.original_name if entry is not None else None) or entity_id

    # ------------------------------------------------------------------ cycle de vie

    async def async_start(self) -> None:
        """Charge, construit les adaptateurs, démarre les écoutes et resynchronise."""
        # Config invalide : `load` journalise et renvoie None, les décisions sont gardées.
        self._config, self._decisions = await self._store.load()
        _localize(self._decisions)
        if self._config is None:
            _LOGGER.info("No valid configuration: the engine stays inactive")
        else:
            self._prune_unknown(self._config)
        self._decisions.purge(dt_util.now())
        self._build()
        try:
            await self._start_listening()
        except BaseException:
            # Écoutes déjà enregistrées : on les annule pour ne rien laisser orphelin.
            await self.async_stop()
            raise

    async def _start_listening(self) -> None:
        self._unsubs = [
            async_track_time_interval(
                self._hass, self._on_tick, timedelta(seconds=TICK_SECONDS)
            ),
            async_track_time_change(
                self._hass, self._on_calendar_time, hour=0, minute=0, second=5
            ),
            async_track_time_interval(self._hass, self._on_calendar_time, CALENDAR_REFRESH),
            self._hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED,
                self._on_registry_change,
                event_filter=self._entity_registry_filter,
            ),
            self._hass.bus.async_listen(
                lr.EVENT_LABEL_REGISTRY_UPDATED, self._on_registry_change
            ),
        ]
        if self._hass.state is not CoreState.running:
            # Au démarrage de HA, les calendriers ne sont pas toujours encore chargés.
            self._unsubs.append(async_at_started(self._hass, self._on_started))
        await self._refresh_calendars()
        # Le verrou est libre : l'évaluation de démarrage passe avant toute tâche en attente.
        self._ready = True
        await self.async_evaluate("start")

    async def async_stop(self) -> None:
        """Annule toutes les écoutes et écrit l'état sans délai."""
        self._stopped = True
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        self._cancel_state_listener()
        self._cancel_label_listener()
        async with self._lock:
            await self._store.flush_state(self._decisions)

    def _prune_unknown(self, cfg: Config) -> None:
        """Retire les décisions visant un enfant ou une ressource absents de `cfg`."""
        removed = self._decisions.prune_unknown(
            {k.id for k in cfg.kids}, {r.id for r in cfg.resources}
        )
        if removed:
            _LOGGER.info(
                "%d decision(s) removed: child or resource missing from the config", removed
            )

    def _cancel_state_listener(self) -> None:
        if self._state_unsub is not None:
            self._state_unsub()
            self._state_unsub = None

    def _cancel_label_listener(self) -> None:
        if self._label_state_unsub is not None:
            self._label_state_unsub()
            self._label_state_unsub = None

    def _build(self) -> None:
        """(Re)construit les adaptateurs et l'écoute des entités pilotées."""
        self._cancel_state_listener()
        self._adapters = {}
        self._applied = {}
        self._sent_at = {}
        self._entity_owners = {}
        self._label_applied = {}
        cfg = self._config
        self._discover_labels()
        if cfg is None:
            return
        for resource in cfg.resources:
            try:
                self._adapters[resource.id] = SimulatedAdapter(
                    build_adapter(
                        self._hass,
                        resource,
                        cfg.managed_services_for_resource(resource.id),
                        cfg.adguard_ids,
                    ),
                    lambda: self._decisions.simulation,
                    self._record_simulation,
                )
            except (KeyError, NotImplementedError) as err:
                _LOGGER.error("%s: cannot create adapter: %s", resource.name, err)
        for resource_id, adapter in self._adapters.items():
            for entity_id in adapter.entity_ids():
                self._entity_owners.setdefault(entity_id, set()).add(resource_id)
        entity_ids = sorted(self._entity_owners)
        if entity_ids:
            self._state_unsub = async_track_state_change_event(
                self._hass, entity_ids, self._on_state_change
            )

    def _discover_labels(self) -> None:
        """Redécouvre les interrupteurs labellisés et leur écoute (adaptateurs intacts)."""
        self._cancel_label_listener()
        previous = {ls.entity_id for ls in self._label_switches}
        cfg = self._config
        if cfg is None:
            self._label_switches, self._label_issues = [], []
        else:
            self._label_switches, self._label_issues = discover(self._hass, cfg)
        entity_ids = {ls.entity_id for ls in self._label_switches}
        self._label_applied = {k: v for k, v in self._label_applied.items() if k in entity_ids}
        self._label_blocked = {k: v for k, v in self._label_blocked.items() if k in entity_ids}
        self._label_unavailable &= entity_ids
        for gone in previous - entity_ids:
            self._sent_at.pop(gone, None)
        # Une seule journalisation par problème, tant qu'il persiste.
        current = {(i.entity_id, i.service, i.problem) for i in self._label_issues}
        self._label_reported &= current
        for issue in self._label_issues:
            key = (issue.entity_id, issue.service, issue.problem)
            if key in self._label_reported:
                continue
            self._label_reported.add(key)
            _LOGGER.warning(
                "%s ignored (%s)",
                ": ".join(filter(None, (issue.entity_id, self.service_name(issue.service)))),
                self._issue_text(issue.problem),
            )
        if entity_ids:
            self._label_state_unsub = async_track_state_change_event(
                self._hass, sorted(entity_ids), self._on_state_change
            )

    @staticmethod
    def _issue_text(problem: str) -> str:
        if problem == "no_target":
            return "no target: add the label of a child or a device"
        return "service label not found in the label registry"

    @callback
    def _entity_registry_filter(self, data: er.EventEntityRegistryUpdatedData) -> bool:
        """Seuls les interrupteurs (ou une entité déjà pilotée) concernent la découverte."""
        piloted = {ls.entity_id for ls in self._label_switches}
        return any(
            e is not None and (e.startswith("switch.") or e in piloted)
            for e in (data["entity_id"], data.get("old_entity_id"))
        )

    @callback
    def _on_registry_change(self, _event: Event[Any]) -> None:
        if self._config is None or not any(s.has_labels for s in self._config.services):
            return  # sans label de service, rien n'a changé pour le moteur
        self._schedule(self._rediscover_and_evaluate())

    async def _rediscover_and_evaluate(self) -> None:
        if self._stopped:
            return
        async with self._lock:
            self._discover_labels()
        await self.async_evaluate("labels")

    @property
    def language(self) -> str:
        """`en` ou `fr` : langue système de HA, celle des textes produits par le serveur."""
        return server_language(self._hass)

    def _text(self, key: str, **params: object) -> str:
        """Texte du serveur dans la langue système de HA."""
        return text(self._hass, key, **params)

    def _record_simulation(self, name: str, line: str) -> None:
        """Journal de bord et journal HA : ce que le moteur aurait fait."""
        _LOGGER.info("Simulation: %s", line)
        async_log_entry(self._hass, name, self._text("simulation.line", line=line), domain=DOMAIN)

    def _schedule(self, coro: Coroutine[Any, Any, None]) -> None:
        self._entry.async_create_task(self._hass, coro, f"{DOMAIN} engine")

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self._expire_requests(dt_util.now())
        self._schedule(self.async_evaluate("tick"))

    @callback
    def _on_calendar_time(self, _now: datetime) -> None:
        self._schedule(self._refresh_and_evaluate())

    @callback
    def _on_started(self, _hass: HomeAssistant) -> None:
        self._schedule(self._refresh_and_evaluate())

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        if event.data["old_state"] is None:
            # Entité apparue après l'application : l'état appliqué n'a pas pu l'atteindre.
            for resource_id in self._entity_owners.get(event.data["entity_id"], ()):
                self._applied.pop(resource_id, None)
            self._label_applied.pop(event.data["entity_id"], None)
        self._schedule(self.async_evaluate("state"))

    # ------------------------------------------------------------------ calendrier

    async def _refresh_calendars(self) -> None:
        cfg = self._config
        if cfg is None:
            return
        today = dt_util.now().date()
        events: dict[str, tuple[date, list[AllDayEvent]]] = {}
        for kid in cfg.kids:
            if kid.calendar is None:
                continue
            fetched = await fetch_all_day_events(self._hass, kid.calendar, today)
            if fetched is None:
                # Échec passager : on garde la lecture du jour, sinon aucun événement.
                previous = self._events.get(kid.id)
                fetched = previous[1] if previous is not None and previous[0] == today else []
            events[kid.id] = (today, fetched)
        self._events = events

    async def _refresh_and_evaluate(self) -> None:
        if self._stopped:
            return
        await self._refresh_calendars()
        await self.async_evaluate("calendar")

    def _day_types(self, now: datetime, cfg: Config) -> dict[str, DayType]:
        return {
            kid_id: day_type(now.date(), events, cfg.calendar_map)
            for kid_id, (_, events) in self._events.items()
        }

    # ------------------------------------------------------------------ évaluation

    async def async_evaluate(self, reason: str) -> None:
        async with self._lock:
            cfg = self._config
            if self._stopped or not self._ready or cfg is None:
                return
            _LOGGER.debug("Evaluation (%s)", reason)
            dec = self._decisions
            now = dt_util.now()
            in_use = self._accumulate_usage(now)
            dec.purge(now)
            day_types = self._day_types(now, cfg)
            snap = evaluate(now, cfg, dec, day_types)
            if snap.expired_exception_ids:
                dec.exceptions = [
                    e for e in dec.exceptions if e.id not in snap.expired_exception_ids
                ]
            self._snapshot = snap = self._with_nintendo_sensors(snap)
            await self._apply(snap, now)
            self._closures = upcoming_closures(now, cfg, dec, day_types, in_use)
            await self._warn(now, cfg, snap)
            await self._store.save_state(dec)
        async_dispatcher_send(self._hass, SIGNAL_UPDATE)

    def _accumulate_usage(self, now: datetime) -> dict[str, bool]:
        in_use: dict[str, bool] = {}
        for resource_id, adapter in self._adapters.items():
            try:
                in_use[resource_id] = adapter.in_use()
            except Exception as err:  # noqa: BLE001 - un adaptateur n'arrête pas les autres
                _LOGGER.warning("%s: usage unreadable: %s", adapter.resource.name, err)
                in_use[resource_id] = False
        last, self._last_eval = self._last_eval, now
        if last is None:
            return in_use
        elapsed = min(max(now - last, timedelta(0)), MAX_ELAPSED).total_seconds() / 60
        if elapsed > 0:
            for resource_id, using in in_use.items():
                if using:
                    self._decisions.add_usage(resource_id, now.date(), elapsed)
        return in_use

    def _with_nintendo_sensors(self, snap: Snapshot) -> Snapshot:
        resources = dict(snap.resources)
        for resource_id, wrapper in self._adapters.items():
            # L'enveloppe cache le composite réel : on lit toujours l'appareil.
            nintendo = wrapper.inner.nintendo
            if nintendo is not None and resource_id in resources:
                resources[resource_id] = replace(
                    resources[resource_id],
                    used_minutes=nintendo.used_minutes(),
                    remaining_minutes=nintendo.remaining_minutes(),
                )
        return replace(snap, resources=resources)

    async def _apply(self, snap: Snapshot, now: datetime) -> None:
        """Applique si l'état voulu change (immédiat) ou en cas de dérive (au plus une
        commande par `DRIFT_COOLDOWN`, le temps que l'appareil rapporte son état)."""
        for resource_id, adapter in self._adapters.items():
            desired = snap.resources.get(resource_id)
            if desired is None:
                continue
            key = (desired.open, desired.blocked_services, desired.opened_services)
            try:
                drifted = adapter.drifted(desired)
                if self._skip_send(resource_id, self._applied.get(resource_id) == key,
                                   drifted, now):
                    continue
                if drifted:  # l'adaptateur va envoyer une correction
                    self._sent_at[resource_id] = now
                await adapter.apply(desired)
            except Exception as err:  # noqa: BLE001 - un adaptateur n'arrête pas les autres
                _LOGGER.error("%s: apply failed: %s", adapter.resource.name, err)
                continue
            self._applied[resource_id] = key
        if self._config is not None:
            await self._apply_label_switches(self._config, snap, now)

    def _skip_send(self, ident: str, unchanged: bool, drifted: bool, now: datetime) -> bool:
        """Vrai si rien n'est à envoyer : état voulu inchangé et sans dérive, ou dérive déjà
        corrigée il y a moins de `DRIFT_COOLDOWN`."""
        if not unchanged:
            return False
        sent = self._sent_at.get(ident)
        return not drifted or (sent is not None and now - sent < DRIFT_COOLDOWN)

    async def _apply_label_switches(self, cfg: Config, snap: Snapshot, now: datetime) -> None:
        """Allume ou éteint chaque interrupteur labellisé selon l'état voulu du service."""
        for ls in self._label_switches:
            blocked = switch_blocked(now, cfg, self._decisions, snap, ls.service, ls.targets)
            self._label_blocked[ls.entity_id] = blocked
            if blocked is None:
                continue
            state = self._hass.states.get(ls.entity_id)
            if state is None or state.state not in (STATE_ON, STATE_OFF):
                self._warn_label_unavailable(ls.entity_id)
                continue
            self._label_unavailable.discard(ls.entity_id)
            want_on = blocked != ls.on_means_allowed
            drifted = (state.state == STATE_ON) != want_on
            unchanged = self._label_applied.get(ls.entity_id) == want_on
            if self._skip_send(ls.entity_id, unchanged, drifted, now):
                continue
            if self._decisions.simulation:
                # Rien n'est envoyé : la ligne n'est écrite qu'au changement d'état voulu.
                if not unchanged:
                    self._label_applied[ls.entity_id] = want_on
                if not unchanged and drifted:  # déjà dans l'état voulu : rien à dire
                    name = self._switch_name(ls.entity_id)
                    self._record_simulation(
                        name,
                        self._text(
                            "simulation.switch",
                            name=name,
                            action=self._text(
                                "simulation.turn_on" if want_on else "simulation.turn_off"
                            ),
                            effect=self._text(
                                "simulation.block" if blocked else "simulation.allow"
                            ),
                            service=self.service_name(ls.service),
                        ),
                    )
                continue
            if drifted:
                self._sent_at[ls.entity_id] = now
                try:
                    await self._hass.services.async_call(
                        "switch", "turn_on" if want_on else "turn_off",
                        {"entity_id": ls.entity_id}, blocking=True,
                    )
                except Exception as err:  # noqa: BLE001 - un interrupteur n'arrête pas les autres
                    _LOGGER.error("%s: apply failed: %s", ls.entity_id, err)
                    continue
            self._label_applied[ls.entity_id] = want_on

    def _warn_label_unavailable(self, entity_id: str) -> None:
        """Une seule alerte par interrupteur absent ou indisponible, une fois HA démarré."""
        if self._hass.state is not CoreState.running or entity_id in self._label_unavailable:
            return
        self._label_unavailable.add(entity_id)
        _LOGGER.warning("%s unavailable: labelled switch not controlled", entity_id)

    # ------------------------------------------------------------------ avertissements

    def _threshold(self, kind: str, ident: str, cfg: Config, snap: Snapshot,
                   now: datetime) -> int:
        owners = [ident] if kind == "kid" else list(cfg.resource(ident).owners)
        values = [
            _segment_warn_minutes(cfg.kid(k), snap.kids[k].day_type, now)
            for k in owners
            if k in snap.kids
        ]
        return min(values, default=DEFAULT_WARN_MINUTES)

    def _already_warned(self, key: str, closes_at: datetime) -> bool:
        # Tolérance d'une minute : la fermeture par quota se recalcule à chaque passage.
        return any(
            k == key and abs(c - closes_at) < timedelta(minutes=1) for k, c in self._warned
        )

    async def _warn(self, now: datetime, cfg: Config, snap: Snapshot) -> None:
        self._warned = {w for w in self._warned if w[1] > now}
        # Au plus une notification des parents par instant de fermeture.
        to_notify: dict[datetime, list[str]] = {}
        for key, closes_at in self._closures.items():
            kind, ident = key.split(":", 1)
            service = None
            if kind == "service":
                ident, service = ident.split(":", 1)
            delta = closes_at - now
            threshold = self._threshold("kid" if kind == "kid" else "resource", ident, cfg,
                                        snap, now)
            if delta > timedelta(minutes=threshold) or self._already_warned(key, closes_at):
                continue
            self._warned.add((key, closes_at))
            minutes = max(1, math.ceil(delta.total_seconds() / 60))
            if kind == "kid":
                message = self._text("warn.kid", name=cfg.kid(ident).name, minutes=minutes)
            elif kind == "service":
                message = self._text(
                    "warn.service",
                    service=self.service_name(service),
                    resource=cfg.resource(ident).name,
                    minutes=minutes,
                )
            else:
                message = self._text(
                    "warn.resource", resource=cfg.resource(ident).name, minutes=minutes
                )
            self._hass.bus.async_fire(
                EVENT_WARNING,
                {"target": key, "closes_at": closes_at.isoformat(), "message": message},
            )
            if kind in ("kid", "service"):
                to_notify.setdefault(closes_at, []).append(message)
            elif (adapter := self._adapters.get(ident)) is not None:
                # Tâche à part : un appareil lent ne retarde pas l'évaluation.
                self._schedule(self._device_warn(adapter, message))
        for messages in to_notify.values():
            self._notify(cfg, "\n".join(messages))

    @staticmethod
    async def _device_warn(adapter: SimulatedAdapter, message: str) -> None:
        try:
            await adapter.warn(message)
        except Exception as err:  # noqa: BLE001 - un avertissement ne bloque rien
            _LOGGER.warning("%s: warning failed: %s", adapter.resource.name, err)

    def _notify(self, cfg: Config, message: str) -> None:
        """Notifie les parents sans attendre l'exécution (`blocking=False`)."""
        if self._decisions.simulation:
            message = self._text("simulation.prefix") + message
        for target in cfg.notify:
            self._schedule(self._send_notify(target, message))

    async def _send_notify(
        self,
        target: str,
        message: str,
        data: dict[str, Any] | None = None,
        *,
        title: bool = True,
    ) -> None:
        domain, _, service = target.partition(".")
        payload: dict[str, Any] = {"message": message}
        if title:
            payload["title"] = self._text("notify.title")
        if data is not None:
            payload["data"] = data
        try:
            await self._hass.services.async_call(domain, service, payload, blocking=False)
        except Exception as err:  # noqa: BLE001 - une notification ne bloque rien
            _LOGGER.warning("Notification %s failed: %s", target, err)

    # ------------------------------------------------------------------ demandes

    def request_message(self, req: TimeRequest) -> str:
        """Texte de la notification envoyée aux parents (langue système de HA)."""
        cfg = self._require_config()
        lang = server_language(self._hass)
        # L'écran « Demandes » affiche aussi les demandes d'un enfant retiré entre-temps.
        params: dict[str, object] = {"kid": self._kid_name(req.kid_id)}
        if req.resource_id is not None:
            try:
                params["resource"] = cfg.resource(req.resource_id).name
            except KeyError:
                params["resource"] = req.resource_id
        if req.proposed is not None:
            params["duration"] = duration_label(req.proposed, lang)
        if req.kind == RequestKind.HOMEWORK:
            return self._text("request.homework", kid=params["kid"])
        if req.kind == RequestKind.BONUS:
            key = "request.bonus_on" if "resource" in params else "request.bonus"
            return self._text(key, **params)
        if req.kind == RequestKind.TIMER:
            return self._text("request.timer", kid=params["kid"], duration=params["duration"])
        if req.service is not None:
            params["service"] = self.service_name(req.service)
        parts = [p for p in ("duration", "service", "resource") if p in params]
        if req.proposed is None:
            # Ni la durée ni la ressource seule : « jusqu'au prochain changement ».
            return self._text("request.open." + "_".join([*parts, "until"]), **params)
        return self._text("request.open." + "_".join(parts), **params)

    def request_choices(self, req: TimeRequest) -> list[tuple[str, str]]:
        """Boutons (choix, titre) de la demande, dans la langue système de HA."""
        return action_choices(req, server_language(self._hass))

    async def request_time(
        self,
        kind: RequestKind,
        kid_id: str,
        *,
        resource_id: str | None = None,
        service: str | None = None,
        proposed: int | None = None,
        options: Sequence[int | None] = (),
        replace: Sequence[str] = (),
    ) -> str:
        """Enregistre une demande et prévient les parents ; renvoie son identifiant."""
        cfg = self._require_config()
        if not cfg.request_notify:
            raise _invalid("requests_disabled")
        self._check_kid(cfg, kid_id)
        if resource_id is not None:
            resource = self._check_resource(cfg, resource_id)
            if kid_id not in resource.owners:
                raise _invalid("invalid_target")
        # Une demande impossible à appliquer est refusée dès l'envoi (mêmes règles
        # que les actions parentales), pas à la réponse du parent.
        if kind == RequestKind.OPEN:
            self._check_target(
                cfg,
                Target(
                    resource_id=resource_id,
                    kid_id=None if resource_id else kid_id,
                    service=service,
                ),
            )
            # Le service vient de la tablette et s'affiche chez les parents : seuls
            # les services de loisir ou sur demande de la cible sont admis.
            if service is not None:
                if resource_id is not None:
                    allowed = cfg.managed_services_for_resource(resource_id)
                else:
                    allowed = cfg.leisure_for(kid_id) | cfg.on_demand_for(kid_id)
                if service not in allowed:
                    raise _invalid("invalid_target")
        elif kind == RequestKind.BONUS:
            if resource_id is not None:
                self._bonus_by_grant(cfg, resource_id)
        elif resource_id is not None:
            raise _invalid("invalid_request")  # minuteur et devoirs visent l'enfant
        try:
            req = self._requests.create(
                kind,
                kid_id,
                resource_id=resource_id,
                service=service,
                proposed=proposed,
                options=options,
                replace=replace,
                now=dt_util.now(),
            )
        except RequestError as err:
            raise _invalid(err.key) from err
        message = self.request_message(req)
        if self._decisions.simulation:
            message = self._text("simulation.prefix") + message
        data = {
            "tag": request_tag(req.id),
            # Toucher la notification ouvre l'écran « Demandes » (iOS : `url`, Android : `clickAction`).
            "url": f"/{REQUESTS_PANEL_PATH}",
            "clickAction": f"/{REQUESTS_PANEL_PATH}",
            "actions": [
                {"action": f"PARENTAL_REQ:{req.id}:{req.token}:{choice}", "title": title}
                for choice, title in self.request_choices(req)
            ],
        }
        for target in cfg.request_notify:
            self._schedule(self._send_notify(target, message, data))
        async_dispatcher_send(self._hass, SIGNAL_UPDATE)
        return req.id

    def clear_request_notification(self, req: TimeRequest) -> None:
        """Retire la notification de la demande chez tous les parents (sans attendre)."""
        cfg = self._config
        if cfg is None:
            return
        for target in cfg.request_notify:
            self._schedule(
                self._send_notify(
                    target, "clear_notification", {"tag": request_tag(req.id)}, title=False
                )
            )

    def _kid_name(self, kid_id: str) -> str:
        """Nom de l'enfant, ou son id s'il n'est plus dans la config."""
        if self._config is not None:
            try:
                return self._config.kid(kid_id).name
            except KeyError:
                pass
        return kid_id

    async def answer_request(
        self, request_id: str, token: str, choice: str, user_id: str
    ) -> RequestStatus | None:
        """Applique la réponse d'un parent (déjà authentifié) ; `None` si elle est ignorée.

        Seule la première réponse au bon jeton, avant l'échéance, est retenue.
        """
        user = await self._hass.auth.async_get_user(user_id)
        answered_by = user.name if user is not None and user.name else user_id
        req = self._requests.claim(request_id, token, dt_util.now())
        if req is None:
            return None
        status, granted, reason = (
            RequestStatus.FAILED, None, self._text("request.reason.impossible")
        )
        try:
            status, granted, reason = await self._apply_answer(req, choice)
        finally:
            # Toujours un statut définitif : la réservation (`claim`) ne doit pas rester.
            self._requests.finish(
                req, status, dt_util.now(),
                granted=granted, reason=reason, answered_by=answered_by,
            )
            self.clear_request_notification(req)
            who = {"kid": self._kid_name(req.kid_id), "parent": answered_by}
            if status == RequestStatus.REFUSED:
                line = self._text("log.refused", **who)
            elif status == RequestStatus.FAILED:
                line = self._text("log.failed", **who, reason=reason)
            elif req.kind == RequestKind.HOMEWORK:
                line = self._text("log.accepted", **who)
            elif granted is None:
                line = self._text("log.accepted_until", **who)
            else:
                line = self._text(
                    "log.accepted_duration",
                    **who,
                    duration=duration_label(granted, server_language(self._hass)),
                )
            async_log_entry(self._hass, self._text("notify.title"), line, domain=DOMAIN)
            async_dispatcher_send(self._hass, SIGNAL_UPDATE)
        return status

    async def _apply_answer(
        self, req: TimeRequest, choice: str
    ) -> tuple[RequestStatus, int | None, str | None]:
        """Statut, durée accordée et raison d'échec de la réponse `choice`."""
        if choice == "refuse":
            return RequestStatus.REFUSED, None, None
        if req.kind == RequestKind.HOMEWORK:
            if choice != "accept":
                return RequestStatus.FAILED, None, self._text("request.reason.unknown_choice")
            minutes = None
        else:
            # Comparaison de chaînes : ni « 01 », ni chiffres d'autres écritures.
            indexes = {str(i): i for i in range(len(req.options))}
            if choice not in indexes:
                return RequestStatus.FAILED, None, self._text("request.reason.unknown_choice")
            minutes = req.options[indexes[choice]]
        kid_id = None if req.resource_id else req.kid_id
        try:
            if req.kind == RequestKind.OPEN:
                target = Target(
                    resource_id=req.resource_id, kid_id=kid_id, service=req.service
                )
                # Cible revérifiée avant toute annulation : un échec ne retire rien.
                self._check_target(self._require_config(), target)
                # `replace` vient de la tablette : seules les exceptions de la même
                # cible sont remplacées (annuler une autre fermeture demande le code).
                for exc_id in req.replace:
                    if any(
                        e.id == exc_id and e.target == target
                        for e in self._decisions.exceptions
                    ):
                        await self.cancel_exception(exc_id)
                    else:
                        _LOGGER.debug(
                            "Request %s: exception %s ignored (missing or other target)",
                            req.id, exc_id,
                        )
                await self.add_exception(target, True, minutes)
            elif req.kind == RequestKind.BONUS:
                assert minutes is not None  # garanti par `normalize_options`
                await self.add_bonus(minutes, kid_id=kid_id, resource_id=req.resource_id)
            elif req.kind == RequestKind.TIMER:
                assert minutes is not None
                await self.start_timer(req.kid_id, minutes)
            else:
                await self.homework_done(req.kid_id)
        except ServiceValidationError as err:
            return RequestStatus.FAILED, None, str(err) or err.translation_key
        except (KeyError, ValueError):
            return RequestStatus.FAILED, None, self._text("request.reason.impossible")
        return RequestStatus.ACCEPTED, minutes, None

    def _expire_requests(self, now: datetime) -> None:
        expired = self._requests.expire(now)
        for req in expired:
            self.clear_request_notification(req)
            async_log_entry(
                self._hass,
                self._text("notify.title"),
                self._text("log.expired", kid=self._kid_name(req.kid_id)),
                domain=DOMAIN,
            )
        if expired:
            async_dispatcher_send(self._hass, SIGNAL_UPDATE)

    # ------------------------------------------------------------------ validation

    def _require_config(self) -> Config:
        if self._config is None:
            raise _invalid("not_configured")
        return self._config

    @staticmethod
    def _check_kid(cfg: Config, kid_id: str) -> Kid:
        try:
            return cfg.kid(kid_id)
        except KeyError:
            raise _invalid("unknown_kid", kid_id=kid_id) from None

    @staticmethod
    def _check_resource(cfg: Config, resource_id: str) -> Resource:
        try:
            return cfg.resource(resource_id)
        except KeyError:
            raise _invalid("unknown_resource", resource_id=resource_id) from None

    def _check_target(self, cfg: Config, target: Target) -> None:
        if target.kid_id is not None:
            self._check_kid(cfg, target.kid_id)
        if target.resource_id is not None:
            resource = self._check_resource(cfg, target.resource_id)
            if resource.has(ResourceKind.NINTENDO):
                # La Switch ne se pilote que par bonus (`add_bonus`).
                raise _invalid("nintendo_use_bonus")
        if target.service is None:
            # Sans service, seule une ressource précise est une cible (spec §5).
            if target.resource_id is None:
                raise _invalid("invalid_target")
            return
        # Même portée que `rule_signature` : la ressource prime sur l'enfant.
        if target.resource_id is not None:
            scope = [cfg.resource(target.resource_id)]
        elif target.kid_id is not None:
            scope = [r for r in cfg.resources if target.kid_id in r.owners]
        else:
            scope = list(cfg.resources)
        # Un service rattaché à des labels vaut pour tout appareil ; ses services AdGuard
        # exigent un appareil AdGuard ; un service inconnu est refusé.
        valid = (cfg.has_adguard(target.service) and any(
            r.has(ResourceKind.ADGUARD) for r in scope
        )) or (cfg.has_labels(target.service) and bool(scope))
        if not valid:
            raise _invalid("invalid_target")

    def _bonus_by_grant(self, cfg: Config, resource_id: str) -> bool:
        """Un bonus sur la ressource passe par l'appareil (Nintendo : `True`) ou par le
        temps mesuré (`False`) ; sinon la ressource n'accepte pas de bonus."""
        resource = self._check_resource(cfg, resource_id)
        adapter = self._adapters.get(resource_id)
        if adapter is not None and adapter.inner.nintendo is not None:
            return True
        if resource.measured:
            return False
        raise _invalid("invalid_target")

    # ------------------------------------------------------------------ actions

    async def homework_done(self, kid_id: str) -> None:
        cfg = self._require_config()
        self._check_kid(cfg, kid_id)
        self._decisions.homework_done[kid_id] = dt_util.now().date()
        await self.async_evaluate("homework_done")

    async def add_bonus(
        self, minutes: int, *, kid_id: str | None = None, resource_id: str | None = None
    ) -> None:
        cfg = self._require_config()
        if (kid_id is None) == (resource_id is None):
            raise _invalid("invalid_target")
        today = dt_util.now().date()
        if kid_id is not None:
            self._check_kid(cfg, kid_id)
            self._decisions.bonuses.append(Bonus(today, minutes, kid_id=kid_id))
        else:
            assert resource_id is not None
            if self._bonus_by_grant(cfg, resource_id):
                # Via l'enveloppe : en simulation, rien n'est accordé.
                await self._adapters[resource_id].grant(minutes)
            else:
                self._decisions.bonuses.append(
                    Bonus(today, minutes, resource_id=resource_id)
                )
        await self.async_evaluate("bonus")

    async def add_exception(
        self, target: Target, open: bool, minutes: int | None  # noqa: A002 - nom du contrat
    ) -> str:
        """Ajoute une exception ; `minutes=None` = jusqu'à la prochaine décision."""
        cfg = self._require_config()
        self._check_target(cfg, target)
        now = dt_util.now()
        until = None
        signature = None
        if minutes is None:
            rule = evaluate(now, cfg, self._decisions, self._day_types(now, cfg),
                            apply_exceptions=False)
            signature = rule_signature(target, rule, cfg)
        else:
            until = _after(now, minutes)
        exc = ManualException(uuid4().hex, target, open, now, until, signature)
        self._decisions.exceptions.append(exc)
        await self.async_evaluate("exception")
        return exc.id

    async def cancel_exception(self, exc_id: str) -> None:
        """Retire l'exception ; sans effet si elle n'existe plus (déjà échue)."""
        self._require_config()
        self._decisions.exceptions = [
            e for e in self._decisions.exceptions if e.id != exc_id
        ]
        await self.async_evaluate("cancel_exception")

    async def start_timer(self, kid_id: str, minutes: int) -> None:
        """Démarre un minuteur, plafonné au reste du quota de l'enfant."""
        cfg = self._require_config()
        self._check_kid(cfg, kid_id)
        now = dt_util.now()
        if self._decisions.active_timer(kid_id, now) is not None:
            raise _invalid("timer_active")
        kid_state = evaluate(now, cfg, self._decisions, self._day_types(now, cfg)).kids[kid_id]
        if kid_state.segment is not SegmentType.QUOTA:
            raise _invalid("not_in_quota")
        duration: float = minutes
        if kid_state.remaining_minutes is not None:
            if kid_state.remaining_minutes <= 0:
                raise _invalid("quota_exhausted")
            duration = min(duration, kid_state.remaining_minutes)
        self._decisions.timers.append(
            Timer(kid_id, now, _after(now, duration))
        )
        await self.async_evaluate("start_timer")

    async def stop_timer(self, kid_id: str) -> None:
        cfg = self._require_config()
        self._check_kid(cfg, kid_id)
        now = dt_util.now()
        timer = self._decisions.active_timer(kid_id, now)
        if timer is None:
            return
        self._decisions.timers = [
            replace(t, end=now) if t is timer else t for t in self._decisions.timers
        ]
        await self.async_evaluate("stop_timer")

    async def set_pause(self, on: bool) -> None:
        """Pause générale ; l'activer ferme immédiatement toutes les ressources."""
        self._require_config()
        self._decisions.paused = on
        if on:
            for adapter in self._adapters.values():
                try:
                    await adapter.force_close()
                except Exception as err:  # noqa: BLE001 - un adaptateur n'arrête pas les autres
                    _LOGGER.error("%s: pause failed: %s", adapter.resource.name, err)
        await self.async_evaluate("pause")

    async def set_simulation(self, on: bool) -> None:
        """Active ou quitte la simulation ; la quitter resynchronise tous les appareils."""
        self._decisions.simulation = on
        if not on:
            # Rien n'a été envoyé pendant la simulation : tout est à rappliquer.
            self._applied.clear()
            self._label_applied.clear()
            self._sent_at.clear()
            for adapter in self._adapters.values():
                adapter.reset()
        await self.async_evaluate("simulation")

    async def set_config(self, cfg: Config) -> None:
        """Enregistre une nouvelle config et reconstruit adaptateurs et écoutes."""
        await self._store.save_config(cfg)
        persistent_notification.async_dismiss(self._hass, INVALID_CONFIG_NOTIFICATION)
        async with self._lock:
            self._config = cfg
            self._prune_unknown(cfg)
            self._build()
        await self._refresh_calendars()
        await self.async_evaluate("config")
