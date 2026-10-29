"""Persistance de la configuration et des décisions parentales."""

from __future__ import annotations

import logging

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORE_VERSION
from .core.config_io import ConfigError, dump_config, parse_config
from .core.decisions import Decisions
from .core.model import Config

_LOGGER = logging.getLogger(__name__)

_SAVE_DELAY = 1
INVALID_CONFIG_NOTIFICATION = f"{DOMAIN}_invalid_config"


class ParentalStore:
    """Deux `Store` : `parental_control.config` et `parental_control.state`."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._config_store: Store[dict] = Store(hass, STORE_VERSION, f"{DOMAIN}.config")
        self._state_store: Store[dict] = Store(hass, STORE_VERSION, f"{DOMAIN}.state")

    async def load(self) -> tuple[Config | None, Decisions]:
        """Config (None si jamais enregistrée ou invalide) et décisions (vides par défaut)."""
        raw_cfg = await self._config_store.async_load()
        raw_state = await self._state_store.async_load()
        dec = Decisions.from_dict(raw_state) if raw_state is not None else Decisions()
        cfg = None
        if raw_cfg is not None:
            try:
                cfg = parse_config(raw_cfg)
            except ConfigError as err:
                # Les décisions restent valables : une config corrigée les retrouvera.
                _LOGGER.error("Configuration enregistrée invalide, moteur inactif : %s", err)
                persistent_notification.async_create(
                    self._hass,
                    "Contrôle parental : configuration invalide, moteur inactif",
                    title="Contrôle parental",
                    notification_id=INVALID_CONFIG_NOTIFICATION,
                )
        return cfg, dec

    async def save_config(self, cfg: Config) -> None:
        await self._config_store.async_save(dump_config(cfg))

    async def save_state(self, dec: Decisions) -> None:
        """Écriture différée d'1 s : les rafales de changements sont regroupées."""
        self._state_store.async_delay_save(dec.to_dict, _SAVE_DELAY)

    async def flush_state(self, dec: Decisions) -> None:
        """Écriture immédiate (déchargement) ; annule une écriture différée en attente."""
        await self._state_store.async_save(dec.to_dict())
