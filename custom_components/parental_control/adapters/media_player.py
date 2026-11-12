"""Adaptateur TV : `media_player` éteint quand la ressource est fermée."""

from __future__ import annotations

import logging

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError

from ..core.evaluator import ResourceState
from ..texts import text
from .base import ha_started

_LOGGER = logging.getLogger(__name__)

IN_USE_STATES = frozenset({"on", "playing", "paused", "idle", "buffering"})


class MediaPlayerAdapter:
    def __init__(self, hass: HomeAssistant, label: str, options: Mapping[str, Any]) -> None:
        self.hass = hass
        self.label = label  # « <appareil physique> (<entity_id>) »
        self._entity_id: str = options["entity_id"]
        self._notify_service: str | None = options.get("notify_service")
        self._missing_logged = False

    def entity_ids(self) -> list[str]:
        return [self._entity_id]

    def _state(self) -> State | None:
        state = self.hass.states.get(self._entity_id)
        if state is None and not self._missing_logged and ha_started(self.hass):
            self._missing_logged = True
            _LOGGER.warning("%s: entity not found", self.label)
        return state

    def in_use(self) -> bool:
        state = self._state()
        return state is not None and state.state in IN_USE_STATES

    def drifted(self, desired: ResourceState) -> bool:
        return self._must_turn_off(desired)

    def _must_turn_off(self, desired: ResourceState) -> bool:
        # Fermée mais un service y est ouvert par exception (R6) : le lecteur reste
        # allumé, AdGuard ne laisse passer que ce service.
        return not desired.open and not desired.opened_services and self.in_use()

    def describe(self, desired: ResourceState) -> list[str]:
        if not self._must_turn_off(desired):
            return []
        return [text(self.hass, "simulation.media_off", label=self.label)]

    def describe_grant(self, minutes: int) -> list[str]:
        return []

    async def apply(self, desired: ResourceState) -> None:
        if not self._must_turn_off(desired):
            return
        try:
            await self.hass.services.async_call(
                "media_player",
                "turn_off",
                {"entity_id": self._entity_id},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("%s: turn off failed: %s", self.label, err)

    def describe_warn(self, message: str) -> list[str]:
        if not self._notify_service:
            return []
        return [text(self.hass, "simulation.media_warn", message=message, label=self.label)]

    async def warn(self, message: str) -> None:
        if not self._notify_service:
            return
        domain, _, service = self._notify_service.partition(".")
        await self.hass.services.async_call(
            domain, service, {"message": message}, blocking=True
        )

    async def grant(self, minutes: int) -> None:
        raise NotImplementedError

    def pause_state(self) -> ResourceState:
        """État fermé de la pause (aussi décrit en simulation)."""
        return ResourceState(
            open=False,
            reason="pause",
            until=None,
            used_minutes=None,
            remaining_minutes=None,
            blocked_services=frozenset(),
        )

    async def force_close(self) -> None:
        await self.apply(self.pause_state())
