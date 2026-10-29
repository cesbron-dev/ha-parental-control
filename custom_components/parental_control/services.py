"""Services du contrôle parental ; les actions qui débloquent exigent le code parent."""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import config_validation as cv

from .const import CONF_CODE, CONF_CODE_HASH, DOMAIN
from .core.config_io import ConfigError, parse_config
from .core.decisions import Target
from .security import check_unlock

if TYPE_CHECKING:
    from . import ParentalConfigEntry

SERVICE_HOMEWORK_DONE = "devoirs_termines"
SERVICE_ADD_BONUS = "ajouter_bonus"
SERVICE_EXCEPTION = "exception"
SERVICE_CANCEL_EXCEPTION = "annuler_exception"
SERVICE_START_TIMER = "demarrer_minuteur"
SERVICE_STOP_TIMER = "arreter_minuteur"
SERVICE_PAUSE = "pause"
SERVICE_IMPORT_CONFIG = "importer_configuration"

ATTR_KID_ID = "kid_id"
ATTR_RESOURCE_ID = "resource_id"
ATTR_SERVICE = "service"
ATTR_MINUTES = "minutes"
ATTR_OPEN = "open"
ATTR_EXCEPTION_ID = "exception_id"
ATTR_ACTIVE = "active"
ATTR_CONFIG = "config"

_CODE = {vol.Optional(CONF_CODE): cv.string}
_MINUTES = vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
_TARGET_MSG = "exactement un de kid_id ou resource_id"

HOMEWORK_SCHEMA = vol.Schema({vol.Required(ATTR_KID_ID): cv.string, **_CODE})
ADD_BONUS_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Required(ATTR_MINUTES): _MINUTES,
            vol.Exclusive(ATTR_KID_ID, "target", msg=_TARGET_MSG): cv.string,
            vol.Exclusive(ATTR_RESOURCE_ID, "target", msg=_TARGET_MSG): cv.string,
            **_CODE,
        }
    ),
    cv.has_at_least_one_key(ATTR_KID_ID, ATTR_RESOURCE_ID),
)
EXCEPTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_OPEN): cv.boolean,
        vol.Optional(ATTR_RESOURCE_ID): cv.string,
        vol.Optional(ATTR_KID_ID): cv.string,
        vol.Optional(ATTR_SERVICE): cv.string,
        vol.Optional(ATTR_MINUTES): _MINUTES,
        **_CODE,
    }
)
CANCEL_EXCEPTION_SCHEMA = vol.Schema(
    {vol.Required(ATTR_EXCEPTION_ID): cv.string, **_CODE}
)
START_TIMER_SCHEMA = vol.Schema(
    {vol.Required(ATTR_KID_ID): cv.string, vol.Required(ATTR_MINUTES): _MINUTES, **_CODE}
)
STOP_TIMER_SCHEMA = vol.Schema({vol.Required(ATTR_KID_ID): cv.string, **_CODE})
PAUSE_SCHEMA = vol.Schema({vol.Required(ATTR_ACTIVE): cv.boolean, **_CODE})
IMPORT_CONFIG_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG): dict, **_CODE})

SERVICES = (
    SERVICE_HOMEWORK_DONE,
    SERVICE_ADD_BONUS,
    SERVICE_EXCEPTION,
    SERVICE_CANCEL_EXCEPTION,
    SERVICE_START_TIMER,
    SERVICE_STOP_TIMER,
    SERVICE_PAUSE,
    SERVICE_IMPORT_CONFIG,
)


def async_setup_services(hass: HomeAssistant, entry: ParentalConfigEntry) -> None:
    """Enregistre les services du domaine pour l'entrée chargée."""

    async def unlock(call: ServiceCall) -> None:
        await check_unlock(
            hass, call.context, call.data.get(CONF_CODE), entry.data[CONF_CODE_HASH]
        )

    async def homework_done(call: ServiceCall) -> None:
        await unlock(call)
        await entry.runtime_data.homework_done(call.data[ATTR_KID_ID])

    async def add_bonus(call: ServiceCall) -> None:
        await unlock(call)
        await entry.runtime_data.add_bonus(
            call.data[ATTR_MINUTES],
            kid_id=call.data.get(ATTR_KID_ID),
            resource_id=call.data.get(ATTR_RESOURCE_ID),
        )

    async def exception(call: ServiceCall) -> ServiceResponse:
        is_open = call.data[ATTR_OPEN]
        if is_open:
            await unlock(call)
        target = Target(
            resource_id=call.data.get(ATTR_RESOURCE_ID),
            kid_id=call.data.get(ATTR_KID_ID),
            service=call.data.get(ATTR_SERVICE),
        )
        exc_id = await entry.runtime_data.add_exception(
            target, is_open, call.data.get(ATTR_MINUTES)
        )
        return {"id": exc_id} if call.return_response else None

    async def cancel_exception(call: ServiceCall) -> None:
        exc_id = call.data[ATTR_EXCEPTION_ID]
        engine = entry.runtime_data
        # Annuler une fermeture rouvre : code exigé. Id inconnu : rien à protéger.
        if any(e.id == exc_id and not e.open for e in engine.decisions.exceptions):
            await unlock(call)
        await engine.cancel_exception(exc_id)

    async def start_timer(call: ServiceCall) -> None:
        await unlock(call)
        await entry.runtime_data.start_timer(call.data[ATTR_KID_ID], call.data[ATTR_MINUTES])

    async def stop_timer(call: ServiceCall) -> None:
        await entry.runtime_data.stop_timer(call.data[ATTR_KID_ID])

    async def pause(call: ServiceCall) -> None:
        active = call.data[ATTR_ACTIVE]
        if not active:
            await unlock(call)
        await entry.runtime_data.set_pause(active)

    async def import_config(call: ServiceCall) -> None:
        if call.context.user_id is not None:
            user = await hass.auth.async_get_user(call.context.user_id)
            if user is None or not user.is_admin:
                raise Unauthorized(context=call.context)
        try:
            cfg = parse_config(call.data[ATTR_CONFIG])
        except ConfigError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_config",
                translation_placeholders={"error": str(err)},
            ) from err
        await entry.runtime_data.set_config(cfg)

    register = hass.services.async_register
    register(DOMAIN, SERVICE_HOMEWORK_DONE, homework_done, HOMEWORK_SCHEMA)
    register(DOMAIN, SERVICE_ADD_BONUS, add_bonus, ADD_BONUS_SCHEMA)
    register(
        DOMAIN, SERVICE_EXCEPTION, exception, EXCEPTION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    register(DOMAIN, SERVICE_CANCEL_EXCEPTION, cancel_exception, CANCEL_EXCEPTION_SCHEMA)
    register(DOMAIN, SERVICE_START_TIMER, start_timer, START_TIMER_SCHEMA)
    register(DOMAIN, SERVICE_STOP_TIMER, stop_timer, STOP_TIMER_SCHEMA)
    register(DOMAIN, SERVICE_PAUSE, pause, PAUSE_SCHEMA)
    register(DOMAIN, SERVICE_IMPORT_CONFIG, import_config, IMPORT_CONFIG_SCHEMA)


def async_unload_services(hass: HomeAssistant) -> None:
    """Retire les services du domaine."""
    for service in SERVICES:
        hass.services.async_remove(DOMAIN, service)
