"""Bouton « Devoirs terminés » de chaque enfant."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ParentalConfigEntry
from .core.model import Config
from .entity import EntityFactories, KidEntity, async_track_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def build(cfg: Config) -> EntityFactories:
        return {
            f"{entry.entry_id}_kid_{kid.id}_homework_done": (
                lambda kid=kid: HomeworkDoneButton(entry, kid.id, kid.name)
            )
            for kid in cfg.kids
        }

    async_track_entities(hass, entry, "button", async_add_entities, build)


class HomeworkDoneButton(KidEntity, ButtonEntity):
    """Débloque la période après devoirs : refusé à un non-admin (code via le service)."""

    def __init__(self, entry: ParentalConfigEntry, kid_id: str, name: str) -> None:
        super().__init__(entry, kid_id, name, "homework_done")

    async def async_press(self) -> None:
        await self._check_unlock()
        await self.engine.homework_done(self.kid_id)
