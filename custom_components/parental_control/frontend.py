"""Sert les cartes Lovelace de l'intégration et les injecte dans le frontend."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_REGISTERED = f"{DOMAIN}_frontend_registered"
_WWW = Path(__file__).parent / "www"
_URL_BASE = "/parental_control_static"
# Lue une seule fois : la version sert à invalider le cache du navigateur.
_MODULES = "frontend_extra_module_url"  # rempli par le composant `frontend`
_VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text("utf-8"))["version"]


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Expose `www/` et charge le point d'entrée des cartes, une seule fois."""
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True
    # `http` est une dépendance facultative (after_dependencies) : sans serveur, rien à servir.
    if (http := getattr(hass, "http", None)) is not None:
        await http.async_register_static_paths([StaticPathConfig(_URL_BASE, str(_WWW), True)])
    # `add_extra_js_url` lit ce registre, créé par le setup du composant `frontend`.
    if _MODULES not in hass.data:
        return
    add_extra_js_url(hass, f"{_URL_BASE}/parental-cards.js?v={_VERSION}")
