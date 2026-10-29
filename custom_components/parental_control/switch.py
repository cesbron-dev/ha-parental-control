"""Interrupteur « Pause générale »."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ParentalConfigEntry
from .core.model import Config
from .entity import EntityFactories, GlobalEntity, async_track_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def build(_cfg: Config) -> EntityFactories:
        return {f"{entry.entry_id}_global_pause": lambda: PauseSwitch(entry)}

    async_track_entities(hass, entry, "switch", async_add_entities, build)


class PauseSwitch(GlobalEntity, SwitchEntity):
    """Mettre en pause ne demande rien ; reprendre exige le code d'un non-admin."""

    def __init__(self, entry: ParentalConfigEntry) -> None:
        super().__init__(entry, "pause")

    @property
    def is_on(self) -> bool:
        return self.engine.decisions.paused

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.engine.set_pause(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._check_unlock()
        await self.engine.set_pause(False)
