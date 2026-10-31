"""Données d'affichage dérivées du moteur : frise du jour et fin des exceptions (pur)."""

from __future__ import annotations

from datetime import datetime, time

from .decisions import ManualException
from .evaluator import Snapshot, timeline
from .model import Config


def kid_timeline(cfg: Config, snap: Snapshot, kid_id: str, now: datetime) -> list[dict]:
    """Frise du jour local de `now` : `[{start, end, type}]` (heures ISO), sans trou.

    Le premier segment commence à minuit même si le profil le place plus tard :
    l'évaluateur le considère déjà courant depuis 00:00.
    """
    slots = timeline(cfg.kid(kid_id), snap.kids[kid_id].day_type, now.date(), now.tzinfo)
    midnight = datetime.combine(now.date(), time(0), tzinfo=now.tzinfo)
    return [
        {
            "start": (midnight if i == 0 else s.start).isoformat(),
            "end": s.end.isoformat(),
            "type": s.type.value,
        }
        for i, s in enumerate(slots)
    ]


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
