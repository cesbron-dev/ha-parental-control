"""Adaptateurs TV (media_player) et AdGuard."""

import logging

import pytest
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.parental_control.adapters import build_adapter
from custom_components.parental_control.adapters.adguard import AdGuardAdapter
from custom_components.parental_control.adapters.composite import CompositeAdapter
from custom_components.parental_control.adapters.media_player import (
    MediaPlayerAdapter,
)
from custom_components.parental_control.core.evaluator import ResourceState
from custom_components.parental_control.core.model import (
    Integration,
    PhysicalDevice,
    Resource,
    ResourceKind,
)
from tests.ha.fake_adguard import FakeAdGuard

TV_ENTITY = "media_player.tv_salon"
TV_LABEL = f"Télé salon ({TV_ENTITY})"
LEISURE = frozenset({"youtube", "roblox"})


def ident(ids) -> frozenset[str]:
    """Traduction identité : le service du parent porte le même identifiant AdGuard."""
    return frozenset(ids)



def state(open_: bool, blocked: frozenset[str] = frozenset(),
          opened: frozenset[str] = frozenset()) -> ResourceState:
    return ResourceState(
        open=open_,
        reason="test",
        until=None,
        used_minutes=None,
        remaining_minutes=None,
        blocked_services=blocked,
        opened_services=opened,
    )


CLOSED = state(False)
OPEN = state(True)


def tv_resource(notify_service: str | None = None) -> Resource:
    return Resource(
        id="tv",
        name="Télé salon",
        owners=("hugo",),
        devices=(PhysicalDevice("Télé salon", (Integration(
            ResourceKind.MEDIA_PLAYER, {"entity_id": TV_ENTITY, "notify_service": notify_service}
        ),)),),
    )


def adguard_resource(device_id: str = "adguard_iphone_hugo") -> Resource:
    return Resource(
        id="iphone_hugo",
        name="iPhone Hugo",
        owners=("hugo",),
        devices=(PhysicalDevice("iPhone Hugo", (
            Integration(ResourceKind.ADGUARD, {"device_id": device_id}),
        )),),
    )


def tv_adapter(hass: HomeAssistant, notify_service: str | None = None) -> MediaPlayerAdapter:
    return MediaPlayerAdapter(
        hass, TV_LABEL, {"entity_id": TV_ENTITY, "notify_service": notify_service}
    )


def called_entities(calls) -> list[str]:
    return sorted(c.data["entity_id"] for c in calls)


# --- build_adapter -------------------------------------------------------------


async def test_build_adapter_is_composite(hass: HomeAssistant) -> None:
    tv = build_adapter(hass, tv_resource(), LEISURE, ident)
    ag = build_adapter(hass, adguard_resource(), LEISURE, ident)
    assert isinstance(tv, CompositeAdapter)
    assert isinstance(ag, CompositeAdapter)
    assert [type(m) for m in tv.members] == [MediaPlayerAdapter]
    assert [type(m) for m in ag.members] == [AdGuardAdapter]
    assert tv.resource.id == "tv"
    assert tv.members[0].label == TV_LABEL
    assert ag.members[0].label == "iPhone Hugo"
    assert tv.entity_ids() == [TV_ENTITY]
    assert ag.entity_ids() == []  # appareil inconnu du registre
    assert tv.nintendo is None
    with pytest.raises(NotImplementedError):
        await tv.grant(10)
    with pytest.raises(NotImplementedError):
        await ag.grant(10)
    assert tv.describe_grant(10) == []


# --- media_player --------------------------------------------------------------


@pytest.mark.parametrize("tv_state", ["on", "playing", "paused", "idle", "buffering"])
async def test_media_player_turn_off_when_closed_and_on(
    hass: HomeAssistant, tv_state: str
) -> None:
    hass.states.async_set(TV_ENTITY, tv_state)
    calls = async_mock_service(hass, "media_player", "turn_off")
    adapter = tv_adapter(hass)

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
    adapter = tv_adapter(hass)

    assert not adapter.in_use()
    await adapter.apply(CLOSED)
    assert calls == []
    assert not adapter.drifted(CLOSED)


