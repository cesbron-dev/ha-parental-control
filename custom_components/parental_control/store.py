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
from .texts import text

_LOGGER = logging.getLogger(__name__)

_SAVE_DELAY = 1
INVALID_CONFIG_NOTIFICATION = f"{DOMAIN}_invalid_config"


class ParentalStore:
    """Deux `Store` : `parental_control.config` et `parental_control.state`."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._config_store: Store[dict] = Store(hass, STORE_VERSION, f"{DOMAIN}.config")
        self._state_store: Store[dict] = Store(hass, STORE_VERSION, f"{DOMAIN}.state")
        # Vrai si la configuration chargée était à l'ancien format (sans la clé
        # `request_notify_owners`) : l'association automatique des téléphones est à faire, une
        # seule fois. Faux dès qu'une configuration est enregistrée (`dump_config` écrit la clé).
        self.owners_migration_pending = False

    async def load(self) -> tuple[Config | None, Decisions]:
        """Config (None si jamais enregistrée ou invalide) et décisions (vides par défaut)."""
        raw_cfg = await self._config_store.async_load()
        raw_state = await self._state_store.async_load()
        dec = Decisions.from_dict(raw_state) if raw_state is not None else Decisions()
        if raw_cfg is None and raw_state is None:
            # Nouvelle installation : on démarre en simulation, rien n'est touché d'office.
            dec.simulation = True
        cfg = None
        if raw_cfg is not None:
            try:
                cfg = parse_config(raw_cfg)
                self.owners_migration_pending = "request_notify_owners" not in raw_cfg
                if raw_cfg.get("version") == 2:
                    # Ancien format (identifiants français) : réécrit en version 3.
                    await self.save_config(cfg)
                    self.owners_migration_pending = "request_notify_owners" not in raw_cfg
            except ConfigError as err:
                # Les décisions restent valables : une config corrigée les retrouvera.
                _LOGGER.error("Stored configuration invalid, engine inactive: %s", err)
                persistent_notification.async_create(
                    self._hass,
                    text(self._hass, "invalid_config.message"),
                    title=text(self._hass, "notify.title"),
                    notification_id=INVALID_CONFIG_NOTIFICATION,
                )
        return cfg, dec

    async def save_config(self, cfg: Config) -> None:
        await self._config_store.async_save(dump_config(cfg))
        self.owners_migration_pending = False

    async def save_state(self, dec: Decisions) -> None:
        """Écriture différée d'1 s : les rafales de changements sont regroupées."""
        self._state_store.async_delay_save(dec.to_dict, _SAVE_DELAY)

    async def flush_state(self, dec: Decisions) -> None:
        """Écriture immédiate (déchargement) ; annule une écriture différée en attente."""
        await self._state_store.async_save(dec.to_dict())
