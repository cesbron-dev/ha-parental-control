"""Adaptateur TV : `media_player` éteint quand la ressource est fermée."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from ..core.evaluator import ResourceState
from ..core.model import Resource

IN_USE_STATES = frozenset({"on", "playing", "paused", "idle", "buffering"})


class MediaPlayerAdapter:
    def __init__(self, hass: HomeAssistant, resource: Resource) -> None:
        self.hass = hass
        self.resource = resource
        self._entity_id: str = resource.options["entity_id"]
        self._notify_service: str | None = resource.options.get("notify_service")

    def entity_ids(self) -> list[str]:
        return [self._entity_id]

    def in_use(self) -> bool:
        state = self.hass.states.get(self._entity_id)
        return state is not None and state.state in IN_USE_STATES

    def drifted(self, desired: ResourceState) -> bool:
        return not desired.open and self.in_use()

    async def apply(self, desired: ResourceState) -> None:
        if desired.open or not self.in_use():
            return
        await self.hass.services.async_call(
            "media_player",
            "turn_off",
            {"entity_id": self._entity_id},
            blocking=True,
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
