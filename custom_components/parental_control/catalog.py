"""Catalogue des services AdGuard, partagé par le WebSocket et les notifications."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import label_registry as lr

from .adapters.adguard import ADGUARD_DOMAIN
from .core.model import Config


def services_catalog(hass: HomeAssistant, cfg: Config | None = None) -> dict[str, str]:
    """Services connus (id → nom) : AdGuard, plus les labels de service de `cfg`.

    Les services AdGuard sont réunis depuis les entrées `adguard_clients` chargées.

    Lu dans le coordinateur de cette intégration (`runtime_data.catalog`) : vide si elle est
    absente ou pas encore chargée ; le panneau garde alors la saisie libre. Un label de service
    (`label:<id>`) porte le nom lu dans le registre des labels, et n'apparaît que s'il existe encore.
    """
    catalog: dict[str, str] = {}
    for entry in hass.config_entries.async_entries(ADGUARD_DOMAIN):
        found = getattr(getattr(entry, "runtime_data", None), "catalog", None)
        if isinstance(found, dict):
            catalog.update({str(k): str(v) for k, v in found.items()})
    if cfg is not None:
        registry = lr.async_get(hass)
        for service in cfg.label_services:
            if (label := registry.async_get_label(service.label_id)) is not None:
                catalog[label_service_id(service.label_id)] = label.name
    return dict(sorted(catalog.items(), key=lambda kv: kv[1].casefold()))
