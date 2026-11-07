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

MARC = "notify.mobile_app_iphone_de_marc"
JULIE = "notify.mobile_app_iphone_de_julie"
CONFIG = {**EX, "request_notify": [MARC, JULIE]}
# Une exception par service vise une ressource AdGuard (`tv` n'est qu'un media_player).
OPEN_CALL = {
    "kind": "open",
    "kid_id": "hugo",
    "resource_id": "iphone_hugo",
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
        assert call.data["message"] == "Hugo demande 30 min de YouTube sur iPhone Hugo"
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
        "[Simulation] Hugo demande 30 min de YouTube sur iPhone Hugo"
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"kind": RequestKind.OPEN, "resource_id": "iphone_hugo", "service": "youtube",
          "proposed": 30},
         "Hugo demande 30 min de YouTube sur iPhone Hugo"),
        ({"kind": RequestKind.OPEN, "service": "youtube", "proposed": 30},
         "Hugo demande 30 min de YouTube"),
        ({"kind": RequestKind.OPEN, "resource_id": "tv", "proposed": 30},
         "Hugo demande 30 min sur Télé salon"),
        ({"kind": RequestKind.OPEN, "resource_id": "iphone_hugo", "service": "youtube",
          "proposed": None},
         "Hugo demande YouTube sur iPhone Hugo jusqu'au prochain changement"),
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


# --- réponse depuis la notification ---------------------------------------------

EVENT = "mobile_app_notification_action"


@pytest.fixture
async def julie_user(hass):
    """Parent non admin, propriétaire du téléphone « iPhone de Julie »."""
    user = await hass.auth.async_create_user("Julie", group_ids=["system-users"])
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


async def _parents_env(make_env, julie_user, moment=None, config=CONFIG, *, marc=True):
    env = await make_env(moment or at(TUESDAY, 16, 30), config)
    add_phone(env.hass, "iPhone de Julie", julie_user.id)
    if marc:
        add_phone(env.hass, "iPhone de Marc", env.admin.id)
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
    hass, make_env, julie, julie_user
) -> None:
    env = await _parents_env(make_env, julie_user)
    entries = async_capture_events(hass, "logbook_entry")
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    choice = str(req.options.index(60))
    await _answer(env, _actions(julie)[choice], julie_user.id)
    assert req.status == "accepted" and req.granted == 60
    assert req.answered_by == "Julie"
    (exc,) = env.engine.decisions.exceptions
    assert exc.open and exc.target == Target(resource_id="iphone_hugo", service="youtube")
    assert exc.until == at(TUESDAY, 17, 30)
    marc = env.services.of("notify", "mobile_app_iphone_de_marc")
    assert len(_clears(marc, req_id)) == 1 and len(_clears(julie, req_id)) == 1
    assert "Demande de Hugo acceptée par Julie : 1 h" in logbook_messages(entries)


