"""Catalogue des services AdGuard, partagé par le WebSocket et les notifications."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .adapters.adguard import ADGUARD_DOMAIN


def services_catalog(hass: HomeAssistant) -> dict[str, str]:
    """Services AdGuard connus (id → nom), réunis depuis les entrées `adguard_clients` chargées.

    Lu dans le coordinateur de cette intégration (`runtime_data.catalog`) : vide si elle est
    absente ou pas encore chargée ; le panneau garde alors la saisie libre. Les services du
    parent (noms, icônes) ne passent plus par ici : ils sont publiés dans l'état.
    """
    catalog: dict[str, str] = {}
    for entry in hass.config_entries.async_entries(ADGUARD_DOMAIN):
        found = getattr(getattr(entry, "runtime_data", None), "catalog", None)
        if isinstance(found, dict):
            catalog.update({str(k): str(v) for k, v in found.items()})
    return dict(sorted(catalog.items(), key=lambda kv: kv[1].casefold()))
