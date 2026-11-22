"""Données d'affichage dérivées du moteur : frise du jour et fin des exceptions (pur)."""

from __future__ import annotations

from datetime import date, datetime, time, tzinfo

from .decisions import Decisions, ManualException
from .evaluator import Snapshot, timeline
from .model import Config, DayType


def kid_timeline(cfg: Config, snap: Snapshot, kid_id: str, now: datetime) -> list[dict]:
    """Frise du jour local de `now` : `[{start, end, type}]` (heures ISO), sans trou."""
    return day_timeline(cfg, kid_id, snap.kids[kid_id].day_type, now.date(), now.tzinfo)


def day_timeline(cfg: Config, kid_id: str, day_type: DayType, day: date,
                 tz: tzinfo | None) -> list[dict]:
    """Frise du jour `day` pour le type `day_type` : `[{start, end, type}]`, sans trou.

    Le premier segment commence à minuit même si le profil le place plus tard :
    l'évaluateur le considère déjà courant depuis 00:00.
    """
    slots = timeline(cfg.kid(kid_id), day_type, day, tz)
    midnight = datetime.combine(day, time(0), tzinfo=tz)
    return [
        {
            "start": (midnight if i == 0 else s.start).isoformat(),
            "end": s.end.isoformat(),
            "type": s.type.value,
        }
        for i, s in enumerate(slots)
    ]


def kid_day_preview(cfg: Config, dec: Decisions, kid_id: str, day: date, day_type: DayType,
                    tz: tzinfo | None, *, event: str | None = None) -> dict:
    """Ce que le moteur prévoit pour un enfant le jour `day` (projection, sans effet).

    `event` : titre de l'événement de calendrier qui a décidé du type (None : jour de la
    semaine). Le quota est celui du profil ; le bonus, celui déjà accordé pour ce jour.
    """
    quota = cfg.kid(kid_id).profile_for(day_type).quota_minutes
    return {
        "day_type": day_type.value,
        "day_type_event": event,
        "timeline": day_timeline(cfg, kid_id, day_type, day, tz),
        "quota_minutes": quota,
        "bonus_minutes": dec.bonus_minutes(day, kid_id=kid_id),
    }


def exception_end(cfg: Config, snap: Snapshot, exc: ManualException) -> datetime | None:
    """Fin effective d'une exception : `until`, sinon la prochaine fin de segment concernée."""
    if exc.until is not None:
        return exc.until
    target = exc.target
    if target.kid_id is not None:
        kid_ids: tuple[str, ...] = (target.kid_id,)
    elif target.resource_id is not None:
        try:
            kid_ids = cfg.resource(target.resource_id).owners
        except KeyError:
            return None
    else:
        kid_ids = tuple(snap.kids)
    ends = [snap.kids[k].segment_end for k in kid_ids if k in snap.kids]
    return min(ends) if ends else None
