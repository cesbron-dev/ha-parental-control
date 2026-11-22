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
    return explain_day_type(day, events, calendar_map)[0]


def explain_day_type(
    day: date,
    events: Sequence[AllDayEvent],
    calendar_map: Mapping[str, DayType],
) -> tuple[DayType, str | None]:
    """Type du jour et titre de l'événement qui l'a décidé (None : jour de la semaine).

    Vacances l'emportent sur congé pédagogique, qui l'emporte sur école / fin de semaine ;
    à type égal, l'événement commencé le plus tôt (puis le titre) départage.
    """
    keys = [(_norm(k), t) for k, t in calendar_map.items()]
    matched: list[tuple[date, str, DayType, str]] = []
    for event in events:
        if not event.start <= day < event.end:
            continue
        summary = _norm(event.summary)
        for key, dtype in keys:
            if key in summary:
                matched.append((event.start, summary, dtype, event.summary))

    for wanted in ((DayType.HOLIDAYS,), (DayType.DAY_OFF,), (DayType.SCHOOL, DayType.WEEKEND)):
        hits = sorted((m for m in matched if m[2] in wanted), key=lambda m: (m[0], m[1]))
        if hits:
            return hits[0][2], hits[0][3]
    return (DayType.SCHOOL if day.weekday() < 5 else DayType.WEEKEND), None
