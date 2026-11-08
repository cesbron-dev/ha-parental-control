"""API WebSocket : droits, configuration (lecture/écriture parents) et état (abonnement)."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parental_control.const import DOMAIN
from custom_components.parental_control.core.decisions import ManualException, Target
from custom_components.parental_control.core.config_io import dump_config, parse_config
from custom_components.parental_control.security import hash_code
from custom_components.parental_control.store import ParentalStore
from tests.fixtures import EX
from tests.ha.conftest import PARENT_PHONE, add_phone, bind_parent_phone
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


async def _client_for(hass, hass_ws_client, user):
    token = await hass.auth.async_create_refresh_token(user, "https://example.com")
    access = hass.auth.async_create_access_token(token)
    return await hass_ws_client(hass, access)


async def _client(hass, hass_ws_client, admin: bool):
    # Le premier utilisateur devient propriétaire : on le crée d'abord.
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    group = "system-admin" if admin else "system-users"
    user = await hass.auth.async_create_user("U", group_ids=[group])
    return await _client_for(hass, hass_ws_client, user)


@pytest.fixture
async def users(hass):
    """Administrateur, parent non admin (téléphone pas encore lié) et enfant."""
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    return SimpleNamespace(
        admin=await hass.auth.async_create_user("Olivier", group_ids=["system-admin"]),
        parent=await hass.auth.async_create_user("Manou", group_ids=["system-users"]),
        kid=await hass.auth.async_create_user("Tablette", group_ids=["system-users"]),
    )


@pytest.fixture
async def parent(hass, entry, users):
    """Manou, non admin, devenue parent : son téléphone est dans la liste."""
    await bind_parent_phone(hass, entry.runtime_data, users.parent)
    return users.parent


async def _send(client, msg: dict) -> dict:
    await client.send_json_auto_id(msg)
    return await client.receive_json()


def _assert_unauthorized(resp: dict) -> None:
    assert not resp["success"]
    assert "result" not in resp
    assert resp["error"] == {"code": "unauthorized", "message": "Réservé aux parents"}


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
    # La config expose les appareils et les cibles de notification : parents seulement.
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
    assert set(result) == {"kids", "resources", "closures", "paused", "simulation", "exceptions", "now",
        "requests", "requests_enabled"}
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
    assert first["event"]["simulation"] is False

    await entry.runtime_data.async_evaluate("test")
    await hass.async_block_till_done()
    pushed = await client.receive_json()
    assert pushed["type"] == "event"
    assert set(pushed["event"]) == {"kids", "resources", "closures", "paused", "simulation", "exceptions", "now",
        "requests", "requests_enabled"}


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


async def test_state_has_display_data_for_non_admin(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state"})
    res = (await client.receive_json())["result"]
    gabin = res["kids"]["gabin"]
    assert (gabin["name"], gabin["emoji"], gabin["color"]) == ("Gabin", "🎮", "#FF6B6B")
    assert gabin["timeline"]
    iphone = res["resources"]["iphone_gabin"]
    assert iphone["kind"] == "adguard_services"
    assert iphone["owners"] == ["gabin"]
    assert "youtube" in iphone["leisure"]
    assert iphone["leisure"] == sorted(iphone["leisure"])
    assert res["resources"]["tv"]["name"] == "Télé salon"
    assert "used_entity" not in res["resources"]["tv"]
    switch = res["resources"]["switch"]
    assert switch["used_entity"] == "sensor.switch_papa_temps_d_ecran_utilise"
    assert switch["remaining_entity"] == "sensor.switch_papa_temps_d_ecran_restant"
    assert res["now"] == at(TUESDAY, 16, 30).isoformat()


async def test_state_exception_has_ends_at(hass, entry, hass_ws_client) -> None:
    engine = entry.runtime_data
    engine.decisions.exceptions.append(
        ManualException(
            id="e1", target=Target(resource_id="tv"), open=True,
            created=at(TUESDAY, 16, 30), until=at(TUESDAY, 17, 0), signature=None,
        )
    )
    engine.decisions.exceptions.append(
        ManualException(
            id="e2", target=Target(kid_id="gabin"), open=True,
            created=at(TUESDAY, 16, 30), until=None, signature=None,
        )
    )
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state"})
    res = (await client.receive_json())["result"]
    ends = {e["id"]: e["ends_at"] for e in res["exceptions"]}
    assert ends["e1"] == at(TUESDAY, 17, 0).isoformat()
    assert ends["e2"] == res["kids"]["gabin"]["segment_end"]


async def test_state_leaks_no_secret(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state"})
    text = json.dumps((await client.receive_json())["result"])
    for secret in (
        "code_hash", "calendar", "calendar_map", "notify", "device_id", "limit_entity",
        "calendar.ecole_primaire", "adguard_iphone_gabin", "b64d274dc045916f9a6de862a104fbb5",
        "number.switch_papa_temps_d_ecran_max_aujourd_hui", "media_player.tv_salon",
    ):
        assert secret not in text


async def test_state_mixed_tv_exposes_kinds_and_icon(hass, freezer, hass_ws_client) -> None:
    await hass.config.async_set_time_zone("America/Toronto")
    freezer.move_to(at(TUESDAY, 16, 30))
    cfg = dump_config(parse_config(EX))
    tv = next(r for r in cfg["resources"] if r["id"] == "tv")
    tv["icon"] = "mdi:television"
    tv["devices"] = [
        {"name": "Samsung", "integrations": [
            {"kind": "media_player", "entity_id": "media_player.tv", "notify_service": None}]},
        {"name": "TV", "integrations": [{"kind": "adguard_services", "device_id": "d1"}]},
    ]
    await ParentalStore(hass).save_config(parse_config(cfg))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code("0123")})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state"})
    res = (await client.receive_json())["result"]["resources"]
    assert res["tv"]["kind"] == "media_player"
    assert res["tv"]["kinds"] == ["adguard_services", "media_player"]
    assert res["tv"]["icon"] == "mdi:television"
    assert res["iphone_gabin"]["icon"] is None


async def test_services_catalog_merges_adguard_entries(hass, entry, hass_ws_client) -> None:
    from types import SimpleNamespace

    first = MockConfigEntry(domain="adguard_clients")
    first.add_to_hass(hass)
    first.runtime_data = SimpleNamespace(catalog={"youtube": "YouTube", "tiktok": "TikTok"})
    second = MockConfigEntry(domain="adguard_clients")  # pas encore chargée : ignorée
    second.add_to_hass(hass)
    third = MockConfigEntry(domain="adguard_clients")
    third.add_to_hass(hass)
    third.runtime_data = SimpleNamespace(catalog={"discord": "Discord"})

    client = await _client(hass, hass_ws_client, admin=True)
    await client.send_json_auto_id({"type": "parental_control/services/catalog"})
    services = (await client.receive_json())["result"]["services"]
    assert list(services.items()) == [("discord", "Discord"), ("tiktok", "TikTok"), ("youtube", "YouTube")]


async def test_services_catalog_empty_and_admin_only(hass, entry, hass_ws_client) -> None:
    admin = await _client(hass, hass_ws_client, admin=True)
    await admin.send_json_auto_id({"type": "parental_control/services/catalog"})
    assert (await admin.receive_json())["result"] == {"services": {}}
    user = await _client(hass, hass_ws_client, admin=False)
    await user.send_json_auto_id({"type": "parental_control/services/catalog"})
    assert not (await user.receive_json())["success"]


async def test_state_requests_hidden_until_enabled(hass, entry, hass_ws_client) -> None:
    client = await _client(hass, hass_ws_client, admin=False)
    await client.send_json_auto_id({"type": "parental_control/state"})
    res = (await client.receive_json())["result"]
    assert res["requests_enabled"] is False
    assert res["requests"] == []


# --- parents non administrateurs -------------------------------------------------

GET = {"type": "parental_control/config/get"}
CATALOG = {"type": "parental_control/services/catalog"}


async def test_config_get_set_and_catalog_parent_non_admin(
    hass, entry, parent, hass_ws_client
) -> None:
    client = await _client_for(hass, hass_ws_client, parent)
    got = (await _send(client, GET))["result"]["config"]
    assert got["request_notify"] == [PARENT_PHONE]
    got["kids"][0]["name"] = "Renommé"
    resp = await _send(client, {"type": "parental_control/config/set", "config": got})
    assert resp["success"]
    assert entry.runtime_data.config.kid("gabin").name == "Renommé"
    assert (await _send(client, CATALOG))["result"] == {"services": {}}


async def test_config_get_non_parent_gets_no_config(
    hass, entry, parent, users, hass_ws_client
) -> None:
    """L'enfant non admin, même avec un parent dans la liste, ne reçoit rien de la config."""
    client = await _client_for(hass, hass_ws_client, users.kid)
    resp = await _send(client, GET)
    _assert_unauthorized(resp)
    assert PARENT_PHONE not in json.dumps(resp)
    _assert_unauthorized(await _send(client, CATALOG))
    before = entry.runtime_data.config
    resp = await _send(
        client, {"type": "parental_control/config/set", "config": dump_config(parse_config(EX))}
    )
    _assert_unauthorized(resp)
    assert entry.runtime_data.config == before


