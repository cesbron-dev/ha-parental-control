"""Adaptateur Nintendo Switch : bonus de temps par tranches via l'intégration HA."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..core.evaluator import ResourceState
from ..core.model import Resource

_LOGGER = logging.getLogger(__name__)

MAX_SLICE_MINUTES = 30
SLICE_DELAY_SECONDS = 5
_UNUSABLE = frozenset({"unavailable", "unknown"})


class NintendoAdapter:
    """Le moteur ne coupe jamais une partie : seule la pause remet la limite à 0."""

    def __init__(self, hass: HomeAssistant, resource: Resource) -> None:
        self.hass = hass
        self.resource = resource
        self._device_id: str = resource.options["device_id"]
        self._limit_entity: str = resource.options["limit_entity"]
        self._remaining_entity: str = resource.options["remaining_entity"]
        self._used_entity: str = resource.options["used_entity"]
        self._slice_delay: float = SLICE_DELAY_SECONDS
        self._missing_logged: set[str] = set()

    def entity_ids(self) -> list[str]:
        return [self._limit_entity, self._remaining_entity, self._used_entity]

    def in_use(self) -> bool:
        return False

    def drifted(self, desired: ResourceState) -> bool:
        return False

    async def apply(self, desired: ResourceState) -> None:
        return

    async def warn(self, message: str) -> None:
        return

    def _minutes(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            if entity_id not in self._missing_logged:
                self._missing_logged.add(entity_id)
                _LOGGER.warning(
                    "%s : entité introuvable %s", self.resource.name, entity_id
                )
            return None
        if state.state in _UNUSABLE:
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def used_minutes(self) -> float | None:
        return self._minutes(self._used_entity)

    def remaining_minutes(self) -> float | None:
        return self._minutes(self._remaining_entity)

    async def _add_bonus(self, minutes: int) -> None:
        await self.hass.services.async_call(
            "nintendo_parental_controls",
            "add_bonus_time",
            {"device_id": self._device_id, "bonus_time": minutes},
            blocking=True,
        )

    async def grant(self, minutes: int) -> None:
        remaining = minutes
        first = True
        while remaining > 0:
            if not first:
                await asyncio.sleep(self._slice_delay)
            first = False
            amount = min(remaining, MAX_SLICE_MINUTES)
            try:
                await self._add_bonus(amount)
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "%s : échec du bonus de %d min, nouvel essai : %s",
                    self.resource.name,
                    amount,
                    err,
                )
                await asyncio.sleep(self._slice_delay)
                await self._add_bonus(amount)
            remaining -= amount

    async def force_close(self) -> None:
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": self._limit_entity, "value": 0},
            blocking=True,
        )
