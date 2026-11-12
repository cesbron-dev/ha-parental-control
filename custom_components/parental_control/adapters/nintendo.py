"""Adaptateur Nintendo Switch : bonus de temps par tranches via l'intégration HA."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..core.evaluator import ResourceState
from ..texts import text
from .base import ha_started

_LOGGER = logging.getLogger(__name__)

MAX_SLICE_MINUTES = 30
SLICE_DELAY_SECONDS = 5
_UNUSABLE = frozenset({"unavailable", "unknown"})


class NintendoAdapter:
    """Le moteur ne coupe jamais une partie : la limite du jour reste à 0 et le temps
    s'accorde par bonus. Une limite relevée (ex. `number.set_value` depuis la tablette)
    est une dérive : elle est remise à 0, comme par la pause."""

    def __init__(self, hass: HomeAssistant, label: str, options: Mapping[str, Any]) -> None:
        self.hass = hass
        self.label = label  # nom de l'appareil physique
        self._device_id: str = options["device_id"]
        self._limit_entity: str = options["limit_entity"]
        self._remaining_entity: str = options["remaining_entity"]
        self._used_entity: str = options["used_entity"]
        self._slice_delay: float = SLICE_DELAY_SECONDS
        self._missing_logged: set[str] = set()

    def entity_ids(self) -> list[str]:
        return [self._limit_entity, self._remaining_entity, self._used_entity]

    def in_use(self) -> bool:
        return False

    def drifted(self, desired: ResourceState) -> bool:
        limit = self._minutes(self._limit_entity)
        return limit is not None and limit > 0

    async def apply(self, desired: ResourceState) -> None:
        # Seulement en cas de dérive : un bonus accordé ne touche pas la limite.
        if self.drifted(desired):
            await self._set_limit_zero()

    def describe(self, desired: ResourceState) -> list[str]:
        # même condition qu'`apply` : seule la dérive de la limite est corrigée
        if not self.drifted(desired):
            return []
        return [text(self.hass, "simulation.nintendo_reset", label=self.label)]

    def describe_grant(self, minutes: int) -> list[str]:
        return [text(self.hass, "simulation.nintendo_grant", minutes=minutes, label=self.label)]

    def describe_warn(self, message: str) -> list[str]:
        return []

    async def warn(self, message: str) -> None:
        return

    def _minutes(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            if entity_id not in self._missing_logged and ha_started(self.hass):
                self._missing_logged.add(entity_id)
                _LOGGER.warning(
                    "%s: entity not found %s", self.label, entity_id
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
                    "%s: %d min bonus failed, retrying: %s",
                    self.label,
                    amount,
                    err,
                )
                await asyncio.sleep(self._slice_delay)
                await self._add_bonus(amount)
            remaining -= amount

    def pause_state(self) -> ResourceState:
        return ResourceState(
            open=False,
            reason="pause",
            until=None,
            used_minutes=None,
            remaining_minutes=None,
            blocked_services=frozenset(),
        )

    async def force_close(self) -> None:
        await self._set_limit_zero()

    async def _set_limit_zero(self) -> None:
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": self._limit_entity, "value": 0},
            blocking=True,
        )