async def test_parent_loses_config_access_when_phone_removed(
    hass, entry, parent, hass_ws_client
) -> None:
    client = await _client_for(hass, hass_ws_client, parent)
    assert (await _send(client, GET))["success"]
    await entry.runtime_data.set_config(parse_config(EX))
    _assert_unauthorized(await _send(client, GET))


async def test_config_set_ignores_forged_owners(hass, entry, parent, users, hass_ws_client) -> None:
    """Le client prétend que le téléphone de Manou est à la tablette : ignoré."""
    tablet = "notify.mobile_app_tablette"
    add_phone(hass, "Tablette", users.kid.id)
    client = await _client_for(hass, hass_ws_client, users.admin)
    cfg = (await _send(client, GET))["result"]["config"]
    cfg["request_notify"].append(tablet)
    cfg["request_notify_owners"] = {PARENT_PHONE: users.kid.id, tablet: users.admin.id}
    resp = await _send(client, {"type": "parental_control/config/set", "config": cfg})
    assert resp["success"]
    owners = {PARENT_PHONE: parent.id, tablet: users.kid.id}
    assert entry.runtime_data.config.request_notify_owners == owners
    assert resp["result"]["config"]["request_notify_owners"] == owners


async def test_config_set_missing_device_rejected_config_unchanged(
    hass, entry, parent, hass_ws_client
) -> None:
    client = await _client_for(hass, hass_ws_client, parent)
    before = entry.runtime_data.config
    cfg = (await _send(client, GET))["result"]["config"]
    cfg["request_notify"].append("notify.mobile_app_inconnu")
    resp = await _send(client, {"type": "parental_control/config/set", "config": cfg})
    assert not resp["success"]
    assert resp["error"]["code"] == "invalid_config"
    assert "notify.mobile_app_inconnu" in resp["error"]["message"]
    assert entry.runtime_data.config == before


