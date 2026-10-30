"""Adaptateurs TV (media_player) et AdGuard."""

import logging

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.parental_control.adapters import build_adapter
from custom_components.parental_control.adapters.adguard import AdGuardAdapter
from custom_components.parental_control.adapters.media_player import (
    MediaPlayerAdapter,
)
from custom_components.parental_control.core.evaluator import ResourceState
from custom_components.parental_control.core.model import Resource, ResourceKind
from tests.ha.fake_adguard import FakeAdGuard

TV_ENTITY = "media_player.tv_salon"
LEISURE = frozenset({"youtube", "roblox"})


def state(open_: bool, blocked: frozenset[str] = frozenset()) -> ResourceState:
    return ResourceState(
        open=open_,
        reason="test",
        until=None,
        used_minutes=None,
        remaining_minutes=None,
        blocked_services=blocked,
    )


CLOSED = state(False)
OPEN = state(True)


def tv_resource(notify_service: str | None = None) -> Resource:
    return Resource(
        id="tv",
        name="Télé salon",
        kind=ResourceKind.MEDIA_PLAYER,
        owners=("gabin",),
        options={"entity_id": TV_ENTITY, "notify_service": notify_service},
    )


def adguard_resource(device_id: str = "adguard_iphone_gabin") -> Resource:
    return Resource(
        id="iphone_gabin",
        name="iPhone Gabin",
        kind=ResourceKind.ADGUARD,
        owners=("gabin",),
        options={"device_id": device_id},
    )


def called_entities(calls) -> list[str]:
    return sorted(c.data["entity_id"] for c in calls)


# --- build_adapter -------------------------------------------------------------


async def test_build_adapter_by_kind(hass: HomeAssistant) -> None:
    tv = build_adapter(hass, tv_resource(), LEISURE)
    ag = build_adapter(hass, adguard_resource(), LEISURE)
    assert isinstance(tv, MediaPlayerAdapter)
    assert isinstance(ag, AdGuardAdapter)
    assert tv.resource.id == "tv"
    assert tv.entity_ids() == [TV_ENTITY]
    assert ag.entity_ids() == []  # appareil inconnu du registre
    with pytest.raises(NotImplementedError):
        await tv.grant(10)
    with pytest.raises(NotImplementedError):
        await ag.grant(10)


# --- media_player --------------------------------------------------------------


@pytest.mark.parametrize("tv_state", ["on", "playing", "paused", "idle", "buffering"])
async def test_media_player_turn_off_when_closed_and_on(
    hass: HomeAssistant, tv_state: str
) -> None:
    hass.states.async_set(TV_ENTITY, tv_state)
    calls = async_mock_service(hass, "media_player", "turn_off")
    adapter = build_adapter(hass, tv_resource(), LEISURE)

    assert adapter.in_use()
    assert adapter.drifted(CLOSED)
    assert not adapter.drifted(OPEN)
    await adapter.apply(CLOSED)

    assert len(calls) == 1
    assert calls[0].data == {"entity_id": TV_ENTITY}


@pytest.mark.parametrize("tv_state", ["unavailable", "unknown", "off", "standby", None])
async def test_media_player_unavailable_is_not_in_use(
    hass: HomeAssistant, tv_state: str | None
) -> None:
    if tv_state is not None:
        hass.states.async_set(TV_ENTITY, tv_state)
    calls = async_mock_service(hass, "media_player", "turn_off")
    adapter = build_adapter(hass, tv_resource(), LEISURE)

    assert not adapter.in_use()
    await adapter.apply(CLOSED)
    assert calls == []
    assert not adapter.drifted(CLOSED)


async def test_media_player_open_does_nothing(hass: HomeAssistant) -> None:
    hass.states.async_set(TV_ENTITY, "playing")
    calls = async_mock_service(hass, "media_player", "turn_off")
    await build_adapter(hass, tv_resource(), LEISURE).apply(OPEN)
    assert calls == []


async def test_media_player_force_close(hass: HomeAssistant) -> None:
    hass.states.async_set(TV_ENTITY, "on")
    calls = async_mock_service(hass, "media_player", "turn_off")
    await build_adapter(hass, tv_resource(), LEISURE).force_close()
    assert called_entities(calls) == [TV_ENTITY]


async def test_media_player_warn_uses_notify_service(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "tv_salon")
    adapter = build_adapter(hass, tv_resource("notify.tv_salon"), LEISURE)
    await adapter.warn("Télé salon : coupure dans 5 min")
    assert len(calls) == 1
    assert calls[0].data == {"message": "Télé salon : coupure dans 5 min"}


