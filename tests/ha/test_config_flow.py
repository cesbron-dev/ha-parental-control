"""Config flow, options flow, code parent et stockage."""

from datetime import date, timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import Context, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.parental_control.const import DOMAIN
from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.core.decisions import Decisions
from custom_components.parental_control.security import (
    check_unlock,
    hash_code,
    verify_code,
)
from custom_components.parental_control.store import ParentalStore
from tests.core.test_config_io import EX


async def test_config_flow_creates_entry_with_hashed_code(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": "1234"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    code_hash = result["data"]["code_hash"]
    assert code_hash.startswith("pbkdf2$")
    assert "1234" not in code_hash
    assert verify_code("1234", code_hash)
    await hass.async_block_till_done()


@pytest.mark.parametrize("code", ["123", "123456789", "12a4", ""])
async def test_config_flow_rejects_invalid_code(hass: HomeAssistant, code: str) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"code": code}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"code": "invalid_code"}


async def test_config_flow_single_instance(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code("1234")}
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    if result["type"] is FlowResultType.FORM:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "5678"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_changes_code(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code("1234")}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"code": "12"}
    )
    assert result["errors"] == {"code": "invalid_code"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"code": "987654"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert verify_code("987654", entry.data["code_hash"])
    assert not verify_code("1234", entry.data["code_hash"])


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code("1234")}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, ParentalStore)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED


def test_verify_code() -> None:
    stored = hash_code("4321")
    assert stored.count("$") == 2
    assert verify_code("4321", stored)
    assert not verify_code("1234", stored)
    assert not verify_code("4321", "garbage")
    # Sel aléatoire : deux hachages du même code diffèrent.
    assert hash_code("4321") != stored


async def test_check_unlock_admin_needs_no_code(hass: HomeAssistant) -> None:
    stored = hash_code("1234")
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    admin = await hass.auth.async_create_user("Parent", group_ids=["system-admin"])
    assert not admin.is_owner
    await check_unlock(hass, Context(user_id=admin.id), None, stored)
    await check_unlock(hass, Context(user_id=admin.id), "0000", stored)


async def test_check_unlock_automation_needs_no_code(hass: HomeAssistant) -> None:
    await check_unlock(hass, Context(), None, hash_code("1234"))


async def test_check_unlock_non_admin_requires_code(hass: HomeAssistant) -> None:
    stored = hash_code("1234")
    # Le premier utilisateur créé devient propriétaire (donc admin) : on le crée d'abord.
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    kid = await hass.auth.async_create_user("Tablette", group_ids=["system-users"])
    assert not kid.is_admin
    ctx = Context(user_id=kid.id)

    with pytest.raises(ServiceValidationError) as err:
        await check_unlock(hass, ctx, None, stored)
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "code_required"

    with pytest.raises(ServiceValidationError) as err:
        await check_unlock(hass, ctx, "", stored)
    assert err.value.translation_key == "code_required"

    with pytest.raises(ServiceValidationError) as err:
        await check_unlock(hass, ctx, "9999", stored)
    assert err.value.translation_key == "code_invalid"

    await check_unlock(hass, ctx, "1234", stored)


async def test_check_unlock_unknown_user_requires_code(hass: HomeAssistant) -> None:
    with pytest.raises(ServiceValidationError):
        await check_unlock(hass, Context(user_id="inconnu"), None, hash_code("1234"))


async def test_store_load_empty(hass: HomeAssistant) -> None:
    cfg, dec = await ParentalStore(hass).load()
    assert cfg is None
    assert dec.to_dict() == Decisions().to_dict()


async def test_store_round_trip(hass: HomeAssistant, hass_storage) -> None:
    store = ParentalStore(hass)
    cfg = parse_config(EX)
    dec = Decisions()
    dec.homework_done["gabin"] = date(2026, 10, 29)
    await store.save_config(cfg)
    await store.save_state(dec)
    await hass.async_block_till_done()

    assert hass_storage["parental_control.config"]["version"] == 1
    # L'état est écrit en différé (1 s).
    assert "parental_control.state" not in hass_storage
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()
    assert hass_storage["parental_control.state"]["data"] == dec.to_dict()

    cfg2, dec2 = await ParentalStore(hass).load()
    assert cfg2 == cfg
    assert dec2.to_dict() == dec.to_dict()


async def test_check_unlock_error_message_is_translated(hass: HomeAssistant) -> None:
    """Le message (anglais côté backend) vient de translations/en.json."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code("1234")}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await check_unlock(hass, Context(user_id="inconnu"), "0000", hash_code("1234"))
    assert str(err.value) == "Invalid parent code"
