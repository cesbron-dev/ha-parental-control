"""Base commune des entités : appareils, mises à jour et suivi de la configuration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CODE_HASH, DOMAIN, SIGNAL_UPDATE
from .core.model import Config
from .engine import ParentalEngine
from .security import check_unlock

if TYPE_CHECKING:
    from . import ParentalConfigEntry

GLOBAL_DEVICE = "global"
GLOBAL_NAME = "Contrôle parental"

type EntityFactories = dict[str, Callable[[], Entity]]


def kid_device_id(kid_id: str) -> str:
    return f"kid_{kid_id}"


def resource_device_id(resource_id: str) -> str:
    return f"resource_{resource_id}"


def _device_info(ident: str, name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, ident)}, name=name, entry_type=DeviceEntryType.SERVICE
    )


class ParentalEntity(Entity):
    """Entité rattachée à un appareil ; se met à jour à chaque `SIGNAL_UPDATE`."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ParentalConfigEntry, unique_suffix: str, key: str,
                 device: DeviceInfo) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = device

    @property
    def engine(self) -> ParentalEngine:
        return self._entry.runtime_data

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state)
        )

    async def _check_unlock(self) -> None:
        """Action qui débloque : code exigé d'un non-admin (que l'entité ne reçoit pas)."""
        context = self._context or Context()
        await check_unlock(self.hass, context, None, self._entry.data[CONF_CODE_HASH])


class KidEntity(ParentalEntity):
    def __init__(self, entry: ParentalConfigEntry, kid_id: str, name: str, key: str) -> None:
        super().__init__(entry, f"kid_{kid_id}", key, _device_info(kid_device_id(kid_id), name))
        self.kid_id = kid_id

    @property
    def available(self) -> bool:
        snap = self.engine.snapshot
        return snap is not None and self.kid_id in snap.kids


class ResourceEntity(ParentalEntity):
    def __init__(self, entry: ParentalConfigEntry, resource_id: str, name: str,
                 key: str) -> None:
        super().__init__(entry, f"resource_{resource_id}", key,
                         _device_info(resource_device_id(resource_id), name))
        self.resource_id = resource_id

    @property
    def available(self) -> bool:
        snap = self.engine.snapshot
        return snap is not None and self.resource_id in snap.resources


class GlobalEntity(ParentalEntity):
    def __init__(self, entry: ParentalConfigEntry, key: str) -> None:
        super().__init__(entry, GLOBAL_DEVICE, key, _device_info(GLOBAL_DEVICE, GLOBAL_NAME))

    @property
    def available(self) -> bool:
        return self.engine.config is not None


@callback
def async_track_entities(
    hass: HomeAssistant,
    entry: ParentalConfigEntry,
    platform: str,
    async_add_entities: AddConfigEntryEntitiesCallback,
    build: Callable[[Config], EntityFactories],
) -> None:
    """Ajoute les entités voulues par la config et retire du registre celles en trop.

    `build` donne, pour la config courante, les fabriques d'entités par `unique_id`.
    Sans config valide, rien n'est touché (on ne perd pas les entités sur une panne).
    """
    known: set[str] = set()

    @callback
    def sync() -> None:
        cfg = entry.runtime_data.config
        if cfg is None:
            return
        wanted = build(cfg)
        new = [factory() for uid, factory in wanted.items() if uid not in known]
        known.clear()
        known.update(wanted)
        registry = er.async_get(hass)
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if reg_entry.domain == platform and reg_entry.unique_id not in wanted:
                registry.async_remove(reg_entry.entity_id)
        if new:
            async_add_entities(new)

    sync()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE, sync))


@callback
def async_sync_devices(hass: HomeAssistant, entry: ParentalConfigEntry) -> None:
    """Retire les appareils des enfants/ressources disparus ; suit les renommages."""
    cfg = entry.runtime_data.config
    if cfg is None:
        return
    names = {kid_device_id(k.id): k.name for k in cfg.kids}
    names |= {resource_device_id(r.id): r.name for r in cfg.resources}
    names[GLOBAL_DEVICE] = GLOBAL_NAME
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        idents = [i for d, i in device.identifiers if d == DOMAIN]
        name = next((names[i] for i in idents if i in names), None)
        if name is None:
            registry.async_remove_device(device.id)
        elif device.name != name:
            registry.async_update_device(device.id, name=name)
