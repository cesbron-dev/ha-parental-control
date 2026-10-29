"""Évaluateur du moteur : état des enfants et des ressources à un instant donné (pur).

Déroulé de `evaluate` :
1. état de chaque enfant d'après sa frise (`_kid_state`) ;
2. accès de chaque couple (enfant, ressource) (`_access`), puis état « règle seule »
   de chaque ressource (`_rule_resource_state`) ;
3. application des exceptions manuelles (`_apply_exceptions`) ;
la pause l'emporte sur tout (`_paused_resource_state`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from enum import StrEnum

from .decisions import Decisions, ManualException
from .model import (
    Config,
    DayType,
    Kid,
    Resource,
    ResourceKind,
    ResourceMode,
    SegmentType,
)


class KidStatus(StrEnum):
    AUTORISE = "autorise"
    BLOQUE = "bloque"
    ATTENTE_DEVOIRS = "attente_devoirs"
    ATTENTE_MINUTEUR = "attente_minuteur"
    QUOTA_EPUISE = "quota_epuise"
    SUR_DEMANDE = "sur_demande"
    PAUSE = "pause"


@dataclass(frozen=True)
class KidState:
    status: KidStatus
    reason: str
    day_type: DayType
    segment: SegmentType
    segment_end: datetime
    until: datetime | None
    remaining_minutes: float | None
    timer_end: datetime | None


@dataclass(frozen=True)
class ResourceState:
    open: bool
    reason: str
    until: datetime | None
    used_minutes: float | None
    remaining_minutes: float | None
    blocked_services: frozenset[str]


@dataclass(frozen=True)
class Snapshot:
    kids: dict[str, KidState]
    resources: dict[str, ResourceState]
    expired_exception_ids: frozenset[str]


# --------------------------------------------------------------------------- frise


@dataclass(frozen=True)
class _Slot:
    """Segment de la frise placé sur la journée (heure murale du fuseau de `now`)."""

    start: datetime
    end: datetime
    type: SegmentType


@dataclass(frozen=True)
class _Access:
    """Résultat de la règle pour un enfant (et éventuellement une ressource)."""

    status: KidStatus
    reason: str
    until: datetime | None

    @property
    def open(self) -> bool:
        return self.status is KidStatus.AUTORISE


def _default_day_type(day: date) -> DayType:
    return DayType.ECOLE if day.weekday() < 5 else DayType.FIN_DE_SEMAINE


def _day_type_for(kid_id: str, day: date, day_types: Mapping[str, DayType]) -> DayType:
    return day_types.get(kid_id) or _default_day_type(day)


def _timeline(kid: Kid, day_type: DayType, day: date, tz: tzinfo | None) -> list[_Slot]:
    segments = kid.profile_for(day_type).segments
    midnight = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)
    slots = []
    for i, seg in enumerate(segments):
        start = datetime.combine(day, seg.start, tzinfo=tz)
        end = (datetime.combine(day, segments[i + 1].start, tzinfo=tz)
               if i + 1 < len(segments) else midnight)
        slots.append(_Slot(start, end, seg.type))
    return slots


def _current_index(slots: Sequence[_Slot], now: datetime) -> int:
    wall = now.time().replace(tzinfo=None)
    index = 0
    for i, slot in enumerate(slots):
        if slot.start.time() <= wall:
            index = i
    return index


def _hhmm(moment: datetime, day: date) -> str:
    if moment.date() > day and moment.time() == time(0):
        return "minuit"
    return f"{moment:%H:%M}"


# --------------------------------------------------------------------------- accès


def _effective_type(seg_type: SegmentType, mode: ResourceMode) -> SegmentType:
    """Un mode de ressource autre que `suit_frise` remplace le type du segment."""
    if mode is ResourceMode.SUIT_FRISE:
        return seg_type
    return SegmentType(mode.value)


def _quota_status(kid: Kid, dec: Decisions, today: date) -> KidStatus:
    """Segment QUOTA : fermé dans cette tâche, les quotas arrivent avec la tâche 5."""
    return KidStatus.BLOQUE


def _segment_status(seg_type: SegmentType, kid: Kid, dec: Decisions, today: date) -> KidStatus:
    if seg_type is SegmentType.LIBRE:
        return KidStatus.AUTORISE
    if seg_type is SegmentType.APRES_DEVOIRS:
        return (KidStatus.AUTORISE if dec.homework_done_on(kid.id, today)
                else KidStatus.ATTENTE_DEVOIRS)
    if seg_type is SegmentType.SUR_DEMANDE:
        return KidStatus.SUR_DEMANDE
    if seg_type is SegmentType.QUOTA:
        return _quota_status(kid, dec, today)
    return KidStatus.BLOQUE


def _access(
    now: datetime,
    dec: Decisions,
    kid: Kid,
    slots: Sequence[_Slot],
    mode: ResourceMode = ResourceMode.SUIT_FRISE,
) -> _Access:
    """Règle d'accès d'un couple (enfant, ressource), sans les exceptions.

    Avec `mode=SUIT_FRISE` (défaut), c'est le statut de l'enfant lui-même.
    """
    if dec.paused:
        return _Access(KidStatus.PAUSE, "Écrans en pause", None)

    today = now.date()
    index = _current_index(slots, now)

    def status_at(i: int) -> KidStatus:
        return _segment_status(_effective_type(slots[i].type, mode), kid, dec, today)

    status = status_at(index)
    if status is KidStatus.AUTORISE:
        last = index
        while last + 1 < len(slots) and status_at(last + 1) is KidStatus.AUTORISE:
            last += 1
        until = slots[last].end
        return _Access(status, f"Écrans autorisés jusqu'à {_hhmm(until, today)}", until)
    if status is KidStatus.ATTENTE_DEVOIRS:
        return _Access(status, "Devoirs à terminer", slots[index].end)
    if status is KidStatus.SUR_DEMANDE:
        return _Access(status, "Sur demande", None)
    return _Access(status, "Bloqué", None)


def _kid_state(now: datetime, dec: Decisions, kid: Kid, day_type: DayType,
               slots: Sequence[_Slot]) -> KidState:
    current = slots[_current_index(slots, now)]
    access = _access(now, dec, kid, slots)
    return KidState(
        status=access.status,
        reason=access.reason,
        day_type=day_type,
        segment=current.type,
        segment_end=current.end,
        until=access.until,
        remaining_minutes=None,
        timer_end=None,
    )


# --------------------------------------------------------------------------- ressources


def _resource_state(cfg: Config, resource: Resource, *, open_: bool, reason: str,
                    until: datetime | None) -> ResourceState:
    blocked: frozenset[str] = frozenset()
    if resource.kind is ResourceKind.ADGUARD and not open_:
        blocked = cfg.leisure_for_resource(resource.id)
    return ResourceState(
        open=open_,
        reason=reason,
        until=until if open_ else None,
        used_minutes=None,
        remaining_minutes=None,
        blocked_services=blocked,
    )


def _rule_resource_state(cfg: Config, resource: Resource,
                         accesses: Mapping[str, _Access], today: date) -> ResourceState:
    """Ressource ouverte ssi au moins un propriétaire y a accès (OU)."""
    open_owners = [kid_id for kid_id in resource.owners if accesses[kid_id].open]
    if open_owners:
        until = max(accesses[k].until for k in open_owners if accesses[k].until is not None)
        if len(resource.owners) > 1 and len(open_owners) < len(resource.owners):
            names = ", ".join(cfg.kid(k).name for k in open_owners)
            reason = f"Ouverte pour {names}"
        else:
            reason = f"Écrans autorisés jusqu'à {_hhmm(until, today)}"
        return _resource_state(cfg, resource, open_=True, reason=reason, until=until)

    statuses = {accesses[k].status for k in resource.owners}
    if KidStatus.ATTENTE_DEVOIRS in statuses:
        reason = "Devoirs à terminer"
    elif statuses == {KidStatus.SUR_DEMANDE}:
        reason = "Sur demande"
    else:
        reason = "Bloqué"
    return _resource_state(cfg, resource, open_=False, reason=reason, until=None)


# --------------------------------------------------------------------------- exceptions


def _active_exceptions(now: datetime, dec: Decisions) -> list[ManualException]:
    """Exceptions non échues, de la plus ancienne à la plus récente (la dernière gagne)."""
    active = [e for e in dec.exceptions if e.until is None or e.until > now]
    return sorted(active, key=lambda e: e.created)


def _is_resource_exception(e: ManualException) -> bool:
    return e.target.service is None and e.target.resource_id is not None


def _service_exception_applies(e: ManualException, resource: Resource) -> bool:
    target = e.target
    if target.service is None or resource.kind is not ResourceKind.ADGUARD:
        return False
    if target.resource_id is not None:
        return target.resource_id == resource.id
    if target.kid_id is not None:
        return target.kid_id in resource.owners
    return True


def _service_overrides(exceptions: Sequence[ManualException],
                       resource: Resource) -> dict[str, bool]:
    """Service -> ouvert ? pour la ressource ; l'exception la plus récente gagne."""
    overrides: dict[str, bool] = {}
    for e in exceptions:
        if _service_exception_applies(e, resource):
            overrides[e.target.service] = e.open  # type: ignore[index]
    return overrides


