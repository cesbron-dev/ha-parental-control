"""Adaptateur AdGuard : appareil client de l'intégration `adguard_clients`.

Lecture : attribut `services` du capteur « Services bloqués » de l'appareil.
Écriture : `adguard_clients.set_blocked_services` (une écriture par décision).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from ..core.evaluator import ResourceState
from ..texts import text
from .base import ha_started

_LOGGER = logging.getLogger(__name__)

ADGUARD_DOMAIN = "adguard_clients"
SET_BLOCKED_SERVICES = "set_blocked_services"
_SENSOR_SUFFIX = "_blocked_services"


class AdGuardAdapter:
    """Gère `loisirs ∪ services bloqués voulus ∪ services hors loisirs qu'il a bloqués`.

    Les services de l'état voulu sont ceux du parent ; `adguard_ids` les traduit en
    identifiants AdGuard (union, un identifiant partagé est bloqué dès qu'un service géré
    qui le contient l'est). Les autres services du client ne sont jamais touchés.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        label: str,
        options: Mapping[str, Any],
        leisure: frozenset[str],
        adguard_ids: Callable[[Iterable[str]], frozenset[str]],
    ) -> None:
        self.hass = hass
        self.label = label  # nom de l'appareil physique
        self._device_id: str = options["device_id"]
        self._adguard_ids = adguard_ids
        # Services du parent gérés (loisirs, sur demande) et leur traduction AdGuard ; un
        # service sans identifiant AdGuard (interrupteurs seuls, vide) ne donne rien.
        self._managed = leisure
        self._leisure = adguard_ids(leisure)
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
            if not self._missing_logged and ha_started(self.hass):
                self._missing_logged = True
                _LOGGER.warning(
                    "%s: AdGuard sensor not found for device %s, ignored",
                    self.label,
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
                "%s: the AdGuard client uses the global blocked services, its list "
                "is not applied; turn off \"Use global blocked services\" on the device",
                self.label,
            )
        return set(services)

    def entity_ids(self) -> list[str]:
        entity_id = self._sensor_entity()
        return [entity_id] if entity_id else []

    def in_use(self) -> bool:
        return False

    def drifted(self, desired: ResourceState) -> bool:
        current = self._blocked_now()
        return current is not None and not self._wanted(desired) <= current

    def _wanted(self, desired: ResourceState) -> frozenset[str]:
        """Identifiants AdGuard à bloquer, traduits des services du parent."""
        return self._adguard_ids(desired.blocked_services)

    def _plan(
        self, desired: ResourceState
    ) -> tuple[list[str], list[str], set[str]] | None:
        """(à bloquer, à débloquer, à oublier) sans effet de bord ; None si illisible."""
        current = self._blocked_now()
        if current is None:
            return None
        wanted = self._wanted(desired)
        released = self._leisure | self._extra_blocked
        released -= wanted
        block = sorted(wanted - current)
        unblock = sorted(released & current)
        # déjà débloqué (à la main ou ailleurs) : plus à gérer
        return block, unblock, released - current

    def describe(self, desired: ResourceState) -> list[str]:
        plan = self._plan(desired)
        if plan is None:
            return []
        block, unblock, _ = plan
        lines = []
        if block:
            lines.append(text(self.hass, "simulation.adguard_block", services=", ".join(block),
                              label=self.label))
        if unblock:
            lines.append(text(self.hass, "simulation.adguard_unblock", services=", ".join(unblock),
                              label=self.label))
        return lines

    def describe_grant(self, minutes: int) -> list[str]:
        return []

    async def apply(self, desired: ResourceState) -> None:
        plan = self._plan(desired)
        if plan is None:
            return
        block, unblock, forgotten = plan
        self._extra_blocked -= forgotten
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
                "%s: AdGuard write failed (block %s, unblock %s): %s",
                self.label,
                block,
                unblock,
                err,
            )
            return
        self._extra_blocked |= set(block) - self._leisure
        self._extra_blocked -= set(unblock)

    def describe_warn(self, message: str) -> list[str]:
        return []

    async def warn(self, message: str) -> None:
        return

    async def grant(self, minutes: int) -> None:
        raise NotImplementedError

    def pause_state(self) -> ResourceState:
        """État fermé de la pause (aussi décrit en simulation) ; services du parent, traduits par
        `apply` comme tout état voulu."""
        return ResourceState(
            open=False,
            reason="pause",
            until=None,
            used_minutes=None,
            remaining_minutes=None,
            blocked_services=self._managed,
        )

    async def force_close(self) -> None:
        await self.apply(self.pause_state())
