"""Adaptateur AdGuard : switches de services bloqués du bridge (ON = bloqué)."""

from __future__ import annotations

import logging

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from ..core.evaluator import ResourceState
from ..core.model import Resource

_LOGGER = logging.getLogger(__name__)


class AdGuardAdapter:
    """Gère exactement `loisirs ∪ services bloqués voulus` ; le reste n'est jamais touché."""

    def __init__(
        self, hass: HomeAssistant, resource: Resource, leisure: frozenset[str]
    ) -> None:
        self.hass = hass
        self.resource = resource
        self._client: str = resource.options["client"]
        self._leisure = leisure
        self._missing_logged: set[str] = set()

    def _entity_id(self, service: str) -> str:
        return f"switch.adguard_{self._client}_svc_{service}"

    def entity_ids(self) -> list[str]:
        return [self._entity_id(s) for s in sorted(self._leisure)]

    def in_use(self) -> bool:
        return False

    def drifted(self, desired: ResourceState) -> bool:
        for service in desired.blocked_services:
            state = self.hass.states.get(self._entity_id(service))
            if state is not None and state.state == STATE_OFF:
                return True
        return False

    async def apply(self, desired: ResourceState) -> None:
        for service in sorted(self._leisure | desired.blocked_services):
            entity_id = self._entity_id(service)
            state = self.hass.states.get(entity_id)
            if state is None:
                if entity_id not in self._missing_logged:
                    self._missing_logged.add(entity_id)
                    _LOGGER.warning(
                        "%s : entité AdGuard introuvable %s, service ignoré",
                        self.resource.name,
                        entity_id,
                    )
                continue
            block = service in desired.blocked_services
            if block and state.state == STATE_OFF:
                action = "turn_on"
            elif not block and state.state == STATE_ON:
                action = "turn_off"
            else:
                continue
            await self.hass.services.async_call(
                "switch", action, {"entity_id": entity_id}, blocking=True
            )

    async def warn(self, message: str) -> None:
        return

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
                blocked_services=self._leisure,
            )
        )
