"""Calcul du type de jour à partir des événements « journée entière » (pur)."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .model import DayType


@dataclass(frozen=True)
class AllDayEvent:
    summary: str
    start: date
    end: date  # exclusif, comme dans Home Assistant


def _norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold()


def day_type(
    day: date,
    events: Sequence[AllDayEvent],
    calendar_map: Mapping[str, DayType],
) -> DayType:
    keys = [(_norm(k), t) for k, t in calendar_map.items()]
    matched: list[tuple[date, str, DayType]] = []
    for event in events:
        if not event.start <= day < event.end:
            continue
        summary = _norm(event.summary)
        for key, dtype in keys:
            if key in summary:
                matched.append((event.start, summary, dtype))

    types = {t for _, _, t in matched}
    if DayType.VACANCES in types:
        return DayType.VACANCES
    if DayType.CONGE_PEDA in types:
        return DayType.CONGE_PEDA
    low = sorted((m for m in matched if m[2] in (DayType.ECOLE, DayType.FIN_DE_SEMAINE)),
                 key=lambda m: (m[0], m[1]))
    if low:
        return low[0][2]
    return DayType.ECOLE if day.weekday() < 5 else DayType.FIN_DE_SEMAINE