async def test_tablet_user_cannot_answer(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    await _answer(env, _actions(julie)["0"], env.kid.id)
    assert env.engine.requests.get(req_id).status == "pending"
    assert env.engine.decisions.exceptions == []


async def test_admin_without_phone_in_list_cannot_answer(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user, marc=False)
    req_id = await _ask(env)
    await _answer(env, _actions(julie)["0"], env.admin.id)
    assert env.engine.requests.get(req_id).status == "pending"
    assert env.engine.decisions.exceptions == []


async def test_answer_without_user_ignored(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    await _answer(env, _actions(julie)["0"], None)
    assert env.engine.requests.get(req_id).status == "pending"


async def test_wrong_token_ignored(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    await _answer(env, f"PARENTAL_REQ:{req_id}:faux:0", julie_user.id)
    assert env.engine.requests.get(req_id).status == "pending"
    assert env.engine.decisions.exceptions == []


async def test_unauthorized_answer_logs_without_token(
    make_env, julie, julie_user, caplog: pytest.LogCaptureFixture
) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    await _answer(env, _actions(julie)["0"], env.kid.id)
    assert f"Réponse à la demande {req_id} ignorée" in caplog.text
    assert req.token not in caplog.text


async def test_first_answer_wins(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    actions = _actions(julie)
    await _answer(env, actions["0"], julie_user.id)
    await _answer(env, actions["refuse"], env.admin.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "accepted" and req.answered_by == "Julie"
    assert len(env.engine.decisions.exceptions) == 1


async def test_refuse(hass, make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    entries = async_capture_events(hass, "logbook_entry")
    req_id = await _ask(env)
    await _answer(env, _actions(julie)["refuse"], julie_user.id)
    assert env.engine.requests.get(req_id).status == "refused"
    assert env.engine.decisions.exceptions == []
    assert "Demande de Hugo refusée par Julie" in logbook_messages(entries)
    assert len(_clears(julie, req_id)) == 1


async def test_accept_until_change(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    await _answer(env, _actions(julie)[str(req.options.index(None))], julie_user.id)
    assert req.status == "accepted" and req.granted is None
    (exc,) = env.engine.decisions.exceptions
    assert exc.open and exc.until is None and exc.signature is not None


async def test_accept_replaces_listed_exceptions(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    closing = await env.engine.add_exception(
        Target(resource_id="iphone_hugo", service="youtube"), False, 30
    )
    await _ask(env, {**OPEN_CALL, "replace": [closing, "absente"]})
    await _answer(env, _actions(julie)["0"], julie_user.id)
    (exc,) = env.engine.decisions.exceptions
    assert exc.id != closing and exc.open


async def test_accept_keeps_listed_exception_of_other_target(
    make_env, julie, julie_user
) -> None:
    """`replace` vient de la tablette : une fermeture d'une autre cible n'est jamais
    annulée par l'acceptation (il faudrait le code parent)."""
    env = await _parents_env(make_env, julie_user)
    same = await env.engine.add_exception(
        Target(resource_id="iphone_hugo", service="youtube"), False, 30
    )
    other_resource = await env.engine.add_exception(Target(resource_id="tv"), False, 60)
    other_service = await env.engine.add_exception(
        Target(resource_id="iphone_hugo", service="roblox"), False, 60
    )
    kid_wide = await env.engine.add_exception(
        Target(kid_id="hugo", service="youtube"), False, 60
    )
    await _ask(env, {**OPEN_CALL, "replace": [same, other_resource, other_service, kid_wide]})
    await _answer(env, _actions(julie)["0"], julie_user.id)
    ids = {e.id for e in env.engine.decisions.exceptions}
    assert same not in ids
    assert {other_resource, other_service, kid_wide} <= ids


async def test_accept_with_invalid_target_cancels_nothing(make_env, julie, julie_user) -> None:
    """La cible n'est plus valide (config changée) : la demande échoue sans retirer la
    fermeture listée dans `replace`."""
    env = await _parents_env(make_env, julie_user)
    closing = await env.engine.add_exception(
        Target(resource_id="iphone_hugo", service="youtube"), False, 30
    )
    req_id = await _ask(env, {**OPEN_CALL, "replace": [closing]})
    cfg = copy.deepcopy(CONFIG)
    (iphone,) = [r for r in cfg["resources"] if r["id"] == "iphone_hugo"]
    iphone.clear()
    iphone.update(
        id="iphone_hugo", name="iPhone Hugo", owners=["hugo"],
        devices=[{"name": "iPhone Hugo", "integrations": [
            {"kind": "media_player", "entity_id": "media_player.iphone_hugo",
             "notify_service": None}]}],
    )
    await env.engine.set_config(parse_config(cfg))
    assert any(e.id == closing for e in env.engine.decisions.exceptions)
    await _answer(env, _actions(julie)["0"], julie_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "failed" and req.reason
    assert [e.id for e in env.engine.decisions.exceptions] == [closing]


async def test_accept_bonus_on_switch_resource(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user, at(SATURDAY, 10, 0))
    set_nintendo(env.hass)
    req_id = await _ask(
        env, {"kind": "bonus", "kid_id": "hugo", "resource_id": "switch", "minutes": 30}
    )
    await _answer(env, _actions(julie)["0"], julie_user.id)
    assert env.engine.requests.get(req_id).status == "accepted"
    assert [c.data for c in env.services.of("nintendo_parental_controls", "add_bonus_time")] == [
        {"device_id": "c52a9e7f10b84d3698e1f4a7d3b60c28", "bonus_time": 30}
    ]


async def test_accept_bonus_on_kid(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user, at(SATURDAY, 10, 0))
    await _ask(env, {"kind": "bonus", "kid_id": "hugo", "minutes": 20})
    await _answer(env, _actions(julie)["0"], julie_user.id)
    assert env.engine.decisions.bonus_minutes(SATURDAY, kid_id="hugo") == 20


async def test_accept_timer(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user, at(SATURDAY, 10, 0))
    req_id = await _ask(env, {"kind": "timer", "kid_id": "hugo", "minutes": 30})
    await _answer(env, _actions(julie)["0"], julie_user.id)
    assert env.engine.requests.get(req_id).status == "accepted"
    timer = env.engine.decisions.active_timer("hugo", at(SATURDAY, 10, 0))
    assert timer is not None and timer.end == at(SATURDAY, 10, 30)


async def test_accept_homework(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env, {"kind": "homework", "kid_id": "hugo"})
    await _answer(env, _actions(julie)["accept"], julie_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "accepted" and req.granted is None
    assert env.engine.decisions.homework_done_on("hugo", TUESDAY)


async def test_unknown_choice_marks_failed(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    base = _actions(julie)["0"].rsplit(":", 1)[0]
    await _answer(env, f"{base}:accept", julie_user.id)  # « accept » : devoirs seulement
    assert req.status == "failed" and req.reason == "Choix inconnu"
    assert env.engine.decisions.exceptions == []
    assert len(_clears(julie, req_id)) == 1


async def test_accept_impossible_marks_failed(
    hass, freezer, make_env, julie, julie_user
) -> None:
    env = await _parents_env(make_env, julie_user, at(SATURDAY, 19, 55))
    entries = async_capture_events(hass, "logbook_entry")
    req_id = await _ask(env, {"kind": "timer", "kid_id": "hugo", "minutes": 30})
    await tick(hass, freezer, 6)  # 20:01 : hors de la plage quota
    await _answer(env, _actions(julie)["0"], julie_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "failed" and req.reason
    assert env.engine.decisions.timers == []
    assert any(
        m.startswith("Demande de Hugo acceptée par Julie, mais impossible : ")
        for m in logbook_messages(entries)
    )


async def test_non_mobile_app_target_ignored(make_env, julie, julie_user) -> None:
    config = {**CONFIG, "request_notify": [*CONFIG["request_notify"], "notify.persistent_notification"]}
    env = await _parents_env(make_env, julie_user, config=config)
    assert parent_user_ids(env.hass, config["request_notify"]) == {
        julie_user.id, env.admin.id
    }
    req_id = await _ask(env)
    await _answer(env, _actions(julie)["0"], julie_user.id)
    assert env.engine.requests.get(req_id).status == "accepted"


async def test_answer_after_config_removed_kid(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env, {"kind": "homework", "kid_id": "hugo"})
    cfg = copy.deepcopy(CONFIG)
    cfg["kids"][0].update(id="lea", name="Léa")
    for resource in cfg["resources"]:
        resource["owners"] = ["lea"]
    cfg["kids"][0]["resource_modes"] = {}
    await env.engine.set_config(parse_config(cfg))
    await _answer(env, _actions(julie)["accept"], julie_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "failed" and req.reason


async def test_late_answer_after_expiry_ignored(
    hass, freezer, make_env, julie, julie_user
) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    await tick(hass, freezer, 15)
    await _answer(env, _actions(julie)["0"], julie_user.id)
    assert env.engine.requests.get(req_id).status == "expired"
    assert env.engine.decisions.exceptions == []


async def test_unexpected_error_still_finishes_request(make_env, julie, julie_user) -> None:
    """Une erreur imprévue ne laisse jamais la demande réservée (statut provisoire)."""
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    _, token, _ = parse_action(_actions(julie)["0"])

    async def boom(*_args, **_kwargs):
        raise RuntimeError("panne")

    env.engine.add_exception = boom
    with pytest.raises(RuntimeError):
        await env.engine.answer_request(req_id, token, "0", julie_user.id)
    req = env.engine.requests.get(req_id)
    assert req.status == "failed" and req.resolved_at is not None
    await env.hass.async_block_till_done()
    assert len(_clears(julie, req_id)) == 1


async def test_duplicate_device_name_trusted_for_nobody(
    make_env, julie, julie_user, caplog: pytest.LogCaptureFixture
) -> None:
    """La tablette enregistre un appareil au même nom que celui de Julie : ni l'une ni
    l'autre ne peut répondre par ce service."""
    env = await _parents_env(make_env, julie_user, marc=False)
    add_phone(env.hass, "iPhone de Julie", env.kid.id)
    assert parent_user_ids(env.hass, CONFIG["request_notify"]) == set()
    assert "mobile_app_iphone_de_julie" in caplog.text and "plusieurs" in caplog.text
    req_id = await _ask(env)
    req = env.engine.requests.get(req_id)
    for user_id in (env.kid.id, julie_user.id):
        await _answer(env, _actions(julie)["0"], user_id)
        assert req.status == "pending"
    assert req.token not in caplog.text


async def test_duplicate_device_name_keeps_other_phones(make_env, julie, julie_user) -> None:
    env = await _parents_env(make_env, julie_user)
    add_phone(env.hass, "iPhone de Julie", env.kid.id)
    assert parent_user_ids(env.hass, CONFIG["request_notify"]) == {env.admin.id}


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({**OPEN_CALL, "resource_id": "tv"}, "invalid_target"),  # pas d'AdGuard sur la télé
        ({"kind": "open", "kid_id": "hugo", "minutes": 30}, "invalid_target"),
        ({"kind": "open", "kid_id": "hugo", "resource_id": "switch", "minutes": 30},
         "nintendo_use_bonus"),
        ({"kind": "bonus", "kid_id": "hugo", "resource_id": "iphone_hugo", "minutes": 30},
         "invalid_target"),
        ({"kind": "timer", "kid_id": "hugo", "resource_id": "tv", "minutes": 30},
         "invalid_request"),
        ({"kind": "homework", "kid_id": "hugo", "resource_id": "tv"}, "invalid_request"),
    ],
)
async def test_impossible_request_rejected_at_creation(make_env, julie, data, key) -> None:
    env = await _env(make_env)
    data = {k: v for k, v in data.items() if v is not None}
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", data, env.kid_ctx)
    assert err.value.translation_key == key
    assert env.engine.requests.visible(at(TUESDAY, 16, 30)) == []
    assert julie == []


@pytest.mark.parametrize(
    "data",
    [
        {**OPEN_CALL, "service": "Donne-moi tout"},  # texte libre, pas un service
        {**OPEN_CALL, "resource_id": None, "service": "steam"},  # hors des loisirs de l'enfant
    ],
)
async def test_request_service_outside_target_rejected(make_env, julie, data) -> None:
    env = await _env(make_env)
    data = {k: v for k, v in data.items() if v is not None}
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", data, env.kid_ctx)
    assert err.value.translation_key == "invalid_target"
    assert julie == []


async def test_request_on_demand_service_accepted(make_env, julie) -> None:
    cfg = {**CONFIG, "default_on_demand": ["steam"]}
    env = await _env(make_env, cfg)
    await env.call("demander", {**OPEN_CALL, "service": "steam"}, env.kid_ctx)
    kid_wide = {k: v for k, v in OPEN_CALL.items() if k != "resource_id"}
    await env.call("demander", {**kid_wide, "service": "steam"}, env.kid_ctx)
    assert len(env.engine.requests.visible(at(TUESDAY, 16, 30))) == 2


async def test_too_many_pending_requests_rejected(make_env, julie) -> None:
    env = await _env(make_env)
    for service in ("youtube", "roblox", "tiktok"):
        await env.call("demander", {**OPEN_CALL, "service": service}, env.kid_ctx)
    with pytest.raises(ServiceValidationError) as err:
        await env.call("demander", {**OPEN_CALL, "service": "netflix"}, env.kid_ctx)
    assert err.value.translation_key == "too_many_requests"
    assert len(env.engine.requests.visible(at(TUESDAY, 16, 30))) == 3


@pytest.mark.parametrize(
    "data",
    [
        {**OPEN_CALL, "resource_id": None},  # service pour tous les appareils de l'enfant
        {"kind": "open", "kid_id": "hugo", "resource_id": "tv", "minutes": 30},
        {"kind": "bonus", "kid_id": "hugo", "resource_id": "tv", "minutes": 30},
        {"kind": "bonus", "kid_id": "hugo", "resource_id": "switch", "minutes": 30},
        {"kind": "bonus", "kid_id": "hugo", "minutes": 30},
    ],
)
async def test_possible_request_accepted_at_creation(make_env, julie, data) -> None:
    env = await _env(make_env)
    data = {k: v for k, v in data.items() if v is not None}
    await env.call("demander", data, env.kid_ctx)
    assert len(env.engine.requests.visible(at(TUESDAY, 16, 30))) == 1


# --- écran « Demandes » (WebSocket) ----------------------------------------------

# Avertissement tiers du composant `http` de HA (requis par websocket_api), fatal sous `-W error`.
_ws = pytest.mark.filterwarnings(
    "ignore:It is recommended to use web:aiohttp.web_exceptions.NotAppKeyWarning"
)


async def _ws_client(hass, hass_ws_client, user):
    token = await hass.auth.async_create_refresh_token(user, "https://example.com")
    return await hass_ws_client(hass, hass.auth.async_create_access_token(token))


async def _ws_answer(client, request_id: str, choice: str) -> dict:
    await client.send_json_auto_id(
        {"type": "parental_control/requests/answer", "request_id": request_id, "choice": choice}
    )
    return await client.receive_json()


async def test_notification_opens_requests_screen(make_env, julie) -> None:
    env = await _env(make_env)
    await _ask(env)
    data = julie[-1].data["data"]
    assert data["url"] == "/parental-control-requests"
    assert data["clickAction"] == "/parental-control-requests"


@_ws
async def test_requests_screen_lists_choices_without_token(
    make_env, julie, julie_user, catalog, hass_ws_client
) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    token = env.engine.requests.get(req_id).token
    for user, can_answer in ((julie_user, True), (env.kid, False)):
        client = await _ws_client(env.hass, hass_ws_client, user)
        await client.send_json_auto_id({"type": "parental_control/requests/subscribe"})
        assert (await client.receive_json())["success"]
        event = (await client.receive_json())["event"]
        assert token not in json.dumps(event)
        assert event["can_answer"] is can_answer
        (req,) = event["requests"]
        assert req["id"] == req_id and req["status"] == "pending"
        assert req["message"] == "Hugo demande 30 min de YouTube sur iPhone Hugo"
        assert req["choices"][0] == ["0", "Accepter 30 min"]
        assert req["choices"][-1] == ["refuse", "Refuser"]


@_ws
async def test_requests_screen_parent_non_admin_answers(
    make_env, julie, julie_user, hass_ws_client
) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    client = await _ws_client(env.hass, hass_ws_client, julie_user)
    resp = await _ws_answer(client, req_id, "0")
    assert resp["success"] and resp["result"] == {"status": "accepted"}
    req = env.engine.requests.get(req_id)
    assert req.granted == 30 and req.answered_by == "Julie"
    await env.hass.async_block_till_done()
    assert len(_clears(julie, req_id)) == 1
    # Première réponse seulement : une seconde est refusée sans effet.
    resp = await _ws_answer(client, req_id, "refuse")
    assert resp["error"]["code"] == "not_pending"
    assert env.engine.requests.get(req_id).status == "accepted"


@_ws
async def test_requests_screen_refuses_non_parents(
    make_env, julie, julie_user, hass_ws_client
) -> None:
    # Marc est admin mais n'a pas de téléphone : il ne peut pas répondre, la tablette non plus.
    env = await _parents_env(make_env, julie_user, marc=False)
    req_id = await _ask(env)
    for user in (env.kid, env.admin):
        client = await _ws_client(env.hass, hass_ws_client, user)
        resp = await _ws_answer(client, req_id, "0")
        assert resp["error"]["code"] == "unauthorized"
    assert env.engine.requests.get(req_id).status == "pending"


@_ws
async def test_requests_screen_unknown_choice_keeps_request(
    make_env, julie, julie_user, hass_ws_client
) -> None:
    env = await _parents_env(make_env, julie_user)
    req_id = await _ask(env)
    client = await _ws_client(env.hass, hass_ws_client, julie_user)
    resp = await _ws_answer(client, req_id, "9")
    assert resp["error"]["code"] == "invalid_choice"
    assert env.engine.requests.get(req_id).status == "pending"
    resp = await _ws_answer(client, "inconnue", "0")
    assert resp["error"]["code"] == "not_pending"
