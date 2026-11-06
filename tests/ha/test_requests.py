"""Demandes de temps : service `demander`, notifications, expiration, état publié."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from homeassistant.core import ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.parental_control.core.requests import RequestKind
from custom_components.parental_control.serialize import serialize_snapshot
from tests.fixtures import EX
from tests.ha.test_engine import TUESDAY, at, logbook_messages, tick

MARC = "notify.mobile_app_iphone_de_marc"
JULIE = "notify.mobile_app_iphone_de_julie"
CONFIG = {**EX, "request_notify": [MARC, JULIE]}
OPEN_CALL = {
    "kind": "open",
    "kid_id": "hugo",
    "resource_id": "tv",
    "service": "youtube",
    "minutes": 30,
    "options": [15, 30, 60, 120, None],
}


@pytest.fixture
def julie(hass) -> list[ServiceCall]:
    """Second parent : service `notify` simulé qui garde ses appels."""
    calls: list[ServiceCall] = []

    @callback
    def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", "mobile_app_iphone_de_julie", record)
    return calls


@pytest.fixture
def catalog(hass) -> None:
    entry = MockConfigEntry(domain="adguard_clients")
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(catalog={"youtube": "YouTube"})


async def _env(make_env, config=CONFIG):
    return await make_env(at(TUESDAY, 16, 30), config)


async def test_request_sends_actionable_notification_to_each_parent(
    make_env, julie, catalog
) -> None:
    env = await _env(make_env)
    req_id = await env.call("demander", OPEN_CALL, env.kid_ctx, return_response=True)
    await env.hass.async_block_till_done()
    marc = env.services.of("notify", "mobile_app_iphone_de_marc")
    assert len(marc) == 1 and len(julie) == 1
    for call in (marc[0], julie[0]):
        assert call.data["title"] == "Contrôle parental"
        assert call.data["message"] == "Hugo demande 30 min de YouTube sur Télé salon"
        assert call.data["data"]["tag"] == f"parental_control_{req_id['id']}"
        actions = call.data["data"]["actions"]
        assert actions[0]["title"] == "Accepter 30 min"
        assert actions[-1]["title"] == "Refuser"
        assert all(a["action"].startswith("PARENTAL_REQ:") for a in actions)
        assert actions[0]["action"].startswith(f"PARENTAL_REQ:{req_id['id']}:")
        assert actions[0]["action"].endswith(":0")


async def test_request_needs_no_code(make_env, julie) -> None:
    env = await _env(make_env)
    await env.call("demander", OPEN_CALL, env.kid_ctx)
    assert env.engine.decisions.exceptions == []
    assert len(env.engine.requests.visible(at(TUESDAY, 16, 30))) == 1


async def test_request_disabled_without_parents(make_env) -> None:
    env = await _env(make_env, {**EX, "request_notify": []})
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", OPEN_CALL, env.kid_ctx)
    assert err.value.translation_key == "requests_disabled"


async def test_duplicate_request_rejected(make_env, julie) -> None:
    env = await _env(make_env)
    await env.call("demander", OPEN_CALL, env.kid_ctx)
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", OPEN_CALL, env.kid_ctx)
    assert err.value.translation_key == "request_pending"


async def test_request_kid_must_own_resource(make_env, julie) -> None:
    cfg = copy.deepcopy(CONFIG)
    cfg["kids"].append({**cfg["kids"][0], "id": "autre", "name": "Autre", "calendar": None})
    env = await _env(make_env, cfg)
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", {**OPEN_CALL, "kid_id": "autre"}, env.kid_ctx)
    assert err.value.translation_key == "invalid_target"


async def test_request_invalid_duration_translated(make_env, julie) -> None:
    env = await _env(make_env)
    data = {"kind": "bonus", "kid_id": "hugo"}  # bonus sans durée
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", data, env.kid_ctx)
    assert err.value.translation_key == "invalid_request"


async def test_request_expires_after_15_minutes(hass, freezer, make_env, julie) -> None:
    env = await _env(make_env)
    entries = async_capture_events(hass, "logbook_entry")
    req_id = (await env.call("demander", OPEN_CALL, env.kid_ctx, return_response=True))["id"]
    await hass.async_block_till_done()
    await tick(hass, freezer, 15)
    assert env.engine.requests.get(req_id).status == "expired"
    clears = [c for c in julie if c.data["message"] == "clear_notification"]
    assert [c.data["data"] for c in clears] == [{"tag": f"parental_control_{req_id}"}]
    assert "Demande de Hugo sans réponse" in logbook_messages(entries)
    assert [e.data["name"] for e in entries][-1] == "Contrôle parental"


async def test_state_exposes_requests_without_token(make_env, julie) -> None:
    env = await _env(make_env)
    req_id = (await env.call("demander", OPEN_CALL, env.kid_ctx, return_response=True))["id"]
    req = env.engine.requests.get(req_id)
    payload = serialize_snapshot(env.engine, display=True)
    assert payload["requests_enabled"] is True
    (item,) = payload["requests"]
    assert item["id"] == req_id and item["kind"] == "open" and item["status"] == "pending"
    assert item["proposed"] == 30 and item["expires"] == req.expires.isoformat()
    assert not {"token", "options", "replace", "answered_by"} & item.keys()
    assert req.token not in json.dumps(payload)
    assert "requests" not in serialize_snapshot(env.engine)


async def test_simulation_prefixes_request_message(make_env, julie, catalog) -> None:
    env = await _env(make_env)
    env.engine.decisions.simulation = True
    await env.call("demander", OPEN_CALL, env.kid_ctx)
    await env.hass.async_block_till_done()
    assert julie[0].data["message"] == (
        "[Simulation] Hugo demande 30 min de YouTube sur Télé salon"
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"kind": RequestKind.OPEN, "resource_id": "tv", "service": "youtube", "proposed": 30},
         "Hugo demande 30 min de YouTube sur Télé salon"),
        ({"kind": RequestKind.OPEN, "service": "youtube", "proposed": 30},
         "Hugo demande 30 min de YouTube"),
        ({"kind": RequestKind.OPEN, "resource_id": "tv", "proposed": 30},
         "Hugo demande 30 min sur Télé salon"),
        ({"kind": RequestKind.OPEN, "resource_id": "tv", "service": "youtube", "proposed": None},
         "Hugo demande YouTube sur Télé salon jusqu'au prochain changement"),
        ({"kind": RequestKind.OPEN, "resource_id": "tv", "proposed": None},
         "Hugo demande Télé salon jusqu'au prochain changement"),
        ({"kind": RequestKind.BONUS, "proposed": 30}, "Hugo demande un bonus de 30 min"),
        ({"kind": RequestKind.BONUS, "resource_id": "switch", "proposed": 30},
         "Hugo demande un bonus de 30 min sur Switch"),
        ({"kind": RequestKind.TIMER, "proposed": 30}, "Hugo demande un minuteur de 30 min"),
        ({"kind": RequestKind.HOMEWORK}, "Hugo dit avoir terminé ses devoirs"),
    ],
)
async def test_request_message(make_env, julie, catalog, kwargs, expected) -> None:
    env = await _env(make_env)
    kind = kwargs.pop("kind")
    req_id = await env.engine.request_time(kind, "hugo", **kwargs)
    assert env.engine.request_message(env.engine.requests.get(req_id)) == expected
