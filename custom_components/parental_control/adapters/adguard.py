"""Adaptateur AdGuard : appareil client de l'intégration `adguard_clients`.

Lecture : attribut `services` du capteur « Services bloqués » de l'appareil.
Écriture : `adguard_clients.set_blocked_services` (une écriture par décision).
"""

from __future__ import annotations

import logging

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from ..core.evaluator import ResourceState
from ..core.model import Resource

_LOGGER = logging.getLogger(__name__)

ADGUARD_DOMAIN = "adguard_clients"
SET_BLOCKED_SERVICES = "set_blocked_services"
_SENSOR_SUFFIX = "_blocked_services"


class AdGuardAdapter:
    """Gère `loisirs ∪ services bloqués voulus ∪ services hors loisirs qu'il a bloqués`.

    Les autres services du client ne sont jamais touchés.
    """

    def __init__(
        self, hass: HomeAssistant, resource: Resource, leisure: frozenset[str]
    ) -> None:
        self.hass = hass
        self.resource = resource
        self._device_id: str = resource.options["device_id"]
        self._leisure = leisure
        self._sensor: str | None = None
        self._missing_logged = False
        self._global_logged = False
        # Services hors loisirs que l'adaptateur a lui-même bloqués (exception de
        # service) : ils restent gérés pour être débloqués quand l'exception échoit.
        # En mémoire seulement : après un redémarrage, un tel service reste bloqué
        # (échec du côté fermé) jusqu'à une action manuelle.
        self._extra_blocked: set[str] = set()

    def _sensor_entity(self) -> str | None:
        """Capteur « Services bloqués » de l'appareil client (registre des entités)."""
        if self._sensor is None:
            registry = er.async_get(self.hass)
            for ent in er.async_entries_for_device(registry, self._device_id):
                if (
                    ent.platform == ADGUARD_DOMAIN
                    and ent.domain == "sensor"
                    and ent.unique_id.endswith(_SENSOR_SUFFIX)
                ):
                    self._sensor = ent.entity_id
                    break
        return self._sensor

    def _blocked_now(self) -> set[str] | None:
        """Services bloqués du client, ou None s'ils sont illisibles."""
        entity_id = self._sensor_entity()
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None:
            if not self._missing_logged:
                self._missing_logged = True
                _LOGGER.warning(
                    "%s : capteur AdGuard introuvable pour l'appareil %s, ignoré",
                    self.resource.name,
                    self._device_id,
                )
            return None
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        services = state.attributes.get("services")
        if not isinstance(services, list):
            return None
        if state.attributes.get("use_global_blocked_services") and not self._global_logged:
            self._global_logged = True
            _LOGGER.warning(
                "%s : le client AdGuard utilise les services bloqués globaux, sa liste "
                "n'est pas appliquée ; désactivez « Utiliser les services bloqués "
                "globaux » sur l'appareil",
                self.resource.name,
            )
        return set(services)

    def entity_ids(self) -> list[str]:
        entity_id = self._sensor_entity()
        return [entity_id] if entity_id else []

    def in_use(self) -> bool:
        return False

    def drifted(self, desired: ResourceState) -> bool:
        current = self._blocked_now()
        return current is not None and not desired.blocked_services <= current

    async def apply(self, desired: ResourceState) -> None:
        current = self._blocked_now()
        if current is None:
            return
        released = self._leisure | self._extra_blocked
        released -= desired.blocked_services
        block = sorted(desired.blocked_services - current)
        unblock = sorted(released & current)
        # déjà débloqué (à la main ou ailleurs) : plus à gérer
        self._extra_blocked -= released - current
        if not block and not unblock:
            return
        try:
            await self.hass.services.async_call(
                ADGUARD_DOMAIN,
                SET_BLOCKED_SERVICES,
                {"device_id": self._device_id, "block": block, "unblock": unblock},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning(
                "%s : échec de l'écriture AdGuard (bloquer %s, débloquer %s) : %s",
                self.resource.name,
                block,
                unblock,
                err,
            )
            return
        self._extra_blocked |= set(block) - self._leisure
        self._extra_blocked -= set(unblock)

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
