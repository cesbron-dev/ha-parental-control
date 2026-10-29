"""Intégration Contrôle parental (setup minimal : stockage seulement)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .store import ParentalStore

type ParentalConfigEntry = ConfigEntry[ParentalStore]


async def async_setup_entry(hass: HomeAssistant, entry: ParentalConfigEntry) -> bool:
    """Prépare le stockage ; le moteur et les plateformes viendront ensuite."""
    entry.runtime_data = ParentalStore(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParentalConfigEntry) -> bool:
    """Rien à décharger tant qu'aucune plateforme n'est installée."""
    return True