async def test_media_player_open_does_nothing(hass: HomeAssistant) -> None:
    hass.states.async_set(TV_ENTITY, "playing")
    calls = async_mock_service(hass, "media_player", "turn_off")
    await tv_adapter(hass).apply(OPEN)
    assert calls == []


async def test_media_player_force_close(hass: HomeAssistant) -> None:
    hass.states.async_set(TV_ENTITY, "on")
    calls = async_mock_service(hass, "media_player", "turn_off")
    await tv_adapter(hass).force_close()
    assert called_entities(calls) == [TV_ENTITY]


async def test_media_player_warn_uses_notify_service(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "tv_salon")
    adapter = tv_adapter(hass, "notify.tv_salon")
    await adapter.warn("Télé salon : coupure dans 5 min")
    assert len(calls) == 1
    assert calls[0].data == {"message": "Télé salon : coupure dans 5 min"}


async def test_media_player_warn_without_notify_service(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "notify", "tv_salon")
    await tv_adapter(hass, None).warn("x")
    assert calls == []


# --- adguard -------------------------------------------------------------------


@pytest.fixture
def fake(hass: HomeAssistant) -> FakeAdGuard:
    return FakeAdGuard(hass)


def adguard(hass: HomeAssistant, fake: FakeAdGuard) -> AdGuardAdapter:
    return AdGuardAdapter(hass, "iPhone Hugo", {"device_id": fake.device_id}, LEISURE, ident)


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


def parent_ids(services: dict[str, tuple[str, ...]]):
    """Traduction par union, comme `Config.adguard_ids` (inconnus ignorés)."""
    def translate(ids) -> frozenset[str]:
        return frozenset(a for s in ids for a in services.get(s, ()))
    return translate


async def test_adguard_blocks_union_of_service_ids(hass: HomeAssistant, fake) -> None:
    fake.set_blocked([])
    adapter = AdGuardAdapter(
        hass, "iPhone Hugo", {"device_id": fake.device_id}, frozenset({"jeux"}),
        parent_ids({"jeux": ("roblox", "fortnite")}),
    )
    await adapter.apply(state(False, frozenset({"jeux"})))

    assert [c.data for c in fake.calls] == [
        {"device_id": fake.device_id, "block": ["fortnite", "roblox"], "unblock": []}
    ]


async def test_adguard_shared_id_blocked_wins(hass: HomeAssistant, fake) -> None:
    fake.set_blocked(["khan"])
    adapter = AdGuardAdapter(
        hass, "iPhone Hugo", {"device_id": fake.device_id}, frozenset({"video", "ecole"}),
        parent_ids({"video": ("youtube",), "ecole": ("youtube", "khan")}),
    )
    # `video` bloqué, `ecole` ouvert : youtube reste bloqué, khan est débloqué.
    desired = state(False, frozenset({"video"}))
    await adapter.apply(desired)

    assert fake.blocks() == ["youtube"]
    assert fake.unblocks() == ["khan"]
    assert not adapter.drifted(desired)


async def test_legacy_stored_ids_not_unblocked(hass: HomeAssistant, fake) -> None:
    """Config stockée sans services : les anciens identifiants sont retirés des loisirs
    au chargement, l'adaptateur ne débloque donc rien."""
    from custom_components.parental_control.core.config_io import parse_config
    from tests.fixtures import EX

    data = {k: v for k, v in EX.items() if k != "services"}
    data["default_leisure"] = ["youtube"]
    cfg = parse_config(data)
    assert cfg.default_leisure == ()
    fake.set_blocked(["youtube"])
    adapter = AdGuardAdapter(
        hass, "iPhone Hugo", {"device_id": fake.device_id},
        cfg.managed_services_for_resource(cfg.resources[0].id), cfg.adguard_ids,
    )
    await adapter.apply(OPEN)

    assert fake.calls == []
    assert fake.blocked == ["youtube"]


