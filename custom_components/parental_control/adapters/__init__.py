"""Adaptateurs : traduction de l'état voulu en appels de services HA."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from ..core.model import Resource, ResourceKind
from .adguard import AdGuardAdapter
from .base import Adapter
from .media_player import MediaPlayerAdapter
from .nintendo import NintendoAdapter

__all__ = ["Adapter", "build_adapter"]


def build_adapter(
    hass: HomeAssistant, resource: Resource, leisure: frozenset[str]
) -> Adapter:
    """Adaptateur de la ressource ; `leisure` ne sert qu'à AdGuard."""
    if resource.kind is ResourceKind.MEDIA_PLAYER:
        return MediaPlayerAdapter(hass, resource)
    if resource.kind is ResourceKind.ADGUARD:
        return AdGuardAdapter(hass, resource, leisure)
    if resource.kind is ResourceKind.NINTENDO:
        return NintendoAdapter(hass, resource)
    raise NotImplementedError(f"Type de ressource non pris en charge : {resource.kind}")
