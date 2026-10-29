"""Intégration Contrôle parental."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .engine import ParentalEngine
from .store import ParentalStore

type ParentalConfigEntry = ConfigEntry[ParentalEngine]


async def async_setup_entry(hass: HomeAssistant, entry: ParentalConfigEntry) -> bool:
    """Démarre le moteur (chargement, resynchronisation, écoutes)."""
    engine = ParentalEngine(hass, entry, ParentalStore(hass))
    entry.runtime_data = engine
    await engine.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParentalConfigEntry) -> bool:
    """Arrête le moteur : écoutes annulées, état écrit sans délai."""
    await entry.runtime_data.async_stop()
    return True
