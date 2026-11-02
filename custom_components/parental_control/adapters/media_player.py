"""Adaptateur TV : `media_player` éteint quand la ressource est fermée."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError

from ..core.evaluator import ResourceState
from ..core.model import Resource

_LOGGER = logging.getLogger(__name__)

IN_USE_STATES = frozenset({"on", "playing", "paused", "idle", "buffering"})


class MediaPlayerAdapter:
    def __init__(self, hass: HomeAssistant, resource: Resource) -> None:
        self.hass = hass
        self.resource = resource
        self._entity_id: str = resource.options["entity_id"]
        self._notify_service: str | None = resource.options.get("notify_service")
        self._missing_logged = False

    def entity_ids(self) -> list[str]:
        return [self._entity_id]

    def _state(self) -> State | None:
        state = self.hass.states.get(self._entity_id)
        if state is None and not self._missing_logged:
            self._missing_logged = True
            _LOGGER.warning(
                "%s : entité introuvable %s", self.resource.name, self._entity_id
            )
        return state

    def in_use(self) -> bool:
        state = self._state()
        return state is not None and state.state in IN_USE_STATES

    def drifted(self, desired: ResourceState) -> bool:
        return not desired.open and self.in_use()

    def _must_turn_off(self, desired: ResourceState) -> bool:
        return not desired.open and self.in_use()

    def describe(self, desired: ResourceState) -> list[str]:
        if not self._must_turn_off(desired):
            return []
        return [f"éteindrait {self.resource.name} ({self._entity_id})"]

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
            _LOGGER.warning(
                "%s : échec de l'extinction de %s : %s",
                self.resource.name,
                self._entity_id,
                err,
            )

    async def warn(self, message: str) -> None:
        if not self._notify_service:
            return
        domain, _, service = self._notify_service.partition(".")
        await self.hass.services.async_call(
            domain, service, {"message": message}, blocking=True
        )

    async def grant(self, minutes: int) -> None:
        raise NotImplementedError

    async def force_close(self) -> None:
        await self.apply(
            ResourceState(
                open=False,
                reason="pause",
                until=None,
                used_minutes=None,
                remaining_minutes=None,
                blocked_services=frozenset(),
            )
        )
