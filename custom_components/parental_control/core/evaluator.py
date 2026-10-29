"""Évaluateur du moteur : état des enfants et des ressources à un instant donné (pur).

Déroulé de `evaluate` :
1. état de chaque enfant d'après sa frise (`_kid_state`) ;
2. accès de chaque couple (enfant, ressource) (`_access`), puis état « règle seule »
   de chaque ressource (`_rule_resource_state`) ;
3. exceptions « jusqu'à la prochaine décision » échues : leur signature ne correspond
   plus à l'état de la règle (`rule_signature`) ;
4. application des exceptions manuelles restantes (`_apply_exceptions`) ;
la pause l'emporte sur tout (`_paused_resource_state`).

Segment QUOTA (`_quota_access`) : une ressource mesurable (TV) puise dans son propre
budget ; les autres (AdGuard, Nintendo) ne s'ouvrent que pendant un minuteur de l'enfant,
qui puise dans le budget de l'enfant.

`upcoming_closures` réévalue aux instants candidats en projetant l'usage en cours.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, tzinfo
from enum import StrEnum

from .decisions import Decisions, ManualException, Target
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


# Tolérance (minutes) : un reste inférieur est considéré comme épuisé.
_EPS = 1e-6


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


@dataclass(frozen=True)
class _Meter:
    """Comment se décompte un segment QUOTA pour une règle.

    - `resource_id` renseigné : ressource mesurable (TV), budget de la ressource ;
    - `resource_id=None` : minuteur de l'enfant, budget de l'enfant.
    `budget` = quota + bonus du jour ; None = pas de quota (illimité).
    """

    resource_id: str | None = None
    budget: float | None = None


def _kid_budget(kid: Kid, day_type: DayType, dec: Decisions, today: date) -> float | None:
    quota = kid.profile_for(day_type).quota_minutes
    if quota is None:
        return None
    return quota + dec.bonus_minutes(today, kid_id=kid.id)


def _kid_remaining(kid: Kid, budget: float | None, dec: Decisions, moment: datetime,
                   today: date) -> float | None:
    if budget is None:
        return None
    return budget - dec.kid_timer_minutes(kid.id, today, moment)


_WEEKEND_FALLBACK = (DayType.CONGE_PEDA, DayType.VACANCES)


def _resource_quota(resource: Resource, day_type: DayType) -> int | None:
    """Quota de la ressource ; congé pédagogique et vacances se replient sur la fin de
    semaine (comme `Kid.profile_for`)."""
    quota = resource.quota_minutes.get(day_type)
    if quota is None and day_type in _WEEKEND_FALLBACK:
        quota = resource.quota_minutes.get(DayType.FIN_DE_SEMAINE)
    return quota


def _resource_budget(resource: Resource, day_type: DayType, dec: Decisions,
                     today: date) -> float | None:
    quota = _resource_quota(resource, day_type)
    if quota is None:
        return None
    return quota + dec.bonus_minutes(today, resource_id=resource.id)


def _quota_access(moment: datetime, kid: Kid, dec: Decisions, meter: _Meter,
                  today: date) -> tuple[KidStatus, datetime | None]:
    """Statut dans un segment QUOTA, et borne d'ouverture propre au quota (None = aucune)."""
    if meter.resource_id is not None:
        if meter.budget is None:
            return KidStatus.AUTORISE, None
        remaining = meter.budget - dec.usage(meter.resource_id, today)
        return (KidStatus.AUTORISE if remaining > _EPS else KidStatus.QUOTA_EPUISE), None

    remaining = _kid_remaining(kid, meter.budget, dec, moment, today)
    if remaining is not None and remaining <= _EPS:
        return KidStatus.QUOTA_EPUISE, None
    timer = dec.active_timer(kid.id, moment)
    if timer is None:
        return KidStatus.ATTENTE_MINUTEUR, None
    cap = timer.end
    if remaining is not None:
        cap = min(cap, moment + timedelta(minutes=remaining))
    return KidStatus.AUTORISE, cap


def _segment_status(seg_type: SegmentType, kid: Kid, dec: Decisions, today: date) -> KidStatus:
    """Statut d'un segment autre que QUOTA (traité par `_quota_access`)."""
    if seg_type is SegmentType.LIBRE:
        return KidStatus.AUTORISE
    if seg_type is SegmentType.APRES_DEVOIRS:
        return (KidStatus.AUTORISE if dec.homework_done_on(kid.id, today)
                else KidStatus.ATTENTE_DEVOIRS)
    if seg_type is SegmentType.SUR_DEMANDE:
        return KidStatus.SUR_DEMANDE
    return KidStatus.BLOQUE


