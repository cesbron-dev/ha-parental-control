"""API WebSocket : droits, configuration (parents) et état pour les cartes ; demandes."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .catalog import services_catalog
from .const import DOMAIN, SIGNAL_UPDATE
from .core.config_io import ConfigError, dump_config, parse_client_config
from .core.model import is_label_service
from .core.requests import RequestStatus, action_choices
from .engine import ParentalEngine
from .parents import bind_owners, is_parent, phone_status, trusted_phone_owners
from .serialize import serialize_requests, serialize_snapshot

_REGISTERED = f"{DOMAIN}_websocket_registered"


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    """Enregistre les commandes (globales à HA) une seule fois."""
    if hass.data.get(_REGISTERED):
        return
    hass.data[_REGISTERED] = True
    websocket_api.async_register_command(hass, ws_whoami)
    websocket_api.async_register_command(hass, ws_config_get)
    websocket_api.async_register_command(hass, ws_config_set)
    websocket_api.async_register_command(hass, ws_services_catalog)
    websocket_api.async_register_command(hass, ws_labels_list)
    websocket_api.async_register_command(hass, ws_label_switches_list)
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


async def _require_parent(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    engine: ParentalEngine,
) -> bool:
    """Parent (`parents.is_parent`, évalué sur la config courante) ; sinon erreur envoyée.

    La config expose les appareils et les cibles de notification : rien aux non-parents.
    """
    if await is_parent(hass, engine.config, connection.user.id):
        return True
    connection.send_error(msg["id"], "unauthorized", "Réservé aux parents")
    return False


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/whoami"})
@websocket_api.async_response
async def ws_whoami(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Droits de l'utilisateur de la connexion, pour les cartes et le panneau (ouvert à tous)."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    cfg = entries[0].runtime_data.config if entries else None
    user = connection.user
    connection.send_result(
        msg["id"],
        {
            "admin": user.is_admin,
            "parent": await is_parent(hass, cfg, user.id),
            "user_id": user.id,
        },
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/config/get"})
@websocket_api.async_response
async def ws_config_get(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    if not await _require_parent(hass, connection, msg, engine):
        return
    cfg = engine.config
    connection.send_result(
        msg["id"],
        {
            "config": None if cfg is None else dump_config(cfg),
            "phones": {} if cfg is None else await phone_status(hass, cfg),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/config/set",
        vol.Required("config"): dict,
        # Téléphones à réassocier au compte actuel de leur appareil (pas une clé de config).
        vol.Optional("rebind", default=[]): [str],
    }
)
@websocket_api.async_response
async def ws_config_set(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    if not await _require_parent(hass, connection, msg, engine):
        return
    try:
        # Propriétaires des téléphones déterminés par le serveur, jamais repris du client.
        cfg = bind_owners(hass, parse_client_config(msg["config"]), engine.config, msg["rebind"])
    except ConfigError as err:
        connection.send_error(msg["id"], "invalid_config", str(err))
        return
    await engine.set_config(cfg)
    connection.send_result(msg["id"], {"config": dump_config(cfg)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/services/catalog"})
@websocket_api.async_response
async def ws_services_catalog(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    if (engine := _engine(hass, connection, msg)) is None:
        return
    if not await _require_parent(hass, connection, msg, engine):
        return
    cfg = engine.config
    if cfg is None:  # installation neuve : pas encore de configuration
        connection.send_result(msg["id"], {"services": services_catalog(hass), "label_services": []})
        return
    services = services_catalog(hass, cfg)
    connection.send_result(
        msg["id"],
        {"services": services, "label_services": [s for s in services if is_label_service(s)]},
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/labels/list"})
@websocket_api.async_response
async def ws_labels_list(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Labels du registre de HA (pour choisir les labels de service et de cible)."""
    if (engine := _engine(hass, connection, msg)) is None:
        return
    if not await _require_parent(hass, connection, msg, engine):
        return
    labels = sorted(lr.async_get(hass).async_list_labels(), key=lambda lb: lb.name.casefold())
    connection.send_result(
        msg["id"],
        {
            "labels": [
                {"label_id": lb.label_id, "name": lb.name, "icon": lb.icon, "color": lb.color}
                for lb in labels
            ]
        },
    )


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/label_switches/list"})
@websocket_api.async_response
async def ws_label_switches_list(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Interrupteurs labellisés pilotés et ceux ignorés (avec la raison)."""
    if (engine := _engine(hass, connection, msg)) is None:
        return
    if not await _require_parent(hass, connection, msg, engine):
        return
    connection.send_result(
        msg["id"], {"switches": engine.label_switches, "issues": engine.label_issues}
    )


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
