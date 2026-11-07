"""Demandes de temps : service `demander`, notifications, expiration, état publié."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from homeassistant.core import Context, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.core.decisions import Target
from custom_components.parental_control.core.requests import RequestKind
from custom_components.parental_control.request_listener import (
    parent_user_ids,
    parse_action,
)
from custom_components.parental_control.serialize import serialize_snapshot
from tests.fixtures import EX
from tests.ha.test_engine import (
    SATURDAY,
    TUESDAY,
    at,
    logbook_messages,
    set_nintendo,
    tick,
)

OLIVIER = "notify.mobile_app_iphone_de_olivier"
MANOU = "notify.mobile_app_iphone_de_manou"
CONFIG = {**EX, "request_notify": [OLIVIER, MANOU]}
# Une exception par service vise une ressource AdGuard (`tv` n'est qu'un media_player).
OPEN_CALL = {
    "kind": "open",
    "kid_id": "gabin",
    "resource_id": "iphone_gabin",
    "service": "youtube",
    "minutes": 30,
    "options": [15, 30, 60, 120, None],
}


@pytest.fixture
def manou(hass) -> list[ServiceCall]:
    """Second parent : service `notify` simulé qui garde ses appels."""
    calls: list[ServiceCall] = []

    @callback
    def record(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", "mobile_app_iphone_de_manou", record)
    return calls


@pytest.fixture
def catalog(hass) -> None:
    entry = MockConfigEntry(domain="adguard_clients")
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(catalog={"youtube": "YouTube"})


async def _env(make_env, config=CONFIG):
    return await make_env(at(TUESDAY, 16, 30), config)


async def test_request_sends_actionable_notification_to_each_parent(
    make_env, manou, catalog
) -> None:
    env = await _env(make_env)
    req_id = await env.call("demander", OPEN_CALL, env.kid_ctx, return_response=True)
    await env.hass.async_block_till_done()
    olivier = env.services.of("notify", "mobile_app_iphone_de_olivier")
    assert len(olivier) == 1 and len(manou) == 1
    for call in (olivier[0], manou[0]):
        assert call.data["title"] == "Contrôle parental"
        assert call.data["message"] == "Gabin demande 30 min de YouTube sur iPhone Gabin"
        assert call.data["data"]["tag"] == f"parental_control_{req_id['id']}"
        actions = call.data["data"]["actions"]
        assert actions[0]["title"] == "Accepter 30 min"
        assert actions[-1]["title"] == "Refuser"
        assert all(a["action"].startswith("PARENTAL_REQ:") for a in actions)
        assert actions[0]["action"].startswith(f"PARENTAL_REQ:{req_id['id']}:")
        assert actions[0]["action"].endswith(":0")


async def test_request_needs_no_code(make_env, manou) -> None:
    env = await _env(make_env)
    await env.call("demander", OPEN_CALL, env.kid_ctx)
    assert env.engine.decisions.exceptions == []
    assert len(env.engine.requests.visible(at(TUESDAY, 16, 30))) == 1


async def test_request_disabled_without_parents(make_env) -> None:
    env = await _env(make_env, {**EX, "request_notify": []})
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", OPEN_CALL, env.kid_ctx)
    assert err.value.translation_key == "requests_disabled"


async def test_duplicate_request_rejected(make_env, manou) -> None:
    env = await _env(make_env)
    await env.call("demander", OPEN_CALL, env.kid_ctx)
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", OPEN_CALL, env.kid_ctx)
    assert err.value.translation_key == "request_pending"


async def test_request_kid_must_own_resource(make_env, manou) -> None:
    cfg = copy.deepcopy(CONFIG)
    cfg["kids"].append({**cfg["kids"][0], "id": "autre", "name": "Autre", "calendar": None})
    env = await _env(make_env, cfg)
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", {**OPEN_CALL, "kid_id": "autre"}, env.kid_ctx)
    assert err.value.translation_key == "invalid_target"


async def test_request_invalid_duration_translated(make_env, manou) -> None:
    env = await _env(make_env)
    data = {"kind": "bonus", "kid_id": "gabin"}  # bonus sans durée
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", data, env.kid_ctx)
    assert err.value.translation_key == "invalid_request"


async def test_request_expires_after_15_minutes(hass, freezer, make_env, manou) -> None:
    env = await _env(make_env)
    entries = async_capture_events(hass, "logbook_entry")
    req_id = (await env.call("demander", OPEN_CALL, env.kid_ctx, return_response=True))["id"]
    await hass.async_block_till_done()
    await tick(hass, freezer, 15)
    assert env.engine.requests.get(req_id).status == "expired"
    clears = [c for c in manou if c.data["message"] == "clear_notification"]
    assert [c.data["data"] for c in clears] == [{"tag": f"parental_control_{req_id}"}]
    assert "Demande de Gabin sans réponse" in logbook_messages(entries)
    assert [e.data["name"] for e in entries][-1] == "Contrôle parental"


async def test_state_exposes_requests_without_token(make_env, manou) -> None:
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


async def test_simulation_prefixes_request_message(make_env, manou, catalog) -> None:
    env = await _env(make_env)
    env.engine.decisions.simulation = True
    await env.call("demander", OPEN_CALL, env.kid_ctx)
    await env.hass.async_block_till_done()
    assert manou[0].data["message"] == (
        "[Simulation] Gabin demande 30 min de YouTube sur iPhone Gabin"
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"kind": RequestKind.OPEN, "resource_id": "iphone_gabin", "service": "youtube",
          "proposed": 30},
         "Gabin demande 30 min de YouTube sur iPhone Gabin"),
        ({"kind": RequestKind.OPEN, "service": "youtube", "proposed": 30},
         "Gabin demande 30 min de YouTube"),
        ({"kind": RequestKind.OPEN, "resource_id": "tv", "proposed": 30},
         "Gabin demande 30 min sur Télé salon"),
        ({"kind": RequestKind.OPEN, "resource_id": "iphone_gabin", "service": "youtube",
          "proposed": None},
         "Gabin demande YouTube sur iPhone Gabin jusqu'au prochain changement"),
        ({"kind": RequestKind.OPEN, "resource_id": "tv", "proposed": None},
         "Gabin demande Télé salon jusqu'au prochain changement"),
        ({"kind": RequestKind.BONUS, "proposed": 30}, "Gabin demande un bonus de 30 min"),
        ({"kind": RequestKind.BONUS, "resource_id": "switch", "proposed": 30},
         "Gabin demande un bonus de 30 min sur Switch"),
        ({"kind": RequestKind.TIMER, "proposed": 30}, "Gabin demande un minuteur de 30 min"),
        ({"kind": RequestKind.HOMEWORK}, "Gabin dit avoir terminé ses devoirs"),
    ],
)
async def test_request_message(make_env, manou, catalog, kwargs, expected) -> None:
    env = await _env(make_env)
    kind = kwargs.pop("kind")
    req_id = await env.engine.request_time(kind, "gabin", **kwargs)
    assert env.engine.request_message(env.engine.requests.get(req_id)) == expected


# --- réponse depuis la notification ---------------------------------------------

EVENT = "mobile_app_notification_action"


@pytest.fixture
async def manou_user(hass):
    """Parent non admin, propriétaire du téléphone « iPhone de Manou »."""
    user = await hass.auth.async_create_user("Manou", group_ids=["system-users"])
    assert not user.is_admin
    return user


def add_phone(hass, device_name: str, user_id: str) -> None:
    MockConfigEntry(
        domain="mobile_app",
        data={
            "device_name": device_name,
            "user_id": user_id,
            "app_id": "io.robbie.HomeAssistant",
            "webhook_id": device_name,
        },
    ).add_to_hass(hass)


async def _parents_env(make_env, manou_user, moment=None, config=CONFIG, *, olivier=True):
    env = await make_env(moment or at(TUESDAY, 16, 30), config)
    add_phone(env.hass, "iPhone de Manou", manou_user.id)
    if olivier:
        add_phone(env.hass, "iPhone de Olivier", env.admin.id)
    return env


async def _ask(env, data=OPEN_CALL) -> str:
    req_id = (await env.call("demander", data, env.kid_ctx, return_response=True))["id"]
    await env.hass.async_block_till_done()
    return req_id


def _actions(calls: list[ServiceCall]) -> dict[str, str]:
    """Choix → action, d'après la dernière notification actionnable reçue."""
    sent = [c for c in calls if "actions" in c.data.get("data", {})]
    return {a["action"].rsplit(":", 1)[1]: a["action"] for a in sent[-1].data["data"]["actions"]}


