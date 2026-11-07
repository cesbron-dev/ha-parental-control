"""Réponses des parents aux demandes de temps, depuis la notification de l'app HA.

Une réponse n'est retenue que si elle porte le jeton de la demande en attente ET que son
contexte vient d'un téléphone de la liste « Demandes » : le webhook `mobile_app` émet
l'événement avec le contexte de l'utilisateur enregistré (`registration_context`).
Être administrateur ne suffit jamais.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant
from homeassistant.util import slugify

if TYPE_CHECKING:
    from . import ParentalConfigEntry

_LOGGER = logging.getLogger(__name__)

EVENT_NOTIFICATION_ACTION = "mobile_app_notification_action"
ACTION_PREFIX = "PARENTAL_REQ"
MOBILE_APP = "mobile_app"
MOBILE_APP_SERVICE = "mobile_app_"


def parse_action(action: object) -> tuple[str, str, str] | None:
    """`"PARENTAL_REQ:id:jeton:choix"` → `(id, jeton, choix)` ; `None` sinon."""
    if not isinstance(action, str):
        return None
    parts = action.split(":")
    if len(parts) != 4 or parts[0] != ACTION_PREFIX or not all(parts[1:]):
        return None
    return parts[1], parts[2], parts[3]


def parent_user_ids(hass: HomeAssistant, targets: Sequence[str]) -> set[str]:
    """Utilisateurs propriétaires des téléphones `notify.mobile_app_<x>` de la liste.

    Les autres cibles (et les entrées incomplètes) sont ignorées. Tout utilisateur peut
    enregistrer un appareil au nom de son choix : un service auquel mènent plusieurs
    entrées `mobile_app` est ambigu, et aucun de leurs propriétaires n'est retenu.
    """
    services = set()
    for target in targets:
        domain, _, service = target.partition(".")
        if domain == "notify" and service.startswith(MOBILE_APP_SERVICE):
            services.add(service)
    owners: dict[str, list[object]] = {}
    for entry in hass.config_entries.async_entries(MOBILE_APP):
        device_name = entry.data.get("device_name")
        if not isinstance(device_name, str):
            continue
        service = MOBILE_APP_SERVICE + slugify(device_name)
        if service in services:
            owners.setdefault(service, []).append(entry.data.get("user_id"))
    users: set[str] = set()
    for service, user_ids in owners.items():
        if len(user_ids) > 1:
            _LOGGER.warning(
                "notify.%s : plusieurs appareils mobile_app portent ce nom ; "
                "aucune réponse aux demandes n'est acceptée par ce service",
                service,
            )
            continue
        user_id = user_ids[0]
        if isinstance(user_id, str) and user_id:
            users.add(user_id)
    return users


def async_setup_request_listener(
    hass: HomeAssistant, entry: ParentalConfigEntry
) -> CALLBACK_TYPE:
    """Écoute les actions de notification ; renvoie le désabonnement."""

    async def on_action(event: Event) -> None:
        parsed = parse_action(event.data.get("action", ""))
        if parsed is None:
            return  # action d'une autre intégration, ou mal formée
        request_id, token, choice = parsed
        engine = entry.runtime_data
        cfg = engine.config
        if cfg is None:
            return
        user_id = event.context.user_id
        if user_id is None or user_id not in parent_user_ids(hass, cfg.request_notify):
            # Jamais le jeton ni l'action complète dans le journal.
            _LOGGER.warning(
                "Réponse à la demande %s ignorée : l'utilisateur %s n'a pas de téléphone "
                "dans la liste des demandes",
                request_id,
                user_id,
            )
            return
        await engine.answer_request(request_id, token, choice, user_id)

    return hass.bus.async_listen(EVENT_NOTIFICATION_ACTION, on_action)