async def test_media_player_warn_without_notify_service(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "tv_salon")
    await build_adapter(hass, tv_resource(None), LEISURE).warn("x")
    assert calls == []


# --- adguard -------------------------------------------------------------------


@pytest.fixture
def fake(hass: HomeAssistant) -> FakeAdGuard:
    return FakeAdGuard(hass)


def adguard(hass: HomeAssistant, fake: FakeAdGuard) -> AdGuardAdapter:
    return build_adapter(hass, adguard_resource(fake.device_id), LEISURE)


async def test_adguard_watches_device_sensor(hass: HomeAssistant, fake) -> None:
    assert adguard(hass, fake).entity_ids() == [fake.entity_id]


async def test_adguard_blocks_only_leisure_services(hass: HomeAssistant, fake) -> None:
    fake.set_blocked(["khanacademy"])
    adapter = adguard(hass, fake)

    desired = state(False, LEISURE)
    assert adapter.drifted(desired)
    await adapter.apply(desired)

    assert [c.data for c in fake.calls] == [
        {"device_id": fake.device_id, "block": ["roblox", "youtube"], "unblock": []}
    ]
    assert fake.blocked == ["khanacademy", "roblox", "youtube"]
    assert not adapter.drifted(desired)
    assert not adapter.in_use()


async def test_adguard_unblocks_when_open(hass: HomeAssistant, fake) -> None:
    fake.set_blocked(["youtube", "roblox", "khanacademy"])
    adapter = adguard(hass, fake)

    await adapter.apply(OPEN)

    assert fake.unblocks() == ["roblox", "youtube"]
    assert fake.blocks() == []
    assert fake.blocked == ["khanacademy"]
    assert not adapter.drifted(OPEN)


async def test_adguard_service_exception_partial(hass: HomeAssistant, fake) -> None:
    """Ouvert avec un service bloqué par exception, hors loisirs compris."""
    fake.set_blocked(["roblox"])
    adapter = adguard(hass, fake)

    desired = state(True, frozenset({"youtube", "tiktok"}))
    assert adapter.drifted(desired)
    await adapter.apply(desired)

    assert len(fake.calls) == 1
    assert fake.blocks() == ["tiktok", "youtube"]
    assert fake.unblocks() == ["roblox"]


async def test_adguard_no_call_when_already_in_state(hass: HomeAssistant, fake) -> None:
    fake.set_blocked(["youtube", "roblox"])
    adapter = adguard(hass, fake)

    desired = state(False, LEISURE)
    assert not adapter.drifted(desired)
    await adapter.apply(desired)
    assert fake.calls == []


@pytest.mark.parametrize("value", ["unavailable", "unknown"])
async def test_adguard_unreadable_sensor_is_left_alone(
    hass: HomeAssistant, fake, value
) -> None:
    hass.states.async_set(fake.entity_id, value, {"services": []})
    adapter = adguard(hass, fake)

    desired = state(False, LEISURE)
    assert not adapter.drifted(desired)
    await adapter.apply(desired)
    assert fake.calls == []