async def _answer(env, action: str, user_id: str | None) -> None:
    env.hass.bus.async_fire(EVENT, {"action": action}, context=Context(user_id=user_id))
    await env.hass.async_block_till_done()


def _clears(calls: list[ServiceCall], req_id: str) -> list[ServiceCall]:
    return [
        c for c in calls
        if c.data["message"] == "clear_notification"
        and c.data["data"] == {"tag": f"parental_control_{req_id}"}
    ]


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("PARENTAL_REQ:abc:tok:0", ("abc", "tok", "0")),
        ("PARENTAL_REQ:abc:tok:refuse", ("abc", "tok", "refuse")),
        ("OTHER:abc:tok:0", None),
        ("PARENTAL_REQ:abc:tok", None),
        ("PARENTAL_REQ:abc:tok:0:extra", None),
        ("PARENTAL_REQ::tok:0", None),
        ("PARENTAL_REQ:abc::0", None),
        ("PARENTAL_REQ:abc:tok:", None),
        ("PARENTAL_REQ:abc:to:k:0", None),
        ("", None),
        (None, None),
        (42, None),
    ],
)
def test_parse_action(action, expected) -> None:
    assert parse_action(action) == expected


async def test_parent_non_admin_accepts_with_other_duration(
    hass, make_env, manou, manou_user
) -> None:
    env = await _parents_env(make_env, manou_user)
    entries = async_capture_events(hass, "logbook_entry")
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    choice = str(req.options.index(60))
    await _answer(env, _actions(manou)[choice], manou_user.id)
    assert req.status == "accepted" and req.granted == 60
    assert req.answered_by == "Manou"
    (exc,) = env.engine.decisions.exceptions
    assert exc.open and exc.target == Target(resource_id="iphone_gabin", service="youtube")
    assert exc.until == at(TUESDAY, 17, 30)
    olivier = env.services.of("notify", "mobile_app_iphone_de_olivier")
    assert len(_clears(olivier, req_id)) == 1 and len(_clears(manou, req_id)) == 1
    assert "Demande de Gabin acceptée par Manou : 1 h" in logbook_messages(entries)


