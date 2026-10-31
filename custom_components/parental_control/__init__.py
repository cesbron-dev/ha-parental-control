"""Intégration Contrôle parental."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import SIGNAL_UPDATE
from .engine import ParentalEngine
from .frontend import async_register_frontend
from .services import async_setup_services, async_unload_services
from .store import ParentalStore
from .websocket import async_register_websocket

type ParentalConfigEntry = ConfigEntry[ParentalEngine]

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ParentalConfigEntry) -> bool:
    """Démarre le moteur (chargement, resynchronisation, écoutes) puis les entités."""
    engine = ParentalEngine(hass, entry, ParentalStore(hass))
    entry.runtime_data = engine
    await engine.async_start()
    async_setup_services(hass, entry)
    async_register_websocket(hass)
    await async_register_frontend(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Import tardif : `entity` importe ce module pour le type de l'entrée.
    from .entity import async_sync_devices

    @callback
    def sync_devices() -> None:
        async_sync_devices(hass, entry)

    sync_devices()
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATE, sync_devices))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParentalConfigEntry) -> bool:
    """Retire les entités, puis arrête le moteur : écoutes annulées, état écrit sans délai."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    async_unload_services(hass)
    await entry.runtime_data.async_stop()
    return True