def _access(
    now: datetime,
    dec: Decisions,
    kid: Kid,
    slots: Sequence[_Slot],
    mode: ResourceMode = ResourceMode.SUIT_FRISE,
    meter: _Meter = _Meter(),
) -> _Access:
    """Règle d'accès d'un couple (enfant, ressource), sans les exceptions.

    Avec `mode=SUIT_FRISE` (défaut), c'est le statut de l'enfant lui-même.
    `until` = fin de la période d'ouverture continue (bornée à minuit) ; chaque segment
    suivant est évalué à son propre début (minuteur et quota compris).
    """
    if dec.paused:
        return _Access(KidStatus.PAUSE, "Écrans en pause", None)

    today = now.date()
    index = _current_index(slots, now)

    def access_at(moment: datetime, i: int) -> tuple[KidStatus, datetime]:
        seg_type = _effective_type(slots[i].type, mode)
        cap = None
        if seg_type is SegmentType.QUOTA:
            status, cap = _quota_access(moment, kid, dec, meter, today)
        else:
            status = _segment_status(seg_type, kid, dec, today)
        end = slots[i].end if cap is None else min(cap, slots[i].end)
        return status, end

    status, until = access_at(now, index)
    if status is KidStatus.AUTORISE:
        i = index
        while until == slots[i].end and i + 1 < len(slots):
            nxt_status, nxt_until = access_at(slots[i + 1].start, i + 1)
            if nxt_status is not KidStatus.AUTORISE:
                break
            i += 1
            until = nxt_until
        return _Access(status, f"Écrans autorisés jusqu'à {_hhmm(until, today)}", until)
    if status is KidStatus.ATTENTE_DEVOIRS:
        return _Access(status, "Devoirs à terminer", slots[index].end)
    if status is KidStatus.QUOTA_EPUISE:
        return _Access(status, "Quota épuisé", None)
    if status is KidStatus.ATTENTE_MINUTEUR:
        return _Access(status, "En attente du minuteur", None)
    if status is KidStatus.SUR_DEMANDE:
        return _Access(status, "Sur demande", None)
    return _Access(status, "Bloqué", None)


