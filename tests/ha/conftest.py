"""Fixtures des tests Home Assistant de l'intégration."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from homeassistant.auth.models import User
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parental_control.const import DOMAIN, STORE_VERSION
from custom_components.parental_control.core.config_io import dump_config, parse_config
from custom_components.parental_control.engine import ParentalEngine
from custom_components.parental_control.security import hash_code
from custom_components.parental_control.store import ParentalStore
from tests.fixtures import EX
from tests.ha.test_engine import Services

CODE = "0123"
PARENT_PHONE = "notify.mobile_app_ipad_de_manou"


def add_phone(hass: HomeAssistant, device_name: str, user_id: str) -> MockConfigEntry:
    """Appareil `mobile_app` de `user_id` : son service est `notify.mobile_app_<nom>`."""
    entry = MockConfigEntry(
        domain="mobile_app",
        data={
            "device_name": device_name,
            "user_id": user_id,
            "app_id": "io.robbie.HomeAssistant",
            "webhook_id": f"{device_name}-{user_id}",
        },
    )
    entry.add_to_hass(hass)
    return entry


async def bind_parent_phone(hass: HomeAssistant, engine: ParentalEngine, parent: User) -> None:
    """Le téléphone de `parent` est dans `request_notify` et mémorisé comme le sien."""
    add_phone(hass, "iPad de Manou", parent.id)
    cfg = dump_config(engine.config)
    cfg["request_notify"] = [*cfg["request_notify"], PARENT_PHONE]
    cfg["request_notify_owners"] = {**cfg["request_notify_owners"], PARENT_PHONE: parent.id}
    await engine.set_config(parse_config(cfg))
    await hass.async_block_till_done()


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
    parent: User
    services: Services

    @property
    def admin_ctx(self) -> Context:
        return Context(user_id=self.admin.id)

    @property
    def kid_ctx(self) -> Context:
        return Context(user_id=self.kid.id)

    @property
    def parent_ctx(self) -> Context:
        return Context(user_id=self.parent.id)

    async def bind_parent(self) -> None:
        """Fait de `parent` (non admin) un parent : son téléphone est dans la liste."""
        await bind_parent_phone(self.hass, self.engine, self.parent)

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
    # Parent non admin : parent seulement une fois son téléphone lié (`Env.bind_parent`).
    parent = await hass.auth.async_create_user("Manou", group_ids=["system-users"])
    assert admin.is_admin and not kid.is_admin and not parent.is_admin

    async def _make(moment, config: dict | None = None, raw: bool = False) -> Env:
        """`raw` : `config` est écrite telle quelle (ex. ancien format sans
        `request_notify_owners`) au lieu de passer par `parse_config`/`dump_config`."""
        freezer.move_to(moment)
        if raw:
            await Store(hass, STORE_VERSION, f"{DOMAIN}.config").async_save(config)
        else:
            await ParentalStore(hass).save_config(parse_config(EX if config is None else config))
        entry = MockConfigEntry(
            domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code(CODE)}
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return Env(hass, entry, entry.runtime_data, admin, kid, parent, services)

    return _make
