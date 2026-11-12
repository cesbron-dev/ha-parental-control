"""Adaptateur interrupteur : `switch` coupé quand la ressource est fermée.

Option `turn_on_when_allowed` : le rallumer une fois, au passage de fermé à autorisé (l'appareil
lui-même, pas une exception de service). Le dernier état vu n'est qu'en mémoire : après un
redémarrage ou un enregistrement de la configuration, un interrupteur déjà autorisé n'est pas
rallumé. Le rallumage est aussi perdu si l'interrupteur est indisponible à ce moment ou si l'appel
échoue (journalisé).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError

from ..core.config_io import TURN_ON_WHEN_ALLOWED
from ..core.evaluator import ResourceState
from ..texts import text
from .base import ha_started

_LOGGER = logging.getLogger(__name__)


class SwitchAdapter:
    def __init__(self, hass: HomeAssistant, label: str, options: Mapping[str, Any]) -> None:
        self.hass = hass
        self.label = label  # « <appareil physique> (<entity_id>) »
        self._entity_id: str = options["entity_id"]
        self._turn_on_when_allowed = bool(options.get(TURN_ON_WHEN_ALLOWED, False))
        # Dernier état voulu vu (None : aucun depuis le démarrage) ; sert à repérer le passage à
        # « autorisé ». Mis à jour aussi en simulation, qui ne fait que décrire.
        self._last_open: bool | None = None
        self._missing_logged = False

    def entity_ids(self) -> list[str]:
        return [self._entity_id]

    def _state(self) -> State | None:
        state = self.hass.states.get(self._entity_id)
        if state is None and not self._missing_logged and ha_started(self.hass):
            self._missing_logged = True
            _LOGGER.warning("%s: entity not found", self.label)
        return state

    def in_use(self) -> bool:
        state = self._state()
        return state is not None and state.state == "on"

    def _closed(self, desired: ResourceState) -> bool:
        # Même règle que le lecteur : un service ouvert par exception garde l'appareil allumé.
        return not desired.open and not desired.opened_services

    def drifted(self, desired: ResourceState) -> bool:
        return self._closed(desired) and self.in_use()

    def _action(self, desired: ResourceState) -> str | None:
        """« turn_off », « turn_on » ou None ; retient l'état voulu pour le prochain passage."""
        was_closed = self._last_open is False
        self._last_open = desired.open
        if self._closed(desired):
            return "turn_off" if self.in_use() else None
        # Seul le passage de l'appareil à « autorisé » rallume : une exception de service sur un
        # appareil fermé garde l'interrupteur allumé (R6) sans l'allumer.
        if self._turn_on_when_allowed and was_closed and desired.open:
            state = self._state()
            if state is not None and state.state == "off":
                return "turn_on"
        return None

    def describe(self, desired: ResourceState) -> list[str]:
        # Retient l'état voulu comme `apply` : en simulation, l'enveloppe appelle `describe` à sa
        # place, une fois par application.
        action = self._action(desired)
        if action == "turn_off":
            return [text(self.hass, "simulation.switch_off", label=self.label)]
        if action == "turn_on":
            return [text(self.hass, "simulation.switch_on", label=self.label)]
        return []

    def describe_grant(self, minutes: int) -> list[str]:
        return []

    def describe_warn(self, message: str) -> list[str]:
        return []

    async def apply(self, desired: ResourceState) -> None:
        action = self._action(desired)
        if action is None:
            return
        try:
            await self.hass.services.async_call(
                "switch", action, {"entity_id": self._entity_id}, blocking=True
            )
        except HomeAssistantError as err:
            _LOGGER.warning("%s: %s failed: %s", self.label, action, err)

    async def warn(self, message: str) -> None:
        return

    async def grant(self, minutes: int) -> None:
        raise NotImplementedError

    def pause_state(self) -> ResourceState:
        """État fermé de la pause (aussi décrit en simulation)."""
        return ResourceState(
            open=False,
            reason_code="paused",
            until=None,
            used_minutes=None,
            remaining_minutes=None,
            blocked_services=frozenset(),
        )

    async def force_close(self) -> None:
        await self.apply(self.pause_state())
