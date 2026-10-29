"""API WebSocket : configuration et état, pour la carte du tableau de bord."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_UPDATE
from .core.config_io import ConfigError, dump_config, parse_config
from .engine import ParentalEngine
from .serialize import serialize_snapshot

_REGISTERED = f"{DOMAIN}_websocket_registered"


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Enregistre les commandes (globales à HA) une seule fois."""
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True
    websocket_api.async_register_command(hass, ws_config_get)
    websocket_api.async_register_command(hass, ws_config_set)
    websocket_api.async_register_command(hass, ws_state)
    websocket_api.async_register_command(hass, ws_state_subscribe)


def _engine(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> ParentalEngine | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_loaded", "Contrôle parental non chargé")
        return None
    return entries[0].runtime_data


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/config/get"})
@callback
def ws_config_get(hass, connection, msg) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    cfg = engine.config
    connection.send_result(msg["id"], {"config": None if cfg is None else dump_config(cfg)})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/config/set", vol.Required("config"): dict}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_config_set(hass, connection, msg) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    try:
        cfg = parse_config(msg["config"])
    except ConfigError as err:
        connection.send_error(msg["id"], "invalid_config", str(err))
        return
    await engine.set_config(cfg)
    connection.send_result(msg["id"], {"config": dump_config(cfg)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/state"})
@callback
def ws_state(hass, connection, msg) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    connection.send_result(msg["id"], serialize_snapshot(engine))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/state/subscribe"})
@callback
def ws_state_subscribe(hass, connection, msg) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    msg_id = msg["id"]

    @callback
    def push() -> None:
        connection.send_message(websocket_api.event_message(msg_id, serialize_snapshot(engine)))

    connection.subscriptions[msg_id] = async_dispatcher_connect(hass, SIGNAL_UPDATE, push)
    connection.send_result(msg_id)
    push()