async def test_adguard_missing_sensor_logs_once(
    hass: HomeAssistant, fake, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = adguard(hass, fake)  # capteur enregistré, sans état
    desired = state(False, LEISURE)

    with caplog.at_level(logging.WARNING):
        await adapter.apply(desired)
        await adapter.apply(desired)

    assert fake.calls == []
    warnings = [r for r in caplog.records if "introuvable" in r.getMessage()]
    assert len(warnings) == 1


async def test_adguard_unknown_device_has_no_entities(hass: HomeAssistant, fake) -> None:
    adapter = build_adapter(hass, adguard_resource("inconnu"), LEISURE)
    assert adapter.entity_ids() == []
    assert not adapter.drifted(state(False, LEISURE))
    await adapter.apply(state(False, LEISURE))
    assert fake.calls == []


async def test_adguard_global_blocked_services_warns_once(
    hass: HomeAssistant, fake, caplog: pytest.LogCaptureFixture
) -> None:
    """Liste du client ignorée par AdGuard : on écrit quand même, on prévient."""
    fake.use_global = True
    fake.set_blocked([])
    adapter = adguard(hass, fake)

    with caplog.at_level(logging.WARNING):
        await adapter.apply(state(False, LEISURE))
        await adapter.apply(OPEN)

    assert fake.blocks() == ["roblox", "youtube"]
    warnings = [r for r in caplog.records if "globaux" in r.getMessage()]
    assert len(warnings) == 1


async def test_adguard_warn_does_nothing(hass: HomeAssistant, fake) -> None:
    fake.set_blocked([])
    await adguard(hass, fake).warn("x")
    assert fake.calls == []


async def test_adguard_lifts_non_leisure_block_after_exception_expires(
    hass: HomeAssistant, fake
) -> None:
    """Un service hors loisirs bloqué par exception est débloqué quand elle échoit."""
    fake.set_blocked([])
    adapter = adguard(hass, fake)

    await adapter.apply(state(True, frozenset({"tiktok"})))
    assert fake.blocked == ["tiktok"]

    # L'exception échoit : tiktok sort de blocked_services.
    await adapter.apply(OPEN)
    assert fake.unblocks() == ["tiktok"]
    assert fake.blocked == []

    # Une fois débloqué, il n'est plus géré.
    fake.set_blocked(["tiktok"])
    await adapter.apply(OPEN)
    assert fake.unblocks() == ["tiktok"]


async def test_adguard_manually_unblocked_extra_is_forgotten(
    hass: HomeAssistant, fake
) -> None:
    fake.set_blocked([])
    adapter = adguard(hass, fake)
    await adapter.apply(state(True, frozenset({"tiktok"})))
    fake.set_blocked([])  # débloqué à la main avant l'échéance

    await adapter.apply(OPEN)
    fake.set_blocked(["tiktok"])  # rebloqué ailleurs : plus géré
    await adapter.apply(OPEN)
    assert fake.unblocks() == []


async def test_adguard_failed_write_logs_and_retries(
    hass: HomeAssistant, fake, caplog: pytest.LogCaptureFixture
) -> None:
    fake.set_blocked([])
    fake.error = HomeAssistantError("AdGuard injoignable")
    adapter = adguard(hass, fake)

    with caplog.at_level(logging.WARNING):
        await adapter.apply(state(True, frozenset({"tiktok"})))
    assert any(
        "injoignable" in r.getMessage() and r.levelno == logging.WARNING
        for r in caplog.records
    )

    fake.error = None
    await adapter.apply(state(True, frozenset({"tiktok"})))
    await adapter.apply(OPEN)
    assert fake.unblocks() == ["tiktok"]


async def test_adguard_force_close_blocks_leisure(hass: HomeAssistant, fake) -> None:
    fake.set_blocked([])
    await adguard(hass, fake).force_close()
    assert fake.blocked == ["roblox", "youtube"]


async def test_media_player_failed_call_logs(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    hass.states.async_set(TV_ENTITY, "on")

    async def turn_off(call: ServiceCall) -> None:
        raise HomeAssistantError("TV injoignable")

    hass.services.async_register("media_player", "turn_off", turn_off)
    with caplog.at_level(logging.WARNING):
        await build_adapter(hass, tv_resource(), LEISURE).apply(CLOSED)
    assert any(TV_ENTITY in r.getMessage() for r in caplog.records)


async def test_media_player_missing_entity_warns_once(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = build_adapter(hass, tv_resource(), LEISURE)
    with caplog.at_level(logging.WARNING):
        assert not adapter.in_use()
        await adapter.apply(CLOSED)
        assert not adapter.drifted(CLOSED)
    warnings = [r for r in caplog.records if TV_ENTITY in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING


# --- Nintendo ---------------------------------------------------------------

from unittest.mock import AsyncMock, patch  # noqa: E402

from custom_components.parental_control.adapters.nintendo import (  # noqa: E402
    NintendoAdapter,
)

LIMIT = "number.switch_limit"
REMAINING = "sensor.switch_remaining"
USED = "sensor.switch_used"


def switch_resource() -> Resource:
    return Resource(
        id="switch",
        name="Switch",
        kind=ResourceKind.NINTENDO,
        owners=("gabin",),
        options={
            "device_id": "dev123",
            "limit_entity": LIMIT,
            "remaining_entity": REMAINING,
            "used_entity": USED,
        },
    )


def nintendo(hass: HomeAssistant, delay: float = 0) -> NintendoAdapter:
    adapter = build_adapter(hass, switch_resource(), LEISURE)
    assert isinstance(adapter, NintendoAdapter)
    adapter._slice_delay = delay
    return adapter


async def test_nintendo_entity_ids(hass: HomeAssistant) -> None:
    assert nintendo(hass).entity_ids() == [LIMIT, REMAINING, USED]


async def test_nintendo_grant_slices_30_min(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "nintendo_parental_controls", "add_bonus_time")
    await nintendo(hass).grant(45)
    assert [c.data for c in calls] == [
        {"device_id": "dev123", "bonus_time": 30},
        {"device_id": "dev123", "bonus_time": 15},
    ]


async def test_nintendo_grant_waits_between_slices(hass: HomeAssistant) -> None:
    async_mock_service(hass, "nintendo_parental_controls", "add_bonus_time")
    adapter = build_adapter(hass, switch_resource(), LEISURE)
    with patch(
        "custom_components.parental_control.adapters.nintendo.asyncio.sleep",
        new=AsyncMock(),
    ) as sleep:
        await adapter.grant(75)
    assert [c.args[0] for c in sleep.await_args_list] == [5, 5]


async def test_nintendo_grant_single_slice_no_wait(hass: HomeAssistant) -> None:
    async_mock_service(hass, "nintendo_parental_controls", "add_bonus_time")
    with patch(
        "custom_components.parental_control.adapters.nintendo.asyncio.sleep",
        new=AsyncMock(),
    ) as sleep:
        await build_adapter(hass, switch_resource(), LEISURE).grant(20)
    sleep.assert_not_awaited()


async def test_nintendo_retries_once_on_error(hass: HomeAssistant) -> None:
    attempts: list[int] = []

    async def flaky(call: ServiceCall) -> None:
        attempts.append(call.data["bonus_time"])
        if len(attempts) == 1:
            raise HomeAssistantError("boom")

    hass.services.async_register(
        "nintendo_parental_controls", "add_bonus_time", flaky
    )
    await nintendo(hass).grant(30)
    assert attempts == [30, 30]


async def test_nintendo_error_after_retry_propagates(hass: HomeAssistant) -> None:
    attempts: list[int] = []

    async def failing(call: ServiceCall) -> None:
        attempts.append(call.data["bonus_time"])
        raise HomeAssistantError("boom")

    hass.services.async_register(
        "nintendo_parental_controls", "add_bonus_time", failing
    )
    with pytest.raises(HomeAssistantError):
        await nintendo(hass).grant(45)
    assert attempts == [30, 30]


async def test_nintendo_apply_leaves_zero_limit_alone(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "number", "set_value")
    bonus = async_mock_service(hass, "nintendo_parental_controls", "add_bonus_time")
    adapter = nintendo(hass)
    assert adapter.drifted(CLOSED) is False  # entité absente
    hass.states.async_set(LIMIT, "0")
    for state in (CLOSED, OPEN):
        assert adapter.drifted(state) is False
        await adapter.apply(state)
    await adapter.warn("msg")
    assert not calls and not bonus
    assert adapter.in_use() is False


@pytest.mark.parametrize("value", ["unavailable", "unknown", "abc"])
async def test_nintendo_unreadable_limit_is_not_drift(hass: HomeAssistant, value) -> None:
    hass.states.async_set(LIMIT, value)
    assert nintendo(hass).drifted(OPEN) is False


async def test_nintendo_raised_limit_is_drift_and_reset(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "number", "set_value")
    adapter = nintendo(hass)
    hass.states.async_set(LIMIT, "60")
    assert adapter.drifted(OPEN) is True
    assert adapter.drifted(CLOSED) is True
    await adapter.apply(OPEN)
    assert [c.data for c in calls] == [{"entity_id": LIMIT, "value": 0}]


async def test_nintendo_force_close_sets_limit_zero(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "number", "set_value")
    await nintendo(hass).force_close()
    assert [c.data for c in calls] == [{"entity_id": LIMIT, "value": 0}]


async def test_nintendo_minutes(hass: HomeAssistant, caplog) -> None:
    adapter = nintendo(hass)
    hass.states.async_set(USED, "12.5")
    hass.states.async_set(REMAINING, "unavailable")
    assert adapter.used_minutes() == 12.5
    assert adapter.remaining_minutes() is None
    hass.states.async_set(REMAINING, "abc")
    assert adapter.remaining_minutes() is None
    hass.states.async_set(REMAINING, "unknown")
    assert adapter.remaining_minutes() is None
    hass.states.async_set(REMAINING, "7")
    assert adapter.remaining_minutes() == 7.0
    hass.states.async_remove(USED)
    with caplog.at_level(logging.WARNING):
        assert adapter.used_minutes() is None
        assert adapter.used_minutes() is None
    assert caplog.text.count(USED) == 1
