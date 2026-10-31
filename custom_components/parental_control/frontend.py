"""Sert les cartes Lovelace de l'intégration et les injecte dans le frontend."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Deux drapeaux distincts, posés seulement après succès : un échec se rattrape au rechargement.
_PATH_REGISTERED = f"{DOMAIN}_frontend_path_registered"
_MODULE_REGISTERED = f"{DOMAIN}_frontend_module_registered"
_WWW = Path(__file__).parent / "www"
_URL_BASE = "/parental_control_static"
# Lue une seule fois : la version sert à invalider le cache du navigateur.
_VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text("utf-8"))["version"]


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Expose `www/` et charge le point d'entrée des cartes, une seule fois chacun."""
    # `http` est une dépendance facultative (after_dependencies) : sans serveur, rien à servir.
    if not hass.data.get(_PATH_REGISTERED) and (http := getattr(hass, "http", None)) is not None:
        try:
            await http.async_register_static_paths([StaticPathConfig(_URL_BASE, str(_WWW), True)])
        except RuntimeError:
            # Routeur déjà figé (serveur démarré) : les cartes manquent, pas le moteur.
            _LOGGER.warning("Chemin statique des cartes non enregistré", exc_info=True)
        else:
            hass.data[_PATH_REGISTERED] = True
    if hass.data.get(_MODULE_REGISTERED):
        return
    # `add_extra_js_url` lit ce registre, créé par le setup du composant `frontend`.
    if DATA_EXTRA_MODULE_URL not in hass.data:
        _LOGGER.warning("Composant frontend non chargé : les cartes ne seront pas injectées")
        return
    add_extra_js_url(hass, f"{_URL_BASE}/parental-cards.js?v={_VERSION}")
    hass.data[_MODULE_REGISTERED] = True
