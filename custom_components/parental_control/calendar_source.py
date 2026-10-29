"""Lecture des événements « journée entière » d'un calendrier HA."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .core.daytype import AllDayEvent

_LOGGER = logging.getLogger(__name__)


def _as_date(value: Any) -> date | None:
    """Date d'un événement journée entière ; None pour un événement horaire."""
    if isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str) and "T" not in value:
        return date.fromisoformat(value)
    return None


async def fetch_all_day_events(
    hass: HomeAssistant, entity_id: str, day: date
) -> list[AllDayEvent]:
    """Événements journée entière de `entity_id` touchant le jour local `day`.

    Toute erreur (calendrier absent, réponse inattendue…) donne `[]` : le type de jour
    se replie alors sur le jour de la semaine.
    """
    tz = dt_util.get_default_time_zone()
    start = datetime.combine(day, time(0), tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz)
    try:
        response = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": entity_id,
                "start_date_time": start.isoformat(),
                "end_date_time": end.isoformat(),
            },
            blocking=True,
            return_response=True,
        )
        result = []
        for event in response[entity_id]["events"]:
            ev_start = _as_date(event["start"])
            ev_end = _as_date(event["end"])
            if ev_start is None or ev_end is None:
                continue
            result.append(AllDayEvent(str(event.get("summary", "")), ev_start, ev_end))
    except Exception as err:  # noqa: BLE001 - tout échec : repli sur le jour de semaine
        _LOGGER.warning("Lecture du calendrier %s impossible : %s", entity_id, err)
        return []
    return result
