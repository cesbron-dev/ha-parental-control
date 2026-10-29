"""API WebSocket : configuration (lecture/écriture admin) et état (abonnement)."""

from __future__ import annotations

import copy

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parental_control.const import DOMAIN
from custom_components.parental_control.core.config_io import dump_config, parse_config
from custom_components.parental_control.security import hash_code
from custom_components.parental_control.store import ParentalStore
from tests.fixtures import EX
from tests.ha.test_engine import TUESDAY, at

# Avertissement tiers du composant `http` de HA (requis par websocket_api), fatal sous `-W error`.
pytestmark = pytest.mark.filterwarnings(
    "ignore:It is recommended to use web:aiohttp.web_exceptions.NotAppKeyWarning"
)


@pytest.fixture
async def entry(hass: HomeAssistant, freezer) -> MockConfigEntry:
    await hass.config.async_set_time_zone("America/Toronto")
    freezer.move_to(at(TUESDAY, 16, 30))
    await ParentalStore(hass).save_config(parse_config(EX))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code("0123")})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _client(hass, hass_ws_client, admin: bool):
    # Le premier utilisateur devient propriétaire : on le crée d'abord.
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    group = "system-admin" if admin else "system-users"
    user = await hass.auth.async_create_user("U", group_ids=[group])
    token = await hass.auth.async_create_refresh_token(user, "https://example.com")
    access = hass.auth.async_create_access_token(token)
    return await hass_ws_client(hass, access)


async def test_config_get_set_round_trip(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=True)
    await client.send_json_auto_id({"type": "parental_control/config/get"})
    got = (await client.receive_json())["result"]["config"]
    assert got == dump_config(parse_config(EX))

    new = copy.deepcopy(got)
    new["kids"][0]["name"] = "Renommé"
    await client.send_json_auto_id({"type": "parental_control/config/set", "config": new})
    resp = await client.receive_json()
    assert resp["success"]
    await client.send_json_auto_id({"type": "parental_control/config/get"})
    again = (await client.receive_json())["result"]["config"]
    assert again["kids"][0]["name"] == "Renommé"
    assert dump_config(entry.runtime_data.config) == again


async def test_config_get_and_set_non_admin_rejected(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=False)
    # La config expose les appareils et les cibles de notification : admin seulement.
    await client.send_json_auto_id({"type": "parental_control/config/get"})
    resp = await client.receive_json()
    assert not resp["success"]
    assert resp["error"]["code"] == "unauthorized"
    await client.send_json_auto_id(
        {"type": "parental_control/config/set", "config": dump_config(parse_config(EX))}
    )
    resp = await client.receive_json()
    assert not resp["success"]
    assert resp["error"]["code"] == "unauthorized"


async def test_config_set_invalid_returns_error(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=True)
    await client.send_json_auto_id({"type": "parental_control/config/set", "config": {"kids": 5}})
    resp = await client.receive_json()
    assert not resp["success"]
    assert resp["error"]["code"] == "invalid_config"
    assert resp["error"]["message"]


async def test_state_and_not_loaded(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state"})
    result = (await client.receive_json())["result"]
    assert set(result) == {"kids", "resources", "closures", "paused", "exceptions"}
    assert "gabin" in result["kids"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await client.send_json_auto_id({"type": "parental_control/state"})
    resp = await client.receive_json()
    assert resp["error"]["code"] == "not_loaded"


async def test_state_subscribe_pushes_on_update(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state/subscribe"})
    assert (await client.receive_json())["type"] == "result"
    first = await client.receive_json()
    assert first["type"] == "event"
    assert first["event"]["paused"] is False

    await entry.runtime_data.async_evaluate("test")
    await hass.async_block_till_done()
    pushed = await client.receive_json()
    assert pushed["type"] == "event"
    assert set(pushed["event"]) == {"kids", "resources", "closures", "paused", "exceptions"}


async def test_state_subscribe_survives_entry_reload(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state/subscribe"})
    await client.receive_json()
    await client.receive_json()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "pause", {"active": True}, blocking=True)
    await hass.async_block_till_done()

    # Les messages sont ordonnés : on lit les évènements jusqu'à la réponse à `state`.
    await client.send_json_auto_id({"type": "parental_control/state"})
    last = None
    while (msg := await client.receive_json())["type"] == "event":
        last = msg
    assert msg["success"]
    assert last is not None
    assert last["event"]["paused"] is True