def _apply_exceptions(
    now: datetime, cfg: Config, dec: Decisions, states: Mapping[str, ResourceState]
) -> dict[str, ResourceState]:
    """Exceptions de ressource d'abord, puis exceptions de service (AdGuard)."""
    exceptions = _active_exceptions(now, dec)
    result = dict(states)
    for e in exceptions:
        if _is_resource_exception(e) and e.target.resource_id in result:
            resource = cfg.resource(e.target.resource_id)  # type: ignore[arg-type]
            reason = "Ouverte manuellement" if e.open else "Fermée manuellement"
            result[resource.id] = _resource_state(cfg, resource, open_=e.open,
                                                  reason=reason, until=e.until)
    for resource in cfg.resources:
        overrides = _service_overrides(exceptions, resource)
        if not overrides:
            continue
        state = result[resource.id]
        blocked = set(state.blocked_services)
        for service, open_ in overrides.items():
            if open_:
                blocked.discard(service)
            else:
                blocked.add(service)
        result[resource.id] = ResourceState(
            open=state.open,
            reason=state.reason,
            until=state.until,
            used_minutes=state.used_minutes,
            remaining_minutes=state.remaining_minutes,
            blocked_services=frozenset(blocked),
        )
    return result


def _paused_resource_state(now: datetime, cfg: Config, dec: Decisions, resource: Resource,
                           apply_exceptions: bool) -> ResourceState:
    """Pause : tout fermé ; les services fermés par exception restent bloqués en plus."""
    state = _resource_state(cfg, resource, open_=False, reason="Écrans en pause", until=None)
    if not apply_exceptions or resource.kind is not ResourceKind.ADGUARD:
        return state
    closed = {s for s, open_ in _service_overrides(
        _active_exceptions(now, dec), resource).items() if not open_}
    return ResourceState(
        open=False,
        reason=state.reason,
        until=None,
        used_minutes=None,
        remaining_minutes=None,
        blocked_services=state.blocked_services | frozenset(closed),
    )