async def test_tablet_user_cannot_answer(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    await _answer(env, _actions(manou)["0"], env.kid.id)
    assert env.engine.requests.get(req_id).status == "pending"
    assert env.engine.decisions.exceptions == []


async def test_admin_without_phone_in_list_cannot_answer(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user, olivier=False)
    req_id = await _ask(env)
    await _answer(env, _actions(manou)["0"], env.admin.id)
    assert env.engine.requests.get(req_id).status == "pending"
    assert env.engine.decisions.exceptions == []


async def test_answer_without_user_ignored(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    await _answer(env, _actions(manou)["0"], None)
    assert env.engine.requests.get(req_id).status == "pending"


async def test_wrong_token_ignored(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    await _answer(env, f"PARENTAL_REQ:{req_id}:faux:0", manou_user.id)
    assert env.engine.requests.get(req_id).status == "pending"
    assert env.engine.decisions.exceptions == []


async def test_unauthorized_answer_logs_without_token(
    make_env, manou, manou_user, caplog: pytest.LogCaptureFixture
) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    await _answer(env, _actions(manou)["0"], env.kid.id)
    assert f"Réponse à la demande {req_id} ignorée" in caplog.text
    assert req.token not in caplog.text


async def test_first_answer_wins(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    actions = _actions(manou)
    await _answer(env, actions["0"], manou_user.id)
    await _answer(env, actions["refuse"], env.admin.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "accepted" and req.answered_by == "Manou"
    assert len(env.engine.decisions.exceptions) == 1


async def test_refuse(hass, make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    entries = async_capture_events(hass, "logbook_entry")
    req_id = await _ask(env)
    await _answer(env, _actions(manou)["refuse"], manou_user.id)
    assert env.engine.requests.get(req_id).status == "refused"
    assert env.engine.decisions.exceptions == []
    assert "Demande de Gabin refusée par Manou" in logbook_messages(entries)
    assert len(_clears(manou, req_id)) == 1


async def test_accept_until_change(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    await _answer(env, _actions(manou)[str(req.options.index(None))], manou_user.id)
    assert req.status == "accepted" and req.granted is None
    (exc,) = env.engine.decisions.exceptions
    assert exc.open and exc.until is None and exc.signature is not None


async def test_accept_replaces_listed_exceptions(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    closing = await env.engine.add_exception(
        Target(resource_id="iphone_gabin", service="youtube"), False, 30
    )
    await _ask(env, {**OPEN_CALL, "replace": [closing, "absente"]})
    await _answer(env, _actions(manou)["0"], manou_user.id)
    (exc,) = env.engine.decisions.exceptions
    assert exc.id != closing and exc.open


async def test_accept_bonus_on_switch_resource(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user, at(SATURDAY, 10, 0))
    set_nintendo(env.hass)
    req_id = await _ask(
        env, {"kind": "bonus", "kid_id": "gabin", "resource_id": "switch", "minutes": 30}
    )
    await _answer(env, _actions(manou)["0"], manou_user.id)
    assert env.engine.requests.get(req_id).status == "accepted"
    assert [c.data for c in env.services.of("nintendo_parental_controls", "add_bonus_time")] == [
        {"device_id": "b64d274dc045916f9a6de862a104fbb5", "bonus_time": 30}
    ]


async def test_accept_bonus_on_kid(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user, at(SATURDAY, 10, 0))
    await _ask(env, {"kind": "bonus", "kid_id": "gabin", "minutes": 20})
    await _answer(env, _actions(manou)["0"], manou_user.id)
    assert env.engine.decisions.bonus_minutes(SATURDAY, kid_id="gabin") == 20


async def test_accept_timer(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user, at(SATURDAY, 10, 0))
    req_id = await _ask(env, {"kind": "timer", "kid_id": "gabin", "minutes": 30})
    await _answer(env, _actions(manou)["0"], manou_user.id)
    assert env.engine.requests.get(req_id).status == "accepted"
    timer = env.engine.decisions.active_timer("gabin", at(SATURDAY, 10, 0))
    assert timer is not None and timer.end == at(SATURDAY, 10, 30)


async def test_accept_homework(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env, {"kind": "homework", "kid_id": "gabin"})
    await _answer(env, _actions(manou)["accept"], manou_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "accepted" and req.granted is None
    assert env.engine.decisions.homework_done_on("gabin", TUESDAY)


async def test_unknown_choice_marks_failed(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    base = _actions(manou)["0"].rsplit(":", 1)[0]
    await _answer(env, f"{base}:accept", manou_user.id)  # « accept » : devoirs seulement
    assert req.status == "failed" and req.reason == "Choix inconnu"
    assert env.engine.decisions.exceptions == []
    assert len(_clears(manou, req_id)) == 1


async def test_accept_impossible_marks_failed(
    hass, freezer, make_env, manou, manou_user
) -> None:
    env = await _parents_env(make_env, manou_user, at(SATURDAY, 19, 55))
    entries = async_capture_events(hass, "logbook_entry")
    req_id = await _ask(env, {"kind": "timer", "kid_id": "gabin", "minutes": 30})
    await tick(hass, freezer, 6)  # 20:01 : hors de la plage quota
    await _answer(env, _actions(manou)["0"], manou_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "failed" and req.reason
    assert env.engine.decisions.timers == []
    assert any(
        m.startswith("Demande de Gabin acceptée par Manou, mais impossible : ")
        for m in logbook_messages(entries)
    )


async def test_non_mobile_app_target_ignored(make_env, manou, manou_user) -> None:
    config = {**CONFIG, "request_notify": [*CONFIG["request_notify"], "notify.persistent_notification"]}
    env = await _parents_env(make_env, manou_user, config=config)
    assert parent_user_ids(env.hass, config["request_notify"]) == {
        manou_user.id, env.admin.id
    }
    req_id = await _ask(env)
    await _answer(env, _actions(manou)["0"], manou_user.id)
    assert env.engine.requests.get(req_id).status == "accepted"


async def test_answer_after_config_removed_kid(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env, {"kind": "homework", "kid_id": "gabin"})
    cfg = copy.deepcopy(CONFIG)
    cfg["kids"][0].update(id="lea", name="Léa")
    for resource in cfg["resources"]:
        resource["owners"] = ["lea"]
    cfg["kids"][0]["resource_modes"] = {}
    await env.engine.set_config(parse_config(cfg))
    await _answer(env, _actions(manou)["accept"], manou_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "failed" and req.reason


async def test_late_answer_after_expiry_ignored(
    hass, freezer, make_env, manou, manou_user
) -> None:
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    await tick(hass, freezer, 15)
    await _answer(env, _actions(manou)["0"], manou_user.id)
    assert env.engine.requests.get(req_id).status == "expired"
    assert env.engine.decisions.exceptions == []


async def test_unexpected_error_still_finishes_request(make_env, manou, manou_user) -> None:
    """Une erreur imprévue ne laisse jamais la demande réservée (statut provisoire)."""
    env = await _parents_env(make_env, manou_user)
    req_id = await _ask(env)
    _, token, _ = parse_action(_actions(manou)["0"])

    async def boom(*_args, **_kwargs):
        raise RuntimeError("panne")

    env.engine.add_exception = boom
    with pytest.raises(RuntimeError):
        await env.engine.answer_request(req_id, token, "0", manou_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "failed" and req.resolved_at is not None
    await env.hass.async_block_till_done()
    assert len(_clears(manou, req_id)) == 1


async def test_duplicate_device_name_trusted_for_nobody(
    make_env, manou, manou_user, caplog: pytest.LogCaptureFixture
) -> None:
    """La tablette enregistre un appareil au même nom que celui de Manou : ni l'une ni
    l'autre ne peut répondre par ce service."""
    env = await _parents_env(make_env, manou_user, olivier=False)
    add_phone(env.hass, "iPhone de Manou", env.kid.id)
    assert parent_user_ids(env.hass, CONFIG["request_notify"]) == set()
    assert "mobile_app_iphone_de_manou" in caplog.text and "plusieurs" in caplog.text
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    for user_id in (env.kid.id, manou_user.id):
        await _answer(env, _actions(manou)["0"], user_id)
        assert req.status == "pending"
    assert req.token not in caplog.text


async def test_duplicate_device_name_keeps_other_phones(make_env, manou, manou_user) -> None:
    env = await _parents_env(make_env, manou_user)
    add_phone(env.hass, "iPhone de Manou", env.kid.id)
    assert parent_user_ids(env.hass, CONFIG["request_notify"]) == {env.admin.id}


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({**OPEN_CALL, "resource_id": "tv"}, "invalid_target"),  # pas d'AdGuard sur la télé
        ({"kind": "open", "kid_id": "gabin", "minutes": 30}, "invalid_target"),
        ({"kind": "open", "kid_id": "gabin", "resource_id": "switch", "minutes": 30},
         "nintendo_use_bonus"),
        ({"kind": "bonus", "kid_id": "gabin", "resource_id": "iphone_gabin", "minutes": 30},
         "invalid_target"),
        ({"kind": "timer", "kid_id": "gabin", "resource_id": "tv", "minutes": 30},
         "invalid_request"),
        ({"kind": "homework", "kid_id": "gabin", "resource_id": "tv"}, "invalid_request"),
    ],
)
async def test_impossible_request_rejected_at_creation(make_env, manou, data, key) -> None:
    env = await _env(make_env)
    data = {k: v for k, v in data.items() if v is not None}
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", data, env.kid_ctx)
    assert err.value.translation_key == key
    assert env.engine.requests.visible(at(TUESDAY, 16, 30)) == []
    assert manou == []


@pytest.mark.parametrize(
    "data",
    [
        {**OPEN_CALL, "resource_id": None},  # service pour tous les appareils de l'enfant
        {"kind": "open", "kid_id": "gabin", "resource_id": "tv", "minutes": 30},
        {"kind": "bonus", "kid_id": "gabin", "resource_id": "tv", "minutes": 30},
        {"kind": "bonus", "kid_id": "gabin", "resource_id": "switch", "minutes": 30},
        {"kind": "bonus", "kid_id": "gabin", "minutes": 30},
    ],
)
async def test_possible_request_accepted_at_creation(make_env, manou, data) -> None:
    env = await _env(make_env)
    data = {k: v for k, v in data.items() if v is not None}
    await env.call("demander", data, env.kid_ctx)
    assert len(env.engine.requests.visible(at(TUESDAY, 16, 30))) == 1
