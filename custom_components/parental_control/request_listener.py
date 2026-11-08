"""Réponses des parents aux demandes de temps, depuis la notification de l'app HA.

Une réponse n'est retenue que si elle porte le jeton de la demande en attente ET que son
contexte vient du propriétaire mémorisé d'un téléphone de la liste « Demandes », toujours
propriétaire de l'appareil (`parents.trusted_phone_owners`) : le webhook `mobile_app` émet
l'événement avec le contexte de l'utilisateur enregistré (`registration_context`).
Être administrateur ne suffit jamais.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant

from .parents import trusted_phone_owners

if TYPE_CHECKING:
    from . import ParentalConfigEntry

_LOGGER = logging.getLogger(__name__)

EVENT_NOTIFICATION_ACTION = "mobile_app_notification_action"
ACTION_PREFIX = "PARENTAL_REQ"


def parse_action(action: object) -> tuple[str, str, str] | None:
    """`"PARENTAL_REQ:id:jeton:choix"` → `(id, jeton, choix)` ; `None` sinon."""
    if not isinstance(action, str):
        return None
    parts = action.split(":")
    if len(parts) != 4 or parts[0] != ACTION_PREFIX or not all(parts[1:]):
        return None
    return parts[1], parts[2], parts[3]


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
        if user_id is None or user_id not in trusted_phone_owners(hass, cfg):
            # Jamais le jeton ni l'action complète dans le journal.
            _LOGGER.warning(
                "Réponse à la demande %s ignorée : l'utilisateur %s n'est pas le propriétaire "
                "reconnu d'un téléphone de la liste des demandes",
                request_id,
                user_id,
            )
            return
        await engine.answer_request(request_id, token, choice, user_id)

    return hass.bus.async_listen(EVENT_NOTIFICATION_ACTION, on_action)
