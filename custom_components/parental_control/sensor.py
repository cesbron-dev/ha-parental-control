"""Capteurs : statut de chaque enfant, temps utilisé/restant des ressources mesurables."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ParentalConfigEntry
from .core.evaluator import KidStatus
from .core.model import Config, ResourceKind
from .entity import EntityFactories, KidEntity, ResourceEntity, async_track_entities
from .serialize import serialize_exception, serialize_snapshot

# Ressources dont le temps est mesurable (les autres n'ont pas de capteur de durée).
MEASURABLE = (ResourceKind.MEDIA_PLAYER, ResourceKind.NINTENDO)
DURATION_KEYS = {"used_time": "used_minutes", "remaining_time": "remaining_minutes"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParentalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    def build(cfg: Config) -> EntityFactories:
        factories: EntityFactories = {}
        for kid in cfg.kids:
            factories[f"{entry.entry_id}_kid_{kid.id}_status"] = (
                lambda kid=kid: KidStatusSensor(entry, kid.id, kid.name)
            )
        for res in cfg.resources:
            if res.kind not in MEASURABLE:
                continue
            for key, field in DURATION_KEYS.items():
                factories[f"{entry.entry_id}_resource_{res.id}_{key}"] = (
                    lambda res=res, key=key, field=field:
                    DurationSensor(entry, res.id, res.name, key, field)
                )
        return factories

    async_track_entities(hass, entry, "sensor", async_add_entities, build)


class KidStatusSensor(KidEntity, SensorEntity):
    """« Statut » : état `KidStatus`, détails de l'instantané en attributs."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, entry: ParentalConfigEntry, kid_id: str, name: str) -> None:
        super().__init__(entry, kid_id, name, "status")
        self._attr_options = [s.value for s in KidStatus]

    @property
    def native_value(self) -> str | None:
        snap = self.engine.snapshot
        if snap is None or (kid := snap.kids.get(self.kid_id)) is None:
            return None
        return kid.status.value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        kid = serialize_snapshot(self.engine)["kids"].get(self.kid_id)
        if kid is None:
            return None
        attrs = {k: v for k, v in kid.items() if k != "status"}
        attrs["exceptions"] = [
            serialize_exception(e)
            for e in self.engine.decisions.exceptions
            if self._concerns(e.target.kid_id, e.target.resource_id)
        ]
        return attrs

    def _concerns(self, kid_id: str | None, resource_id: str | None) -> bool:
        """Exception ciblant l'enfant, une de ses ressources, ou tout le monde."""
        if kid_id is not None:
            return kid_id == self.kid_id
        if resource_id is None:
            return True
        cfg = self.engine.config
        if cfg is None:
            return False
        try:
            return self.kid_id in cfg.resource(resource_id).owners
        except KeyError:
            return False


class DurationSensor(ResourceEntity, SensorEntity):
    """« Temps utilisé » / « Temps restant » (minutes) ; inconnu si non mesuré."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 0

    def __init__(self, entry: ParentalConfigEntry, resource_id: str, name: str,
                 key: str, field: str) -> None:
        super().__init__(entry, resource_id, name, key)
        self._field = field

    @property
    def native_value(self) -> float | None:
        snap = self.engine.snapshot
        if snap is None or (res := snap.resources.get(self.resource_id)) is None:
            return None
        value = getattr(res, self._field)
        return None if value is None else round(value, 1)