def _kid_state(now: datetime, dec: Decisions, kid: Kid, day_type: DayType,
               slots: Sequence[_Slot]) -> KidState:
    today = now.date()
    current = slots[_current_index(slots, now)]
    budget = _kid_budget(kid, day_type, dec, today)
    access = _access(now, dec, kid, slots, meter=_Meter(budget=budget))
    remaining = None
    if current.type is SegmentType.QUOTA:
        remaining = _kid_remaining(kid, budget, dec, now, today)
        if remaining is not None:
            remaining = max(remaining, 0.0)
    timer = dec.active_timer(kid.id, now)
    return KidState(
        status=access.status,
        reason=access.reason,
        day_type=day_type,
        segment=current.type,
        segment_end=current.end,
        until=access.until,
        remaining_minutes=remaining,
        timer_end=timer.end if timer is not None else None,
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


def _latest_until(accesses: Mapping[str, _Access]) -> datetime | None:
    return max((a.until for a in accesses.values() if a.open and a.until is not None),
               default=None)


def _shared_until(start: datetime, access_at: Callable[[datetime], Mapping[str, _Access]],
                  midnight: datetime) -> datetime | None:
    """Fin de la période d'ouverture continue de la ressource, relais entre propriétaires
    compris : on repart de la fin la plus tardive tant qu'un propriétaire prend le relais."""
    until = start
    while until < midnight:
        nxt = _latest_until(access_at(until))
        if nxt is None or nxt <= until:
            break
        until = nxt
    return until


def _rule_resource_state(cfg: Config, resource: Resource, now: datetime,
                         access_at: Callable[[datetime], Mapping[str, _Access]],
                         midnight: datetime) -> ResourceState:
    """Ressource ouverte ssi au moins un propriétaire y a accès (OU)."""
    today = now.date()
    accesses = access_at(now)
    open_owners = [kid_id for kid_id in resource.owners if accesses[kid_id].open]
    first = _latest_until(accesses)
    if open_owners and first is not None:
        until = _shared_until(first, access_at, midnight)
        if len(resource.owners) > 1 and len(open_owners) < len(resource.owners):
            names = ", ".join(cfg.kid(k).name for k in open_owners)
            reason = f"Ouverte pour {names}"
        else:
            reason = f"Écrans autorisés jusqu'à {_hhmm(until, today)}"
        return _resource_state(cfg, resource, open_=True, reason=reason, until=until)

    statuses = {accesses[k].status for k in resource.owners}
    if KidStatus.ATTENTE_DEVOIRS in statuses:
        reason = "Devoirs à terminer"
    elif KidStatus.QUOTA_EPUISE in statuses:
        reason = "Quota épuisé"
    elif KidStatus.ATTENTE_MINUTEUR in statuses:
        reason = "En attente du minuteur"
    elif statuses == {KidStatus.SUR_DEMANDE}:
        reason = "Sur demande"
    else:
        reason = "Bloqué"
    return _resource_state(cfg, resource, open_=False, reason=reason, until=None)


# --------------------------------------------------------------------------- exceptions


def _active_exceptions(now: datetime, dec: Decisions,
                       ignored: frozenset[str] = frozenset()) -> list[ManualException]:
    """Exceptions non échues, de la plus ancienne à la plus récente (la dernière gagne)."""
    active = [e for e in dec.exceptions
              if (e.until is None or e.until > now) and e.id not in ignored]
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
    now: datetime, cfg: Config, dec: Decisions, states: Mapping[str, ResourceState],
    ignored: frozenset[str] = frozenset(),
) -> dict[str, ResourceState]:
    """Exceptions de ressource d'abord, puis exceptions de service (AdGuard)."""
    exceptions = _active_exceptions(now, dec, ignored)
    result = dict(states)
    for e in exceptions:
        if _is_resource_exception(e) and e.target.resource_id in result:
            resource = cfg.resource(e.target.resource_id)  # type: ignore[arg-type]
            reason = "Ouverte manuellement" if e.open else "Fermée manuellement"
            state = _resource_state(cfg, resource, open_=e.open, reason=reason, until=e.until)
            result[resource.id] = replace(state,
                                          used_minutes=result[resource.id].used_minutes,
                                          remaining_minutes=result[resource.id].remaining_minutes)
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


def _signature_resources(target: Target, cfg: Config) -> list[Resource]:
    if target.resource_id is not None:
        return [cfg.resource(target.resource_id)]
    if target.kid_id is not None:
        return [r for r in cfg.resources if target.kid_id in r.owners]
    return list(cfg.resources)


def rule_signature(target: Target, snap: Snapshot, cfg: Config) -> tuple:
    """État de la règle pour chaque couple (ressource, service) couvert par la cible.

    `snap` doit être évalué sans exceptions. Ordre stable : celui de la config.
    Éléments : `(resource_id, service, ouvert)` ; `service=None` pour la ressource entière.
    """
    items = []
    for resource in _signature_resources(target, cfg):
        state = snap.resources[resource.id]
        if target.service is None:
            items.append((resource.id, None, state.open))
        elif resource.kind is ResourceKind.ADGUARD:
            items.append((resource.id, target.service,
                          target.service not in state.blocked_services))
    return tuple(items)


def _expired_exceptions(now: datetime, cfg: Config, dec: Decisions,
                        rule: Snapshot) -> frozenset[str]:
    """Exceptions « jusqu'à la prochaine décision » dont la règle a changé depuis."""
    return frozenset(
        e.id for e in _active_exceptions(now, dec)
        if e.until is None and e.signature is not None
        and e.signature != rule_signature(e.target, rule, cfg)
    )


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


