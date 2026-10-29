"""Entités : statut enfant, ressources, devoirs, pause, suivi de la config."""

from __future__ import annotations

import copy
import json

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN, UnitOfTime
from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.parental_control.const import DOMAIN
from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.core.evaluator import KidStatus
from custom_components.parental_control.serialize import serialize_snapshot
from tests.fixtures import EX
from tests.ha.test_engine import LEISURE, SATURDAY, TUESDAY, TV, at, set_nintendo
from tests.ha.test_services import Env, make_env  # noqa: F401 - fixture


def entity_id(env: Env, platform: str, key: str) -> str | None:
    unique_id = f"{env.entry.entry_id}_{key}"
    return er.async_get(env.hass).async_get_entity_id(platform, DOMAIN, unique_id)


def state(env: Env, platform: str, key: str):
    eid = entity_id(env, platform, key)
    assert eid is not None, key
    return env.hass.states.get(eid)


def device(env: Env, ident: str) -> dr.DeviceEntry | None:
    return dr.async_get(env.hass).async_get_device_by_identifier(
        (DOMAIN, ident), env.entry.entry_id
    )


async def call(env: Env, domain: str, service: str, eid: str, context: Context) -> None:
    await env.hass.services.async_call(
        domain, service, {"entity_id": eid}, blocking=True, context=context
    )
    await env.hass.async_block_till_done()


async def test_kid_status_sensor_reflects_snapshot(make_env) -> None:  # noqa: F811
    env = await make_env(at(TUESDAY, 16, 30))
    assert entity_id(env, "sensor", "kid_gabin_status") == "sensor.gabin_status"
    st = state(env, "sensor", "kid_gabin_status")
    assert st.state == KidStatus.ATTENTE_DEVOIRS
    assert st.attributes["device_class"] == SensorDeviceClass.ENUM
    assert st.attributes["options"] == [s.value for s in KidStatus]
    attrs = st.attributes
    assert attrs["day_type"] == "ecole"
    assert attrs["segment"] == "apres_devoirs"
    assert attrs["segment_end"] == at(TUESDAY, 19, 0).isoformat()
    assert attrs["reason"]
    for key in ("until", "remaining_minutes", "timer_end", "closes_at"):
        assert key in attrs
    assert attrs["exceptions"] == []
    gabin = device(env, "kid_gabin")
    assert gabin is not None and gabin.name == "Gabin"

    await env.call("devoirs_termines", {"kid_id": "gabin"}, env.admin_ctx)
    # Exception sur une ressource de Gabin : listée dans ses attributs.
    await env.call("exception", {"open": False, "resource_id": "tv", "minutes": 30},
                   env.admin_ctx)
    await env.hass.async_block_till_done()
    attrs = state(env, "sensor", "kid_gabin_status").attributes
    [exc] = env.engine.decisions.exceptions
    assert attrs["exceptions"] == [{
        "id": exc.id,
        "target": {"resource_id": "tv", "kid_id": None, "service": None},
        "open": False,
        "until": exc.until.isoformat(),
    }]

    await env.call("annuler_exception", {"exception_id": exc.id}, env.admin_ctx)
    await env.hass.async_block_till_done()
    st = state(env, "sensor", "kid_gabin_status")
    assert st.state == KidStatus.AUTORISE
    assert st.attributes["closes_at"] == at(TUESDAY, 19, 0).isoformat()


async def test_resource_binary_sensor_and_durations(make_env) -> None:  # noqa: F811
    env = await make_env(at(SATURDAY, 10, 0))
    set_nintendo(env.hass, used="42", remaining="18")
    env.hass.states.async_set(TV, "on")
    await env.hass.async_block_till_done()
    await env.engine.async_evaluate("test")
    await env.hass.async_block_till_done()

    assert state(env, "binary_sensor", "resource_tv_allowed").state == STATE_ON
    adguard = state(env, "binary_sensor", "resource_iphone_gabin_allowed")
    assert adguard.state == STATE_OFF
    assert adguard.attributes["blocked_services"] == LEISURE
    assert "blocked_services" not in state(
        env, "binary_sensor", "resource_tv_allowed").attributes

    used = state(env, "sensor", "resource_switch_used_time")
    assert float(used.state) == pytest.approx(42)
    assert used.attributes["unit_of_measurement"] == UnitOfTime.MINUTES
    assert used.attributes["device_class"] == SensorDeviceClass.DURATION
    assert float(state(env, "sensor", "resource_switch_remaining_time").state) == \
        pytest.approx(18)
    assert float(state(env, "sensor", "resource_tv_remaining_time").state) == \
        pytest.approx(180)
    # AdGuard : rien à mesurer, pas d'entité de durée.
    assert entity_id(env, "sensor", "resource_iphone_gabin_used_time") is None
    assert entity_id(env, "sensor", "resource_iphone_gabin_remaining_time") is None

    tv = device(env, "resource_tv")
    assert tv is not None and tv.name == "Télé salon"


