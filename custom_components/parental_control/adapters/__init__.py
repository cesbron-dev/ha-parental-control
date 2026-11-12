"""Adaptateurs : traduction de l'état voulu en appels de services HA."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import HomeAssistant

from ..core.model import Integration, PhysicalDevice, Resource, ResourceKind
from .adguard import AdGuardAdapter
from .base import Adapter
from .composite import CompositeAdapter
from .media_player import MediaPlayerAdapter
from .nintendo import NintendoAdapter
from .switch import SwitchAdapter

__all__ = ["Adapter", "CompositeAdapter", "build_adapter"]


def build_adapter(
    hass: HomeAssistant,
    resource: Resource,
    leisure: frozenset[str],
    adguard_ids: Callable[[Iterable[str]], frozenset[str]],
) -> CompositeAdapter:
    """Composite de la ressource, un membre par intégration ; `leisure` (services du parent
    gérés : loisirs et sur demande) et `adguard_ids` (leur traduction) ne servent qu'à AdGuard."""
    return CompositeAdapter(
        resource,
        [
            _member(hass, device, integration, leisure, adguard_ids)
            for device in resource.devices
            for integration in device.integrations
        ],
    )


def _member(
    hass: HomeAssistant,
    device: PhysicalDevice,
    integration: Integration,
    leisure: frozenset[str],
    adguard_ids: Callable[[Iterable[str]], frozenset[str]],
) -> Adapter:
    options = integration.options
    if integration.kind is ResourceKind.MEDIA_PLAYER:
        return MediaPlayerAdapter(hass, f"{device.name} ({options['entity_id']})", options)
    if integration.kind is ResourceKind.SWITCH:
        return SwitchAdapter(hass, f"{device.name} ({options['entity_id']})", options)
    if integration.kind is ResourceKind.ADGUARD:
        return AdGuardAdapter(hass, device.name, options, leisure, adguard_ids)
    if integration.kind is ResourceKind.NINTENDO:
        return NintendoAdapter(hass, device.name, options)
    raise NotImplementedError(f"Type d'intégration non pris en charge : {integration.kind}")
