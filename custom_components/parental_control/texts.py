"""Textes du serveur dans la langue système de HA (`hass.config.language`, repli `en`)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .core.i18n import base_language, msg


def server_language(hass: HomeAssistant) -> str:
    """`en` ou `fr` : langue des textes produits sans utilisateur (notifications, journal)."""
    return base_language(hass.config.language)


def text(hass: HomeAssistant, key: str, **params: object) -> str:
    """`msg` dans la langue système de HA."""
    return msg(server_language(hass), key, **params)