async def test_duration_none_is_unknown(make_env) -> None:  # noqa: F811
    env = await make_env(at(TUESDAY, 16, 30))  # pas de capteurs Nintendo
    assert state(env, "sensor", "resource_switch_used_time").state == STATE_UNKNOWN


async def test_button_press_non_admin_rejected(make_env) -> None:  # noqa: F811
    env = await make_env(at(TUESDAY, 16, 30))
    eid = entity_id(env, "button", "kid_gabin_homework_done")
    assert eid is not None
    with pytest.raises(ServiceValidationError) as err:
        await call(env, "button", "press", eid, env.kid_ctx)
    assert err.value.translation_key == "code_required"
    assert not env.engine.decisions.homework_done_on("gabin", TUESDAY)


async def test_button_press_admin_marks_homework(make_env) -> None:  # noqa: F811
    env = await make_env(at(TUESDAY, 16, 30))
    eid = entity_id(env, "button", "kid_gabin_homework_done")
    await call(env, "button", "press", eid, env.admin_ctx)
    assert env.engine.decisions.homework_done_on("gabin", TUESDAY)
    assert state(env, "sensor", "kid_gabin_status").state == KidStatus.AUTORISE


async def test_pause_switch_turn_off_non_admin_rejected(make_env) -> None:  # noqa: F811
    env = await make_env(at(TUESDAY, 16, 30))
    eid = entity_id(env, "switch", "global_pause")
    assert eid is not None
    assert env.hass.states.get(eid).state == STATE_OFF
    glob = device(env, "global")
    assert glob is not None and glob.name == "Contrôle parental"

    await call(env, "switch", "turn_on", eid, env.kid_ctx)  # la pause ne demande rien
    assert env.engine.decisions.paused
    assert env.hass.states.get(eid).state == STATE_ON
    assert state(env, "sensor", "kid_gabin_status").state == KidStatus.PAUSE

    with pytest.raises(ServiceValidationError) as err:
        await call(env, "switch", "turn_off", eid, env.kid_ctx)
    assert err.value.translation_key == "code_required"
    assert env.engine.decisions.paused

    await call(env, "switch", "turn_off", eid, env.admin_ctx)
    assert not env.engine.decisions.paused
    assert env.hass.states.get(eid).state == STATE_OFF


async def test_entities_follow_config_change(make_env) -> None:  # noqa: F811
    env = await make_env(at(TUESDAY, 16, 30))
    tv_keys = [("binary_sensor", "resource_tv_allowed"),
               ("sensor", "resource_tv_used_time"),
               ("sensor", "resource_tv_remaining_time")]
    tv_ids = [entity_id(env, p, k) for p, k in tv_keys]
    assert all(tv_ids)

    raw = copy.deepcopy(EX)
    raw["resources"] = [r for r in raw["resources"] if r["id"] != "tv"]
    lea = copy.deepcopy(raw["kids"][0])
    lea.update(id="lea", name="Léa", calendar=None)
    raw["kids"].append(lea)
    await env.engine.set_config(parse_config(raw))
    await env.hass.async_block_till_done()

    for (platform, key), eid in zip(tv_keys, tv_ids, strict=True):
        assert entity_id(env, platform, key) is None
        assert env.hass.states.get(eid) is None
    assert device(env, "resource_tv") is None
    assert state(env, "sensor", "kid_lea_status").state in {s.value for s in KidStatus}
    assert entity_id(env, "button", "kid_lea_homework_done") is not None
    assert device(env, "kid_lea").name == "Léa"
    assert entity_id(env, "sensor", "kid_gabin_status") is not None

    # Retour de la télé : ses entités sont recréées.
    await env.engine.set_config(parse_config(EX))
    await env.hass.async_block_till_done()
    assert all(entity_id(env, p, k) for p, k in tv_keys)
    assert entity_id(env, "sensor", "kid_lea_status") is None
    assert device(env, "kid_lea") is None


async def test_serialize_snapshot_shape(make_env) -> None:  # noqa: F811
    env = await make_env(at(TUESDAY, 16, 30))
    await env.call("exception", {"open": True, "resource_id": "tv", "minutes": 10},
                   env.admin_ctx)
    data = serialize_snapshot(env.engine)
    assert set(data) == {"kids", "resources", "closures", "paused", "exceptions"}
    gabin = data["kids"]["gabin"]
    assert gabin["status"] == "attente_devoirs"
    assert gabin["segment_end"] == at(TUESDAY, 19, 0).isoformat()
    assert "closes_at" in gabin
    assert data["resources"]["iphone_gabin"]["blocked_services"] == LEISURE
    tv = data["resources"]["tv"]
    assert tv["open"] is True
    assert data["closures"]["resource:tv"] == tv["until"]
    assert data["paused"] is False
    [exc] = data["exceptions"]
    assert exc["target"] == {"resource_id": "tv", "kid_id": None, "service": None}
    assert exc["open"] is True
    json.dumps(data)  # tout est sérialisable
