"""Config flow : instance unique et code parent (options : changer le code)."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_CODE, CONF_CODE_HASH, DOMAIN
from .security import hash_code

_CODE_RE = re.compile(r"^\d{4,8}$")

_CODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CODE): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


def _valid_code(code: Any) -> bool:
    return isinstance(code, str) and _CODE_RE.fullmatch(code) is not None


class ParentalControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Création de l'unique entrée de l'intégration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input[CONF_CODE]
            if _valid_code(code):
                code_hash = await self.hass.async_add_executor_job(hash_code, code)
                return self.async_create_entry(
                    title="Contrôle parental", data={CONF_CODE_HASH: code_hash}
                )
            errors[CONF_CODE] = "invalid_code"

        return self.async_show_form(
            step_id="user", data_schema=_CODE_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ParentalControlOptionsFlow()


class ParentalControlOptionsFlow(OptionsFlow):
    """Changement du code parent (le hachage reste dans `entry.data`)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input[CONF_CODE]
            if _valid_code(code):
                code_hash = await self.hass.async_add_executor_job(hash_code, code)
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={**self.config_entry.data, CONF_CODE_HASH: code_hash},
                )
                return self.async_create_entry(data={})
            errors[CONF_CODE] = "invalid_code"

        return self.async_show_form(
            step_id="init", data_schema=_CODE_SCHEMA, errors=errors
        )
