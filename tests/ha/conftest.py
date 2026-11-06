"""Fixtures des tests Home Assistant de l'intégration."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from homeassistant.auth.models import User
from homeassistant.core import Context, HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parental_control.const import DOMAIN
from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.engine import ParentalEngine
from custom_components.parental_control.security import hash_code
from custom_components.parental_control.store import ParentalStore
from tests.fixtures import EX
from tests.ha.test_engine import Services

CODE = "0123"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Active le chargement de `custom_components/` dans chaque test."""
    yield


@dataclass
class Env:
    hass: HomeAssistant
    entry: MockConfigEntry
    engine: ParentalEngine
    admin: User
    kid: User
    services: Services

    @property
    def admin_ctx(self) -> Context:
        return Context(user_id=self.admin.id)

    @property
    def kid_ctx(self) -> Context:
        return Context(user_id=self.kid.id)

    async def call(self, service: str, data: dict, context: Context | None = None,
                   return_response: bool = False):
        return await self.hass.services.async_call(
            DOMAIN, service, data, blocking=True, context=context,
            return_response=return_response,
        )


@pytest.fixture
async def make_env(hass: HomeAssistant, freezer):
    await hass.config.async_set_time_zone("America/Toronto")
    services = Services(hass)
    # Le premier utilisateur créé devient propriétaire : on le crée d'abord.
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    admin = await hass.auth.async_create_user("Parent", group_ids=["system-admin"])
    kid = await hass.auth.async_create_user("Tablette", group_ids=["system-users"])
    assert admin.is_admin and not kid.is_admin

    async def _make(moment, config: dict | None = None) -> Env:
        freezer.move_to(moment)
        await ParentalStore(hass).save_config(parse_config(EX if config is None else config))
        entry = MockConfigEntry(
            domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code(CODE)}
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return Env(hass, entry, entry.runtime_data, admin, kid, services)

    return _make