def _in_quota_segment(now: datetime, kid: Kid, resource: Resource,
                      slots: Sequence[_Slot]) -> bool:
    """Le propriétaire est-il dans un segment QUOTA pour cette ressource (mode compris) ?"""
    mode = kid.resource_modes.get(resource.id, ResourceMode.SUIT_FRISE)
    seg_type = _effective_type(slots[_current_index(slots, now)].type, mode)
    return seg_type is SegmentType.QUOTA


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

    midnight = datetime.combine(today + timedelta(days=1), time(0), tzinfo=now.tzinfo)
    resources: dict[str, ResourceState] = {}
    for resource in cfg.resources:
        # Budget par propriétaire (son type de jour) ; l'usage reste un compteur commun.
        meters = {
            kid_id: (_Meter(resource.id, _resource_budget(resource, kids[kid_id].day_type,
                                                          dec, today))
                     if resource.kind is ResourceKind.MEDIA_PLAYER
                     else _Meter(budget=_kid_budget(cfg.kid(kid_id), kids[kid_id].day_type,
                                                    dec, today)))
            for kid_id in resource.owners
        }

        def access_at(moment: datetime, resource: Resource = resource,
                      meters: Mapping[str, _Meter] = meters) -> dict[str, _Access]:
            result = {}
            for kid_id in resource.owners:
                kid = cfg.kid(kid_id)
                mode = kid.resource_modes.get(resource.id, ResourceMode.SUIT_FRISE)
                result[kid_id] = _access(moment, dec, kid, timelines[kid_id], mode,
                                         meters[kid_id])
            return result

        state = _rule_resource_state(cfg, resource, now, access_at, midnight)
        if resource.kind is ResourceKind.MEDIA_PLAYER:
            used = dec.usage(resource.id, today)
            budgets = [meters[k].budget for k in resource.owners
                       if meters[k].budget is not None
                       and _in_quota_segment(now, cfg.kid(k), resource, timelines[k])]
            state = replace(state, used_minutes=used,
                            remaining_minutes=max(max(budgets) - used, 0.0) if budgets
                            else None)
        resources[resource.id] = state

    if not apply_exceptions:
        return Snapshot(kids, resources, frozenset())
    expired = _expired_exceptions(now, cfg, dec, Snapshot(kids, resources, frozenset()))
    resources = _apply_exceptions(now, cfg, dec, resources, expired)
    return Snapshot(kids, resources, expired)


# --------------------------------------------------------------------------- fermetures à venir


def _projected(dec: Decisions, now: datetime, moment: datetime,
               in_use: Mapping[str, bool]) -> Decisions:
    """Copie des décisions avec l'usage projeté à `moment` pour les ressources en usage."""
    projected = replace(dec, resource_usage=dict(dec.resource_usage))
    elapsed = (moment - now).total_seconds() / 60
    for resource_id, using in in_use.items():
        if using:
            projected.add_usage(resource_id, now.date(), elapsed)
    return projected


def _closure_candidates(now: datetime, cfg: Config, dec: Decisions,
                        day_types: Mapping[str, DayType], snap: Snapshot,
                        in_use: Mapping[str, bool], midnight: datetime) -> list[datetime]:
    today = now.date()
    candidates = {midnight}
    for kid in cfg.kids:
        for slot in _timeline(kid, _day_type_for(kid.id, today, day_types), today, now.tzinfo):
            candidates.add(slot.start)
    candidates.update(t.end for t in dec.timers)
    candidates.update(e.until for e in dec.exceptions if e.until is not None)
    candidates.update(k.until for k in snap.kids.values() if k.until is not None)
    candidates.update(r.until for r in snap.resources.values() if r.until is not None)
    for resource_id, state in snap.resources.items():
        if in_use.get(resource_id) and state.remaining_minutes is not None:
            candidates.add(now + timedelta(minutes=state.remaining_minutes))
    return sorted(c for c in candidates if now < c <= midnight)


def upcoming_closures(
    now: datetime,
    cfg: Config,
    dec: Decisions,
    day_types: Mapping[str, DayType],
    in_use: Mapping[str, bool],
) -> dict[str, datetime]:
    """Prochaine fermeture de chaque cible ouverte (`"kid:<id>"`, `"resource:<id>"`).

    Réévalue à chaque instant candidat (bornés à minuit) en projetant l'usage des
    ressources en usage ; une cible encore ouverte à minuit n'a pas de clé.
    """
    snap = evaluate(now, cfg, dec, day_types)
    pending = {f"kid:{k}" for k, s in snap.kids.items() if s.status is KidStatus.AUTORISE}
    pending |= {f"resource:{r}" for r, s in snap.resources.items() if s.open}
    midnight = datetime.combine(now.date() + timedelta(days=1), time(0), tzinfo=now.tzinfo)

    closures: dict[str, datetime] = {}
    for moment in _closure_candidates(now, cfg, dec, day_types, snap, in_use, midnight):
        if not pending:
            break
        later = evaluate(moment, cfg, _projected(dec, now, moment, in_use), day_types)
        for key in list(pending):
            kind, ident = key.split(":", 1)
            is_open = (later.kids[ident].status is KidStatus.AUTORISE if kind == "kid"
                       else later.resources[ident].open)
            if not is_open:
                closures[key] = moment
                pending.discard(key)
    return closures
