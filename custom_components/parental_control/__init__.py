"""Intégration Contrôle parental."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .engine import ParentalEngine
from .services import async_setup_services, async_unload_services
from .store import ParentalStore

type ParentalConfigEntry = ConfigEntry[ParentalEngine]


async def async_setup_entry(hass: HomeAssistant, entry: ParentalConfigEntry) -> bool:
    """Démarre le moteur (chargement, resynchronisation, écoutes)."""
    engine = ParentalEngine(hass, entry, ParentalStore(hass))
    entry.runtime_data = engine
    await engine.async_start()
    async_setup_services(hass, entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParentalConfigEntry) -> bool:
    """Arrête le moteur : écoutes annulées, état écrit sans délai."""
    async_unload_services(hass)
    await entry.runtime_data.async_stop()
    return True
