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
from collections.abc import Coroutine
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .adapters import Adapter, build_adapter
from .adapters.nintendo import NintendoAdapter
from .calendar_source import fetch_all_day_events
from .const import DOMAIN, EVENT_WARNING, SIGNAL_UPDATE, TICK_SECONDS
from .core.daytype import AllDayEvent, day_type
from .core.decisions import Bonus, Decisions, ManualException, Target, Timer
from .core.evaluator import Snapshot, evaluate, rule_signature, upcoming_closures
from .core.model import Config, DayType, Kid, Resource, ResourceKind, SegmentType
from .store import ParentalStore

_LOGGER = logging.getLogger(__name__)

MAX_ELAPSED = timedelta(minutes=5)
CALENDAR_REFRESH = timedelta(minutes=15)
DEFAULT_WARN_MINUTES = 5
DRIFT_COOLDOWN = timedelta(seconds=30)
NOTIFY_TITLE = "Contrôle parental"


def _invalid(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )


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
        self._adapters: dict[str, Adapter] = {}
        # Dernier état appliqué par ressource : (ouvert, services bloqués).
        self._applied: dict[str, tuple[bool, frozenset[str]]] = {}
        self._warned: set[tuple[str, datetime]] = set()
        # Événements par enfant, avec le jour local pour lequel ils ont été lus.
        self._events: dict[str, tuple[date, list[AllDayEvent]]] = {}
        # Dernier envoi de commande par ressource (anti-rafale des corrections de dérive).
        self._sent_at: dict[str, datetime] = {}
        self._last_eval: datetime | None = None
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
    def closures(self) -> dict[str, datetime]:
        return self._closures

    # ------------------------------------------------------------------ cycle de vie

    async def async_start(self) -> None:
        """Charge, construit les adaptateurs, démarre les écoutes et resynchronise."""
        # Config invalide : `load` journalise et renvoie None, les décisions sont gardées.
        self._config, self._decisions = await self._store.load()
        if self._config is None:
            _LOGGER.info("Aucune configuration valide : le moteur reste inactif")
        self._decisions.purge(dt_util.now())
        self._build()
        self._unsubs = [
            async_track_time_interval(
                self._hass, self._on_tick, timedelta(seconds=TICK_SECONDS)
            ),
            async_track_time_change(
                self._hass, self._on_calendar_time, hour=0, minute=0, second=5
            ),
            async_track_time_interval(self._hass, self._on_calendar_time, CALENDAR_REFRESH),
        ]
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
        async with self._lock:
            await self._store.flush_state(self._decisions)

    def _cancel_state_listener(self) -> None:
        if self._state_unsub is not None:
            self._state_unsub()
            self._state_unsub = None

    def _build(self) -> None:
        """(Re)construit les adaptateurs et l'écoute des entités pilotées."""
        self._cancel_state_listener()
        self._adapters = {}
        self._applied = {}
        self._sent_at = {}
        cfg = self._config
        if cfg is None:
            return
        for resource in cfg.resources:
            try:
                self._adapters[resource.id] = build_adapter(
                    self._hass, resource, cfg.leisure_for_resource(resource.id)
                )
            except (KeyError, NotImplementedError) as err:
                _LOGGER.error("%s : adaptateur impossible à créer : %s", resource.name, err)
        entity_ids = sorted({e for a in self._adapters.values() for e in a.entity_ids()})
        if entity_ids:
            self._state_unsub = async_track_state_change_event(
                self._hass, entity_ids, self._on_state_change
            )

    def _schedule(self, coro: Coroutine[Any, Any, None]) -> None:
        self._entry.async_create_task(self._hass, coro, f"{DOMAIN} engine")

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self._schedule(self.async_evaluate("tick"))

    @callback
    def _on_calendar_time(self, _now: datetime) -> None:
        self._schedule(self._refresh_and_evaluate())

    @callback
    def _on_state_change(self, _event: Event[EventStateChangedData]) -> None:
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
            _LOGGER.debug("Évaluation (%s)", reason)
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
                _LOGGER.warning("%s : usage illisible : %s", adapter.resource.name, err)
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
        for resource_id, adapter in self._adapters.items():
            if isinstance(adapter, NintendoAdapter) and resource_id in resources:
                resources[resource_id] = replace(
                    resources[resource_id],
                    used_minutes=adapter.used_minutes(),
                    remaining_minutes=adapter.remaining_minutes(),
                )
        return replace(snap, resources=resources)

    async def _apply(self, snap: Snapshot, now: datetime) -> None:
        """Applique si l'état voulu change (immédiat) ou en cas de dérive (au plus une
        commande par `DRIFT_COOLDOWN`, le temps que l'appareil rapporte son état)."""
        for resource_id, adapter in self._adapters.items():
            desired = snap.resources.get(resource_id)
            if desired is None:
                continue
            key = (desired.open, desired.blocked_services)
            try:
                drifted = adapter.drifted(desired)
                if self._applied.get(resource_id) == key:
                    sent = self._sent_at.get(resource_id)
                    if not drifted or (sent is not None and now - sent < DRIFT_COOLDOWN):
                        continue
                if drifted:  # l'adaptateur va envoyer une correction
                    self._sent_at[resource_id] = now
                await adapter.apply(desired)
            except Exception as err:  # noqa: BLE001 - un adaptateur n'arrête pas les autres
                _LOGGER.error("%s : échec de l'application : %s", adapter.resource.name, err)
                continue
            self._applied[resource_id] = key

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
        for key, closes_at in self._closures.items():
            kind, ident = key.split(":", 1)
            delta = closes_at - now
            threshold = self._threshold(kind, ident, cfg, snap, now)
            if delta > timedelta(minutes=threshold) or self._already_warned(key, closes_at):
                continue
            self._warned.add((key, closes_at))
            minutes = max(1, math.ceil(delta.total_seconds() / 60))
            if kind == "kid":
                message = f"{cfg.kid(ident).name} : fin des écrans dans {minutes} min"
            else:
                message = f"{cfg.resource(ident).name} : coupure dans {minutes} min"
            self._hass.bus.async_fire(
                EVENT_WARNING,
                {"target": key, "closes_at": closes_at.isoformat(), "message": message},
            )
            if kind == "kid":
                self._notify(cfg, message)
            elif (adapter := self._adapters.get(ident)) is not None:
                # Tâche à part : un appareil lent ne retarde pas l'évaluation.
                self._schedule(self._device_warn(adapter, message))

    @staticmethod
    async def _device_warn(adapter: Adapter, message: str) -> None:
        try:
            await adapter.warn(message)
        except Exception as err:  # noqa: BLE001 - un avertissement ne bloque rien
            _LOGGER.warning("%s : avertissement impossible : %s", adapter.resource.name, err)

    def _notify(self, cfg: Config, message: str) -> None:
        """Notifie les parents sans attendre l'exécution (`blocking=False`)."""
        for target in cfg.notify:
            self._schedule(self._send_notify(target, message))

    async def _send_notify(self, target: str, message: str) -> None:
        domain, _, service = target.partition(".")
        try:
            await self._hass.services.async_call(
                domain, service, {"title": NOTIFY_TITLE, "message": message}, blocking=False
            )
        except Exception as err:  # noqa: BLE001 - une notification ne bloque rien
            _LOGGER.warning("Notification %s impossible : %s", target, err)

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
            self._check_resource(cfg, target.resource_id)
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
        if not any(r.kind is ResourceKind.ADGUARD for r in scope):
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
            resource = self._check_resource(cfg, resource_id)
            if resource.kind is ResourceKind.NINTENDO:
                adapter = self._adapters.get(resource_id)
                if adapter is None:
                    raise _invalid("invalid_target")
                await adapter.grant(minutes)
            elif resource.kind is ResourceKind.MEDIA_PLAYER:
                self._decisions.bonuses.append(
                    Bonus(today, minutes, resource_id=resource_id)
                )
            else:
                raise _invalid("invalid_target")
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
            until = now + timedelta(minutes=minutes)
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
            Timer(kid_id, now, now + timedelta(minutes=duration))
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
                    _LOGGER.error("%s : échec de la pause : %s", adapter.resource.name, err)
        await self.async_evaluate("pause")

    async def set_config(self, cfg: Config) -> None:
        """Enregistre une nouvelle config et reconstruit adaptateurs et écoutes."""
        await self._store.save_config(cfg)
        async with self._lock:
            self._config = cfg
            self._build()
        await self._refresh_calendars()
        await self.async_evaluate("config")
