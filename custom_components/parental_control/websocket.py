"""API WebSocket : configuration et état, pour les cartes ; demandes, pour l'écran « Demandes »."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .catalog import services_catalog
from .const import DOMAIN, SIGNAL_UPDATE
from .core.config_io import ConfigError, dump_config, parse_config
from .core.requests import RequestStatus, action_choices
from .engine import ParentalEngine
from .parents import trusted_phone_owners
from .serialize import serialize_requests, serialize_snapshot

_REGISTERED = f"{DOMAIN}_websocket_registered"


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Enregistre les commandes (globales à HA) une seule fois."""
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True
    websocket_api.async_register_command(hass, ws_config_get)
    websocket_api.async_register_command(hass, ws_config_set)
    websocket_api.async_register_command(hass, ws_services_catalog)
    websocket_api.async_register_command(hass, ws_state)
    websocket_api.async_register_command(hass, ws_state_subscribe)
    websocket_api.async_register_command(hass, ws_requests_subscribe)
    websocket_api.async_register_command(hass, ws_requests_answer)


def _engine(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> ParentalEngine | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_loaded", "Contrôle parental non chargé")
        return None
    return entries[0].runtime_data


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/config/get"})
@websocket_api.require_admin
@callback
def ws_config_get(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    cfg = engine.config
    connection.send_result(msg["id"], {"config": None if cfg is None else dump_config(cfg)})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/config/set", vol.Required("config"): dict}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_config_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    try:
        cfg = parse_config(msg["config"])
    except ConfigError as err:
        connection.send_error(msg["id"], "invalid_config", str(err))
        return
    await engine.set_config(cfg)
    connection.send_result(msg["id"], {"config": dump_config(cfg)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/services/catalog"})
@websocket_api.require_admin
@callback
def ws_services_catalog(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    connection.send_result(msg["id"], {"services": services_catalog(hass)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/state"})
@callback
def ws_state(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    connection.send_result(msg["id"], serialize_snapshot(engine, display=True))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/state/subscribe"})
@callback
def ws_state_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if _engine(hass, connection, msg) is None:
        return
    msg_id = msg["id"]

    @callback
    def push() -> None:
        # SIGNAL_UPDATE est global : on relit le moteur courant (l'entrée a pu être rechargée).
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            return
        connection.send_message(
            websocket_api.event_message(msg_id, serialize_snapshot(entries[0].runtime_data, display=True))
        )

    connection.subscriptions[msg_id] = async_dispatcher_connect(hass, SIGNAL_UPDATE, push)
    connection.send_result(msg_id)
    push()


def _can_answer(hass: HomeAssistant, engine: ParentalEngine, user_id: str) -> bool:
    """Même règle que la réponse par notification : propriétaire reconnu d'un téléphone de
    la liste (`parents.trusted_phone_owners`). Être administrateur ne suffit pas."""
    return user_id in trusted_phone_owners(hass, engine.config)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/requests/subscribe"})
@callback
def ws_requests_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if _engine(hass, connection, msg) is None:
        return
    msg_id = msg["id"]
    user_id = connection.user.id

    @callback
    def push() -> None:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            return
        engine = entries[0].runtime_data
        # Recalculé à chaque envoi : la liste des téléphones a pu changer.
        payload = serialize_requests(engine, can_answer=_can_answer(hass, engine, user_id))
        connection.send_message(websocket_api.event_message(msg_id, payload))

    connection.subscriptions[msg_id] = async_dispatcher_connect(hass, SIGNAL_UPDATE, push)
    connection.send_result(msg_id)
    push()


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/requests/answer",
        vol.Required("request_id"): str,
        vol.Required("choice"): str,
    }
)
@websocket_api.async_response
async def ws_requests_answer(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Réponse depuis l'écran : réservée aux parents, comme celle de la notification."""
    if (engine := _engine(hass, connection, msg)) is None:
        return
    user_id = connection.user.id
    if not _can_answer(hass, engine, user_id):
        connection.send_error(
            msg["id"], "unauthorized", "Seul un parent de la liste des demandes peut répondre"
        )
        return
    req = engine.requests.get(msg["request_id"])
    if req is None or req.status != RequestStatus.PENDING:
        connection.send_error(msg["id"], "not_pending", "Demande déjà traitée ou expirée")
        return
    # Un choix inconnu ne doit pas consommer la demande (le moteur la marquerait « impossible »).
    if msg["choice"] not in dict(action_choices(req)):
        connection.send_error(msg["id"], "invalid_choice", "Choix inconnu")
        return
    status = await engine.answer_request(req.id, req.token, msg["choice"], user_id)
    if status is None:  # expirée ou prise par l'autre parent entre-temps
        connection.send_error(msg["id"], "not_pending", "Demande déjà traitée ou expirée")
        return
    connection.send_result(msg["id"], {"status": status.value})