# --------------------------------------------------------------------------- point d'entrée


def evaluate(
    now: datetime,
    cfg: Config,
    dec: Decisions,
    day_types: Mapping[str, DayType],
    *,
    apply_exceptions: bool = True,
) -> Snapshot:
    """État de tous les enfants et ressources à `now` (conscient du fuseau)."""
    today = now.date()
    timelines: dict[str, list[_Slot]] = {}
    kids: dict[str, KidState] = {}
    for kid in cfg.kids:
        dtype = _day_type_for(kid.id, today, day_types)
        timelines[kid.id] = _timeline(kid, dtype, today, now.tzinfo)
        kids[kid.id] = _kid_state(now, dec, kid, dtype, timelines[kid.id])

    if dec.paused:
        resources = {
            r.id: _paused_resource_state(now, cfg, dec, r, apply_exceptions)
            for r in cfg.resources
        }
        return Snapshot(kids, resources, frozenset())

    resources: dict[str, ResourceState] = {}
    for resource in cfg.resources:
        accesses = {}
        for kid_id in resource.owners:
            kid = cfg.kid(kid_id)
            mode = kid.resource_modes.get(resource.id, ResourceMode.SUIT_FRISE)
            accesses[kid_id] = _access(now, dec, kid, timelines[kid_id], mode)
        resources[resource.id] = _rule_resource_state(cfg, resource, accesses, today)

    if apply_exceptions:
        resources = _apply_exceptions(now, cfg, dec, resources)
    return Snapshot(kids, resources, frozenset())