async def test_config_set_rebind(hass, entry, parent, users, hass_ws_client) -> None:
    """App réinstallée : l'appareil de ce nom appartient à un autre compte de Manou."""
    manou2 = await hass.auth.async_create_user("Manou 2", group_ids=["system-users"])
    [phone] = hass.config_entries.async_entries("mobile_app")
    hass.config_entries.async_update_entry(phone, data={**phone.data, "user_id": manou2.id})
    client = await _client_for(hass, hass_ws_client, users.admin)
    cfg = (await _send(client, GET))["result"]["config"]
    msg = {"type": "parental_control/config/set", "config": cfg}
    assert (await _send(client, msg))["success"]
    assert entry.runtime_data.config.request_notify_owners == {PARENT_PHONE: parent.id}
    assert (await _send(client, {**msg, "rebind": [PARENT_PHONE]}))["success"]
    assert entry.runtime_data.config.request_notify_owners == {PARENT_PHONE: manou2.id}
    # `rebind` est un champ du message, jamais une clé de la configuration.
    assert "rebind" not in dump_config(entry.runtime_data.config)


async def test_config_get_includes_phone_status(hass, entry, parent, users, hass_ws_client) -> None:
    client = await _client_for(hass, hass_ws_client, users.admin)
    result = (await _send(client, GET))["result"]
    assert result["phones"] == {PARENT_PHONE: {"owner": parent.id, "status": "ok"}}


async def test_whoami(hass, entry, parent, users, hass_ws_client) -> None:
    expected = {
        users.admin.id: {"admin": True, "parent": True},
        parent.id: {"admin": False, "parent": True},
        users.kid.id: {"admin": False, "parent": False},
    }
    for user_id, rights in expected.items():
        user = await hass.auth.async_get_user(user_id)
        client = await _client_for(hass, hass_ws_client, user)
        resp = await _send(client, {"type": "parental_control/whoami"})
        assert resp["result"] == {**rights, "user_id": user_id}