async def test_service_without_attachments_noop(hass: HomeAssistant, fake) -> None:
    fake.set_blocked([])
    adapter = AdGuardAdapter(
        hass, "iPhone Hugo", {"device_id": fake.device_id}, frozenset({"vide", "console"}),
        parent_ids({"vide": (), "console": ()}),
    )
    desired = state(False, frozenset({"vide", "console"}))
    assert not adapter.drifted(desired)
    await adapter.apply(desired)

    assert fake.calls == []
    assert adapter.describe(desired) == []


async def test_adguard_force_close_translates_once(hass: HomeAssistant, fake) -> None:
    fake.set_blocked([])
    adapter = AdGuardAdapter(
        hass, "iPhone Hugo", {"device_id": fake.device_id}, frozenset({"jeux"}),
        parent_ids({"jeux": ("roblox",)}),
    )
    assert adapter.pause_state().blocked_services == frozenset({"jeux"})
    await adapter.force_close()

    assert fake.blocks() == ["roblox"]


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


async def test_adguard_missing_sensor_waits_for_startup(
    hass: HomeAssistant, fake, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = adguard(hass, fake)  # capteur enregistré, sans état
    desired = state(False, LEISURE)

    hass.set_state(CoreState.starting)
    with caplog.at_level(logging.WARNING):
        await adapter.apply(desired)
    assert "introuvable" not in caplog.text

    # toujours absent une fois HA démarré : l'avertissement part
    hass.set_state(CoreState.running)
    with caplog.at_level(logging.WARNING):
        await adapter.apply(desired)
    assert "introuvable" in caplog.text


async def test_adguard_unknown_device_has_no_entities(hass: HomeAssistant, fake) -> None:
    adapter = AdGuardAdapter(hass, "iPhone Hugo", {"device_id": "inconnu"}, LEISURE, ident)
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
        await tv_adapter(hass).apply(CLOSED)
    assert any(TV_ENTITY in r.getMessage() for r in caplog.records)


async def test_media_player_missing_entity_warns_once(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = tv_adapter(hass)
    with caplog.at_level(logging.WARNING):
        assert not adapter.in_use()
        await adapter.apply(CLOSED)
        assert not adapter.drifted(CLOSED)
    warnings = [r for r in caplog.records if TV_ENTITY in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING


async def test_media_player_missing_entity_waits_for_startup(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = tv_adapter(hass)
    hass.set_state(CoreState.starting)
    with caplog.at_level(logging.WARNING):
        assert not adapter.in_use()
    assert TV_ENTITY not in caplog.text

    hass.set_state(CoreState.running)
    with caplog.at_level(logging.WARNING):
        assert not adapter.in_use()
    assert TV_ENTITY in caplog.text


# --- Nintendo ---------------------------------------------------------------

from unittest.mock import AsyncMock, patch  # noqa: E402

from custom_components.parental_control.adapters.nintendo import (  # noqa: E402
    NintendoAdapter,
)

SLICE_DELAY = 5
LIMIT = "number.switch_limit"
REMAINING = "sensor.switch_remaining"
USED = "sensor.switch_used"


SWITCH_OPTIONS = {
    "device_id": "dev123",
    "limit_entity": LIMIT,
    "remaining_entity": REMAINING,
    "used_entity": USED,
}


def switch_resource() -> Resource:
    return Resource(
        id="switch",
        name="Switch",
        owners=("hugo",),
        devices=(PhysicalDevice("Switch", (
            Integration(ResourceKind.NINTENDO, SWITCH_OPTIONS),
        )),),
    )


def nintendo(hass: HomeAssistant, delay: float = 0) -> NintendoAdapter:
    adapter = NintendoAdapter(hass, "Switch", SWITCH_OPTIONS)
    adapter._slice_delay = delay
    return adapter


async def test_build_adapter_exposes_nintendo(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "nintendo_parental_controls", "add_bonus_time")
    composite = build_adapter(hass, switch_resource(), LEISURE, ident)
    assert isinstance(composite.nintendo, NintendoAdapter)
    assert composite.nintendo.label == "Switch"
    assert composite.describe_grant(15) == ["accorderait 15 min sur Switch"]
    await composite.grant(20)
    assert [c.data for c in calls] == [{"device_id": "dev123", "bonus_time": 20}]


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
    adapter = nintendo(hass, SLICE_DELAY)
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
        await nintendo(hass, SLICE_DELAY).grant(20)
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


# --- describe (simulation : ce que apply ferait, sans rien appeler) ---------------

async def test_media_player_describe_closed_and_in_use(hass: HomeAssistant) -> None:
    hass.states.async_set(TV_ENTITY, "playing")
    calls = async_mock_service(hass, "media_player", "turn_off")
    adapter = tv_adapter(hass)

    assert adapter.describe(CLOSED) == [f"éteindrait Télé salon ({TV_ENTITY})"]
    assert adapter.describe(OPEN) == []
    assert adapter.describe_grant(15) == []
    assert calls == []


async def test_media_player_describe_not_in_use(hass: HomeAssistant) -> None:
    hass.states.async_set(TV_ENTITY, "off")
    calls = async_mock_service(hass, "media_player", "turn_off")
    assert tv_adapter(hass).describe(CLOSED) == []
    assert calls == []


async def test_adguard_describe_block_and_unblock(hass: HomeAssistant, fake) -> None:
    fake.set_blocked(["roblox", "khanacademy"])
    adapter = adguard(hass, fake)

    assert adapter.describe(state(False, LEISURE)) == [
        "bloquerait youtube sur iPhone Hugo"
    ]
    assert adapter.describe(OPEN) == ["débloquerait roblox sur iPhone Hugo"]
    # les deux lignes quand les deux se produisent
    fake.set_blocked(["roblox"])
    assert adapter.describe(state(True, frozenset({"youtube", "tiktok"}))) == [
        "bloquerait tiktok, youtube sur iPhone Hugo",
        "débloquerait roblox sur iPhone Hugo",
    ]
    assert adapter.describe_grant(15) == []
    assert fake.calls == []


async def test_adguard_describe_nothing_to_do(hass: HomeAssistant, fake) -> None:
    fake.set_blocked(["youtube", "roblox"])
    adapter = adguard(hass, fake)
    assert adapter.describe(state(False, LEISURE)) == []
    assert fake.calls == []


async def test_adguard_describe_unreadable_sensor(hass: HomeAssistant, fake) -> None:
    hass.states.async_set(fake.entity_id, "unavailable", {"services": []})
    assert adguard(hass, fake).describe(CLOSED) == []


async def test_adguard_describe_does_not_mutate_extra_blocked(
    hass: HomeAssistant, fake
) -> None:
    fake.set_blocked([])
    adapter = adguard(hass, fake)
    await adapter.apply(state(True, frozenset({"tiktok"})))
    assert adapter._extra_blocked == {"tiktok"}
    calls_before = len(fake.calls)

    # débloqué à la main : apply l'oublierait, describe ne doit pas le faire
    fake.set_blocked([])
    assert adapter.describe(OPEN) == []
    assert adapter._extra_blocked == {"tiktok"}
    # tiktok reste décrit comme à débloquer tant que apply ne l'a pas oublié
    fake.set_blocked(["tiktok"])
    assert adapter.describe(OPEN) == ["débloquerait tiktok sur iPhone Hugo"]
    assert adapter._extra_blocked == {"tiktok"}
    assert len(fake.calls) == calls_before


async def test_nintendo_describe_drift(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "number", "set_value")
    bonus = async_mock_service(hass, "nintendo_parental_controls", "add_bonus_time")
    adapter = nintendo(hass)
    hass.states.async_set(LIMIT, "60")

    assert adapter.describe(OPEN) == ["remettrait la limite de Switch à 0 min"]
    assert adapter.describe(CLOSED) == ["remettrait la limite de Switch à 0 min"]
    assert adapter.describe_grant(15) == ["accorderait 15 min sur Switch"]
    assert not calls and not bonus


async def test_nintendo_describe_no_drift(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "number", "set_value")
    adapter = nintendo(hass)
    assert adapter.describe(OPEN) == []  # entité absente
    hass.states.async_set(LIMIT, "0")
    assert adapter.describe(CLOSED) == []
    assert not calls


async def test_describe_warn_only_where_warn_does_something(
    hass: HomeAssistant, fake
) -> None:
    with_notify = tv_adapter(hass, "notify.tv_salon")
    assert with_notify.describe_warn("bientôt") == [
        f"afficherait « bientôt » sur {TV_LABEL}"
    ]
    assert tv_adapter(hass, None).describe_warn("x") == []
    assert adguard(hass, fake).describe_warn("x") == []
    assert nintendo(hass).describe_warn("x") == []


# --- composite : un appareil logique, plusieurs intégrations ------------------------

from custom_components.parental_control.adapters.simulation import (  # noqa: E402
    SimulatedAdapter,
)

SAMSUNG = "media_player.samsung"
GOOGLE_TV = "media_player.google_tv"


class MixedTv:
    """Télé : Samsung (lecteur + AdGuard), Google TV (lecteur + AdGuard), Chromecast (VPN)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.calls: list[ServiceCall] = []
        self.samsung = FakeAdGuard(hass, self.calls, name="Samsung")
        self.google = FakeAdGuard(hass, self.calls, name="Google TV")
        self.vpn = FakeAdGuard(hass, self.calls, name="Chromecast (VPN)")

        async def turn_off(call: ServiceCall) -> None:
            self.calls.append(call)
            hass.states.async_set(call.data["entity_id"], "off")

        hass.services.async_register("media_player", "turn_off", turn_off)
        self.resource = Resource(
            id="tv",
            name="Télé",
            owners=("hugo",),
            devices=(
                PhysicalDevice("Samsung", (
                    Integration(ResourceKind.MEDIA_PLAYER, {"entity_id": SAMSUNG}),
                    Integration(ResourceKind.ADGUARD, {"device_id": self.samsung.device_id}),
                )),
                PhysicalDevice("Google TV", (
                    Integration(ResourceKind.MEDIA_PLAYER, {"entity_id": GOOGLE_TV}),
                    Integration(ResourceKind.ADGUARD, {"device_id": self.google.device_id}),
                )),
                PhysicalDevice("Chromecast (VPN)", (
                    Integration(ResourceKind.ADGUARD, {"device_id": self.vpn.device_id}),
                )),
            ),
        )
        self.adapter = build_adapter(hass, self.resource, LEISURE, ident)

    @property
    def fakes(self) -> list[FakeAdGuard]:
        return [self.samsung, self.google, self.vpn]

    def turn_offs(self) -> list[str]:
        return sorted(c.data["entity_id"] for c in self.calls if c.domain == "media_player")

    def adguard_writes(self) -> list[ServiceCall]:
        return [c for c in self.calls if c.domain == "adguard_clients"]


@pytest.fixture
def mixed(hass: HomeAssistant) -> MixedTv:
    return MixedTv(hass)


async def test_mixed_tv_watches_every_member(hass: HomeAssistant, mixed) -> None:
    assert mixed.adapter.entity_ids() == [
        SAMSUNG, mixed.samsung.entity_id, GOOGLE_TV, mixed.google.entity_id,
        mixed.vpn.entity_id,
    ]
    assert mixed.adapter.nintendo is None


async def test_mixed_tv_closes_every_member(hass: HomeAssistant, mixed) -> None:
    hass.states.async_set(SAMSUNG, "on")
    hass.states.async_set(GOOGLE_TV, "playing")
    for fake in mixed.fakes:
        fake.set_blocked([])
    closed = state(False, LEISURE)

    assert mixed.adapter.drifted(closed)
    await mixed.adapter.apply(closed)

    assert mixed.turn_offs() == [GOOGLE_TV, SAMSUNG]
    assert len(mixed.adguard_writes()) == 3
    assert all(fake.blocked == ["roblox", "youtube"] for fake in mixed.fakes)
    assert not mixed.adapter.drifted(closed)


async def test_mixed_tv_in_use_if_one_player_plays(hass: HomeAssistant, mixed) -> None:
    hass.states.async_set(SAMSUNG, "off")
    hass.states.async_set(GOOGLE_TV, "playing")
    assert mixed.adapter.in_use()
    hass.states.async_set(GOOGLE_TV, "off")
    assert not mixed.adapter.in_use()


async def test_missing_integration_does_not_stop_siblings(
    hass: HomeAssistant, mixed, caplog: pytest.LogCaptureFixture
) -> None:
    """Samsung absente de HA, Chromecast VPN débranché : les autres sont pilotés."""
    hass.states.async_set(GOOGLE_TV, "on")
    mixed.samsung.set_blocked([])
    mixed.google.set_blocked([])  # le capteur du VPN n'a pas d'état
    closed = state(False, LEISURE)

    with caplog.at_level(logging.WARNING):
        await mixed.adapter.apply(closed)
        await mixed.adapter.apply(closed)

    assert mixed.turn_offs() == [GOOGLE_TV]
    assert mixed.samsung.blocked == mixed.google.blocked == ["roblox", "youtube"]
    assert mixed.vpn.blocks() == []
    assert sum(SAMSUNG in r.getMessage() for r in caplog.records) == 1
    assert sum("Chromecast (VPN)" in r.getMessage() for r in caplog.records) == 1


async def test_member_error_does_not_stop_siblings(
    hass: HomeAssistant, mixed, caplog: pytest.LogCaptureFixture
) -> None:
    """Une erreur inattendue d'un membre est journalisée avec son label."""
    hass.states.async_set(SAMSUNG, "on")
    for fake in mixed.fakes:
        fake.set_blocked([])

    async def broken(call: ServiceCall) -> None:
        raise RuntimeError("panne")

    hass.services.async_register("media_player", "turn_off", broken)
    with caplog.at_level(logging.ERROR):
        await mixed.adapter.apply(state(False, LEISURE))
        await mixed.adapter.force_close()

    assert all(fake.blocked == ["roblox", "youtube"] for fake in mixed.fakes)
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 2
    assert all(f"Samsung ({SAMSUNG})" in m and "panne" in m for m in errors)


async def test_service_exception_opens_every_adguard_client(
    hass: HomeAssistant, mixed
) -> None:
    """Exception « youtube ouvert » sur la Télé fermée : chaque client AdGuard le
    débloque et les lecteurs restent allumés (R6)."""
    hass.states.async_set(SAMSUNG, "on")
    hass.states.async_set(GOOGLE_TV, "playing")
    for fake in mixed.fakes:
        fake.set_blocked(["roblox", "youtube"])
    desired = state(False, frozenset({"roblox"}), opened=frozenset({"youtube"}))

    assert not mixed.adapter.drifted(desired)
    assert mixed.adapter.describe(desired) == [
        "débloquerait youtube sur Samsung",
        "débloquerait youtube sur Google TV",
        "débloquerait youtube sur Chromecast (VPN)",
    ]
    await mixed.adapter.apply(desired)

    assert [c.data["unblock"] for c in mixed.adguard_writes()] == [["youtube"]] * 3
    assert all(fake.blocked == ["roblox"] for fake in mixed.fakes)
    assert mixed.turn_offs() == []
    assert not mixed.adapter.drifted(desired)


async def test_mixed_tv_force_close_pauses_every_member(
    hass: HomeAssistant, mixed
) -> None:
    hass.states.async_set(SAMSUNG, "on")
    hass.states.async_set(GOOGLE_TV, "on")
    for fake in mixed.fakes:
        fake.set_blocked([])

    await mixed.adapter.force_close()

    assert mixed.turn_offs() == [GOOGLE_TV, SAMSUNG]
    assert all(fake.blocked == ["roblox", "youtube"] for fake in mixed.fakes)


async def test_mixed_tv_describe_per_integration(hass: HomeAssistant, mixed) -> None:
    hass.states.async_set(SAMSUNG, "on")
    hass.states.async_set(GOOGLE_TV, "off")
    for fake in mixed.fakes:
        fake.set_blocked([])

    expected = [
        f"éteindrait Samsung ({SAMSUNG})",
        "bloquerait roblox, youtube sur Samsung",
        "bloquerait roblox, youtube sur Google TV",
        "bloquerait roblox, youtube sur Chromecast (VPN)",
    ]
    assert mixed.adapter.describe(state(False, LEISURE)) == expected
    # pause : chaque membre avec son propre état fermé (loisirs pour AdGuard)
    assert mixed.adapter.describe_pause() == expected
    assert mixed.calls == []


async def test_simulated_composite_logs_each_line_once(
    hass: HomeAssistant, mixed
) -> None:
    hass.states.async_set(SAMSUNG, "on")
    for fake in mixed.fakes:
        fake.set_blocked([])
    logged: list[str] = []
    sim = SimulatedAdapter(mixed.adapter, lambda: True, lambda _name, line: logged.append(line))
    closed = state(False, LEISURE)

    await sim.apply(closed)
    await sim.apply(closed)  # même état, mêmes lignes : rien de nouveau
    assert len(logged) == 4
    await sim.force_close()  # la pause décrit les mêmes actions : déjà journalisées
    assert len(logged) == 4

    hass.states.async_set(SAMSUNG, "off")
    for fake in mixed.fakes:
        fake.set_blocked(["roblox", "youtube"])
    await sim.apply(closed)  # plus rien à faire : la mémoire est oubliée
    hass.states.async_set(SAMSUNG, "on")
    await sim.apply(closed)
    assert logged.count(f"éteindrait Samsung ({SAMSUNG})") == 2
    assert mixed.calls == []


async def test_simulated_composite_dedups_identical_lines(hass: HomeAssistant) -> None:
    """Deux clients AdGuard du même appareil physique : une seule ligne."""
    first = FakeAdGuard(hass, name="Google TV")
    second = FakeAdGuard(hass, first.calls, name="Google TV")
    first.set_blocked([])
    second.set_blocked([])
    resource = Resource(
        id="tv", name="Télé", owners=("hugo",),
        devices=(PhysicalDevice("Google TV", (
            Integration(ResourceKind.ADGUARD, {"device_id": first.device_id}),
            Integration(ResourceKind.ADGUARD, {"device_id": second.device_id}),
        )),),
    )
    logged: list[str] = []
    sim = SimulatedAdapter(
        build_adapter(hass, resource, LEISURE, ident), lambda: True,
        lambda _name, line: logged.append(line),
    )
    await sim.apply(state(False, LEISURE))
    assert logged == ["bloquerait roblox, youtube sur Google TV"]


async def test_composite_warn_failure_logged_as_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Un avertissement impossible est un avertissement, pas une erreur."""
    adapter = build_adapter(hass, tv_resource("notify.tv_absent"), LEISURE, ident)
    with caplog.at_level(logging.WARNING):
        await adapter.warn("bientôt")
    records = [r for r in caplog.records if "avertissement" in r.getMessage()]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert TV_LABEL in records[0].getMessage()
