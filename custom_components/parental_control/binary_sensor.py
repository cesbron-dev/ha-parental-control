"""Capteur binaire « Autorisée » de chaque ressource."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ParentalConfigEntry
from .core.model import Config, ResourceKind
from .entity import EntityFactories, ResourceEntity, async_track_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def build(cfg: Config) -> EntityFactories:
        return {
            f"{entry.entry_id}_resource_{res.id}_allowed": (
                lambda res=res: AllowedBinarySensor(
                    entry, res.id, res.name, res.kind is ResourceKind.ADGUARD
                )
            )
            for res in cfg.resources
        }

    async_track_entities(hass, entry, "binary_sensor", async_add_entities, build)


class AllowedBinarySensor(ResourceEntity, BinarySensorEntity):
    """Ouverte selon la règle ; pour AdGuard, services bloqués en attribut."""

    def __init__(self, entry: ParentalConfigEntry, resource_id: str, name: str,
                 adguard: bool) -> None:
        super().__init__(entry, resource_id, name, "allowed")
        self._adguard = adguard

    def _state(self):
        snap = self.engine.snapshot
        return None if snap is None else snap.resources.get(self.resource_id)

    @property
    def is_on(self) -> bool | None:
        state = self._state()
        return None if state is None else state.open

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        state = self._state()
        if not self._adguard or state is None:
            return None
        return {"blocked_services": sorted(state.blocked_services)}
