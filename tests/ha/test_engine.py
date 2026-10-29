"""Moteur : boucle, usage, application, dérive, avertissements, calendrier."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.parental_control.const import DOMAIN, EVENT_WARNING
from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.core.decisions import Target, Timer
from custom_components.parental_control.core.model import DayType
from custom_components.parental_control.engine import ParentalEngine
from custom_components.parental_control.store import ParentalStore
from tests.fixtures import EX

TZ = ZoneInfo("America/Toronto")
TUESDAY = date(2026, 10, 27)
SATURDAY = date(2026, 10, 31)
TV = "media_player.tv_salon"
LEISURE = ["disneyplus", "netflix", "roblox", "tiktok", "twitch", "youtube"]
NOTIFY = "mobile_app_iphone_de_olivier"
LIMIT = "number.switch_papa_temps_d_ecran_max_aujourd_hui"
REMAINING = "sensor.switch_papa_temps_d_ecran_restant"
USED = "sensor.switch_papa_temps_d_ecran_utilise"


def at(day: date, hh: int, mm: int) -> datetime:
    return datetime.combine(day, time(hh, mm), tzinfo=TZ)


SERVICES_KEY = "test_parental_services"


def svc(service: str) -> str:
    return f"switch.adguard_iphone_gabin_svc_{service}"


class Services:
    """Services simulés : les appels mettent à jour l'état des entités."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.calls: list[ServiceCall] = []
        self.calendar_events: list[dict] = []
        self.calendar_error: Exception | None = None
        self.calendar_calls: list[ServiceCall] = []
        hass.data[SERVICES_KEY] = self
        self.register(hass)

    def register(self, hass: HomeAssistant, only: str | None = None) -> None:
        """Enregistre les services simulés (ou ceux du seul domaine `only`).

        `switch` est à refaire après la mise en route de l'intégration : la plateforme
        `switch` (pause générale) enregistre les vrais `switch.turn_on/turn_off`.
        """

        @callback
        def record(call: ServiceCall) -> None:
            self.calls.append(call)
            entity_id = call.data.get("entity_id")
            if call.service == "turn_off" and entity_id:
                hass.states.async_set(entity_id, "off")
            elif call.service == "turn_on" and entity_id:
                hass.states.async_set(entity_id, "on")

        for domain, service in [
            ("media_player", "turn_off"),
            ("switch", "turn_on"),
            ("switch", "turn_off"),
            ("number", "set_value"),
            ("nintendo_parental_controls", "add_bonus_time"),
            ("notify", NOTIFY),
        ]:
            if only is None or domain == only:
                hass.services.async_register(domain, service, record)
        if only is not None:
            return

        @callback
        def get_events(call: ServiceCall):
            self.calendar_calls.append(call)
            if self.calendar_error is not None:
                raise self.calendar_error
            ids = call.data["entity_id"]
            ids = [ids] if isinstance(ids, str) else ids
            return {eid: {"events": self.calendar_events} for eid in ids}

        hass.services.async_register(
            "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
        )

    def of(self, domain: str, service: str) -> list[ServiceCall]:
        return [c for c in self.calls if c.domain == domain and c.service == service]

    def entities(self, domain: str, service: str) -> list[str]:
        return sorted(c.data["entity_id"] for c in self.of(domain, service))


@pytest.fixture
async def services(hass: HomeAssistant) -> Services:
    await hass.config.async_set_time_zone("America/Toronto")
    return Services(hass)


def set_switches(hass: HomeAssistant, state: str) -> None:
    for service in LEISURE:
        hass.states.async_set(svc(service), state)


def set_nintendo(hass: HomeAssistant, used: str = "42", remaining: str = "18") -> None:
    hass.states.async_set(LIMIT, "0")
    hass.states.async_set(USED, used)
    hass.states.async_set(REMAINING, remaining)


async def setup(hass: HomeAssistant, freezer, moment: datetime | None = None,
                entry: MockConfigEntry | None = None) -> tuple[MockConfigEntry, ParentalEngine]:
    if moment is not None:
        freezer.move_to(moment)
    if entry is None:
        await ParentalStore(hass).save_config(parse_config(EX))
        entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": "x"})
        entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    if (services := hass.data.get(SERVICES_KEY)) is not None:
        services.register(hass, only="switch")
    return entry, entry.runtime_data


async def tick(hass: HomeAssistant, freezer, minutes: int = 1) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


# --- boucle et application -----------------------------------------------------


async def test_tick_turns_off_tv_at_16(hass, freezer, services) -> None:
    hass.states.async_set(TV, "on")
    await setup(hass, freezer, at(TUESDAY, 15, 59))
    assert services.of("media_player", "turn_off") == []
    await tick(hass, freezer, 2)
    assert services.entities("media_player", "turn_off") == [TV]


async def test_warning_fired_5_min_before(hass, freezer, services) -> None:
    events = async_capture_events(hass, EVENT_WARNING)
    await setup(hass, freezer, at(TUESDAY, 15, 50))

    def kid_events():
        return [e for e in events if e.data["target"] == "kid:gabin"]

    await tick(hass, freezer, 4)  # 15:54
    assert kid_events() == []
    await tick(hass, freezer)  # 15:55
    assert len(kid_events()) == 1
    event = kid_events()[0]
    assert event.data["closes_at"] == at(TUESDAY, 16, 0).isoformat()
    assert event.data["message"] == "Gabin : fin des écrans dans 5 min"
    # Ressources aussi averties (événement), mais seuls les enfants notifient les parents.
    assert {e.data["target"] for e in events} == {
        "kid:gabin", "resource:tv", "resource:iphone_gabin"
    }
    notes = [c.data for c in services.of("notify", NOTIFY)]
    assert notes == [{"title": "Contrôle parental",
                      "message": "Gabin : fin des écrans dans 5 min"}]
    await tick(hass, freezer)  # 15:56
    assert len(kid_events()) == 1


async def test_failing_notify_does_not_stop_warning(hass, freezer, services, caplog) -> None:
    @callback
    def boom(call: ServiceCall) -> None:
        raise HomeAssistantError("panne")

    hass.services.async_register("notify", NOTIFY, boom)
    events = async_capture_events(hass, EVENT_WARNING)
    await setup(hass, freezer, at(TUESDAY, 15, 54))
    await tick(hass, freezer)
    assert any(e.data["target"] == "kid:gabin" for e in events)
    assert "panne" in caplog.text


async def test_tv_usage_accumulates_only_when_on(hass, freezer, services) -> None:
    hass.states.async_set(TV, "on")
    _, engine = await setup(hass, freezer, at(SATURDAY, 10, 0))
    for _ in range(10):
        await tick(hass, freezer)
    hass.states.async_set(TV, "off")
    await hass.async_block_till_done()
    for _ in range(10):
        await tick(hass, freezer)
    assert engine.decisions.usage("tv", SATURDAY) == pytest.approx(10)
    assert engine.snapshot.resources["tv"].used_minutes == pytest.approx(10)


async def test_usage_elapsed_capped_to_5_minutes(hass, freezer, services) -> None:
    hass.states.async_set(TV, "on")
    _, engine = await setup(hass, freezer, at(SATURDAY, 10, 0))
    await tick(hass, freezer, 30)  # saut d'horloge : un seul passage
    assert engine.decisions.usage("tv", SATURDAY) == pytest.approx(5)


async def test_tv_turned_back_on_is_turned_off_again(hass, freezer, services) -> None:
    hass.states.async_set(TV, "on")
    await setup(hass, freezer, at(TUESDAY, 16, 30))
    assert len(services.of("media_player", "turn_off")) == 1
    freezer.tick(timedelta(seconds=31))  # après le délai anti-rafale, avant le tick
    hass.states.async_set(TV, "on")
    await hass.async_block_till_done()
    assert len(services.of("media_player", "turn_off")) == 2


async def test_drift_cooldown_when_device_state_lags(hass, freezer, services) -> None:
    calls = []

    @callback
    def lagging_off(call: ServiceCall) -> None:
        calls.append(call)  # l'état de la TV ne change pas tout de suite

    hass.services.async_register("media_player", "turn_off", lagging_off)
    hass.states.async_set(TV, "on")
    await setup(hass, freezer, at(TUESDAY, 16, 30))
    assert len(calls) == 1
    for i in range(5):
        freezer.tick(timedelta(seconds=5))
        hass.states.async_set(TV, "on", {"volume": i})
        await hass.async_block_till_done()
    assert len(calls) == 1
    freezer.tick(timedelta(seconds=10))  # 35 s après la commande
    hass.states.async_set(TV, "on", {"volume": 99})
    await hass.async_block_till_done()
    assert len(calls) == 2


async def test_desired_change_applies_despite_drift_cooldown(hass, freezer, services) -> None:
    set_switches(hass, "off")
    _, engine = await setup(hass, freezer, at(SATURDAY, 10, 0))
    services.calls.clear()
    await engine.start_timer("gabin", 30)  # changement voulu immédiat : ouverture
    assert services.entities("switch", "turn_off") == sorted(svc(s) for s in LEISURE)


async def test_no_duplicate_commands(hass, freezer, services) -> None:
    hass.states.async_set(TV, "on")
    set_switches(hass, "off")
    await setup(hass, freezer, at(TUESDAY, 16, 30))
    for _ in range(5):
        await tick(hass, freezer)
    per_entity = Counter((c.domain, c.service, c.data.get("entity_id"))
                         for c in services.calls if c.domain != "notify")
    assert per_entity
    assert max(per_entity.values()) == 1
    assert services.entities("switch", "turn_on") == sorted(svc(s) for s in LEISURE)


async def test_restart_restores_decisions_and_keeps_closed(
    hass, freezer, services, hass_storage
) -> None:
    set_switches(hass, "off")
    entry, engine = await setup(hass, freezer, at(SATURDAY, 10, 0))
    assert services.entities("switch", "turn_on") == sorted(svc(s) for s in LEISURE)
    await engine.start_timer("gabin", 30)
    await engine.homework_done("gabin")
    assert engine.snapshot.resources["iphone_gabin"].open
    assert services.entities("switch", "turn_off") == sorted(svc(s) for s in LEISURE)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "parental_control.state" in hass_storage  # écrit sans attendre le délai
    services.calls.clear()

    freezer.tick(timedelta(minutes=40))
    _, engine = await setup(hass, freezer, entry=entry)
    assert engine.decisions.homework_done_on("gabin", SATURDAY)
    assert len(engine.decisions.timers) == 1
    assert engine.decisions.active_timer("gabin", at(SATURDAY, 10, 40)) is None
    assert not engine.snapshot.resources["iphone_gabin"].open
    assert services.entities("switch", "turn_on") == sorted(svc(s) for s in LEISURE)


async def test_unload_cancels_listeners(hass, freezer, services) -> None:
    hass.states.async_set(TV, "on")
    entry, _ = await setup(hass, freezer, at(TUESDAY, 15, 59))
    assert await hass.config_entries.async_unload(entry.entry_id)
    await tick(hass, freezer, 2)
    hass.states.async_set(TV, "playing")
    await hass.async_block_till_done()
    assert services.of("media_player", "turn_off") == []


async def test_missing_entity_does_not_stop_other_resources(
    hass, freezer, services, caplog
) -> None:
    hass.states.async_set(TV, "on")
    with caplog.at_level(logging.WARNING):
        await setup(hass, freezer, at(TUESDAY, 16, 30))
    assert services.entities("media_player", "turn_off") == [TV]
    assert "introuvable" in caplog.text


async def test_adapter_exception_does_not_stop_other_resources(
    hass, freezer, services, caplog
) -> None:
    @callback
    def boom(call: ServiceCall) -> None:
        raise RuntimeError("explosion")

    hass.services.async_register("switch", "turn_on", boom)
    set_switches(hass, "off")
    hass.states.async_set(TV, "on")
    await setup(hass, freezer, at(TUESDAY, 16, 30))
    assert services.entities("media_player", "turn_off") == [TV]
    assert "explosion" in caplog.text


async def test_invalid_stored_config_leaves_engine_idle(
    hass, freezer, services, hass_storage, caplog
) -> None:
    hass_storage["parental_control.config"] = {
        "version": 1, "minor_version": 1, "key": "parental_control.config",
        "data": {"version": 1, "kids": "pas une liste"},
    }
    hass.states.async_set(TV, "on")
    freezer.move_to(at(TUESDAY, 16, 30))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": "x"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data
    await tick(hass, freezer)
    assert engine.config is None
    assert engine.snapshot is None
    assert services.calls == []
    assert "configuration" in caplog.text.lower()


async def test_decisions_kept_after_invalid_stored_config(
    hass, freezer, services, hass_storage
) -> None:
    hass_storage["parental_control.config"] = {
        "version": 1, "minor_version": 1, "key": "parental_control.config",
        "data": {"version": 1, "kids": "pas une liste"},
    }
    hass_storage["parental_control.state"] = {
        "version": 1, "minor_version": 1, "key": "parental_control.state",
        "data": {"homework_done": {"gabin": TUESDAY.isoformat()}},
    }
    freezer.move_to(at(TUESDAY, 16, 30))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": "x"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data
    assert engine.config is None
    assert engine.decisions.homework_done_on("gabin", TUESDAY)

    await engine.set_config(parse_config(EX))
    assert engine.decisions.homework_done_on("gabin", TUESDAY)
    assert engine.snapshot.resources["tv"].open


# --- calendrier ----------------------------------------------------------------


async def test_calendar_failure_falls_back_to_weekday(hass, freezer, services, caplog) -> None:
    services.calendar_error = HomeAssistantError("calendrier en panne")
    _, engine = await setup(hass, freezer, at(TUESDAY, 10, 0))
    assert engine.snapshot.kids["gabin"].day_type is DayType.ECOLE
    assert "calendrier en panne" in caplog.text


async def test_no_evaluation_before_first_calendar_refresh(hass, freezer, services) -> None:
    release = asyncio.Event()
    started = asyncio.Event()

    async def slow_get_events(call: ServiceCall):
        started.set()
        await release.wait()
        return {call.data["entity_id"]: {"events": []}}

    hass.services.async_register(
        "calendar", "get_events", slow_get_events, supports_response=SupportsResponse.ONLY
    )
    hass.states.async_set(TV, "on")
    freezer.move_to(at(TUESDAY, 16, 30))
    await ParentalStore(hass).save_config(parse_config(EX))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": "x"})
    entry.add_to_hass(hass)
    setup_task = hass.async_create_task(hass.config_entries.async_setup(entry.entry_id))
    await started.wait()
    hass.states.async_set(TV, "playing")  # changement d'état pendant la lecture
    for _ in range(5):
        await asyncio.sleep(0)
    assert services.calls == []
    assert entry.runtime_data.snapshot is None

    release.set()
    assert await setup_task
    await hass.async_block_till_done()
    assert services.entities("media_player", "turn_off") == [TV]


async def test_calendar_failure_keeps_todays_events(hass, freezer, services, caplog) -> None:
    services.calendar_events = [
        {"start": "2026-10-27", "end": "2026-10-28", "summary": "Congé pédagogique"},
    ]
    _, engine = await setup(hass, freezer, at(TUESDAY, 10, 0))
    assert engine.snapshot.kids["gabin"].day_type is DayType.CONGE_PEDA
    services.calendar_error = HomeAssistantError("panne passagère")
    await tick(hass, freezer, 15)  # rafraîchissement des 15 min
    assert len(services.calendar_calls) == 2
    assert "panne passagère" in caplog.text
    assert engine.snapshot.kids["gabin"].day_type is DayType.CONGE_PEDA


async def test_calendar_conge_peda_switches_profile(hass, freezer, services) -> None:
    services.calendar_events = [
        {"start": "2026-10-27", "end": "2026-10-28", "summary": "Congé pédagogique"},
        # Événement horaire : ignoré même s'il correspond à « vacances ».
        {"start": "2026-10-27T09:00:00-04:00", "end": "2026-10-27T10:00:00-04:00",
         "summary": "Réunion vacances"},
    ]
    _, engine = await setup(hass, freezer, at(TUESDAY, 10, 0))
    assert engine.snapshot.kids["gabin"].day_type is DayType.CONGE_PEDA
    call = services.calendar_calls[0]
    assert call.data["entity_id"] == "calendar.ecole_primaire"
    assert call.data["start_date_time"] == at(TUESDAY, 0, 0).isoformat()
    assert call.data["end_date_time"] == at(TUESDAY + timedelta(days=1), 0, 0).isoformat()


async def test_calendar_refreshed_at_midnight(hass, freezer, services) -> None:
    _, engine = await setup(hass, freezer, at(TUESDAY, 23, 50))
    assert engine.snapshot.kids["gabin"].day_type is DayType.ECOLE
    services.calendar_events = [
        {"start": "2026-10-28", "end": "2026-10-29", "summary": "Vacances"},
    ]
    await tick(hass, freezer, 11)  # 00:01
    await tick(hass, freezer)  # 00:02 (après le rafraîchissement de 00:00:05)
    assert engine.snapshot.kids["gabin"].day_type is DayType.VACANCES


# --- actions -------------------------------------------------------------------


async def test_start_timer_capped_to_remaining_quota(hass, freezer, services) -> None:
    now = at(SATURDAY, 10, 0)
    _, engine = await setup(hass, freezer, now)
    engine.decisions.timers.append(Timer("gabin", now - timedelta(minutes=100), now))
    await engine.start_timer("gabin", 30)
    timer = engine.decisions.active_timer("gabin", now)
    assert timer is not None
    assert timer.end == now + timedelta(minutes=20)


async def test_start_timer_errors(hass, freezer, services) -> None:
    now = at(SATURDAY, 10, 0)
    _, engine = await setup(hass, freezer, now)
    await engine.start_timer("gabin", 10)
    with pytest.raises(ServiceValidationError) as err:
        await engine.start_timer("gabin", 10)
    assert err.value.translation_key == "timer_active"

    await engine.stop_timer("gabin")
    assert engine.decisions.active_timer("gabin", now) is None
    engine.decisions.timers.append(Timer("gabin", now - timedelta(minutes=120), now))
    with pytest.raises(ServiceValidationError) as err:
        await engine.start_timer("gabin", 10)
    assert err.value.translation_key == "quota_exhausted"

    with pytest.raises(ServiceValidationError) as err:
        await engine.start_timer("inconnu", 10)
    assert err.value.translation_key == "unknown_kid"


async def test_start_timer_outside_quota_segment(hass, freezer, services) -> None:
    _, engine = await setup(hass, freezer, at(TUESDAY, 16, 30))
    with pytest.raises(ServiceValidationError) as err:
        await engine.start_timer("gabin", 10)
    assert err.value.translation_key == "not_in_quota"


async def test_pause_force_closes_all(hass, freezer, services) -> None:
    hass.states.async_set(TV, "on")
    set_switches(hass, "off")
    set_nintendo(hass)
    _, engine = await setup(hass, freezer, at(SATURDAY, 10, 0))
    await engine.start_timer("gabin", 30)
    assert services.of("media_player", "turn_off") == []
    services.calls.clear()

    await engine.set_pause(True)
    assert engine.decisions.paused
    assert services.entities("media_player", "turn_off") == [TV]
    assert [c.data for c in services.of("number", "set_value")] == [
        {"entity_id": LIMIT, "value": 0}
    ]
    assert services.entities("switch", "turn_on") == sorted(svc(s) for s in LEISURE)
    assert not any(r.open for r in engine.snapshot.resources.values())


async def test_nintendo_bonus_goes_through_grant(hass, freezer, services) -> None:
    set_nintendo(hass)
    _, engine = await setup(hass, freezer, at(SATURDAY, 10, 0))
    await engine.add_bonus(30, resource_id="switch")
    assert [c.data for c in services.of("nintendo_parental_controls", "add_bonus_time")] == [
        {"device_id": "b64d274dc045916f9a6de862a104fbb5", "bonus_time": 30}
    ]
    assert engine.decisions.bonuses == []

    await engine.add_bonus(15, kid_id="gabin")
    await engine.add_bonus(20, resource_id="tv")
    assert engine.decisions.bonus_minutes(SATURDAY, kid_id="gabin") == 15
    assert engine.decisions.bonus_minutes(SATURDAY, resource_id="tv") == 20


async def test_nintendo_state_uses_sensor_values(hass, freezer, services) -> None:
    set_nintendo(hass, used="42", remaining="18")
    _, engine = await setup(hass, freezer, at(SATURDAY, 10, 0))
    state = engine.snapshot.resources["switch"]
    assert state.used_minutes == 42
    assert state.remaining_minutes == 18


async def test_exception_until_next_decision_expires_and_is_removed(
    hass, freezer, services
) -> None:
    hass.states.async_set(TV, "on")
    _, engine = await setup(hass, freezer, at(TUESDAY, 15, 30))
    exc_id = await engine.add_exception(Target(resource_id="tv"), False, None)
    assert [e.id for e in engine.decisions.exceptions] == [exc_id]
    assert engine.decisions.exceptions[0].signature == (("tv", None, True),)
    assert services.entities("media_player", "turn_off") == [TV]

    await tick(hass, freezer, 31)  # 16:01 : la règle ferme, l'exception échoit
    assert engine.decisions.exceptions == []


async def test_exception_with_duration_and_cancel(hass, freezer, services) -> None:
    now = at(TUESDAY, 16, 30)
    _, engine = await setup(hass, freezer, now)
    exc_id = await engine.add_exception(Target(resource_id="tv"), True, 30)
    exc = engine.decisions.exceptions[0]
    assert exc.until == now + timedelta(minutes=30)
    assert exc.signature is None
    assert engine.snapshot.resources["tv"].open
    await engine.cancel_exception(exc_id)
    assert engine.decisions.exceptions == []
    assert not engine.snapshot.resources["tv"].open


@pytest.mark.parametrize(
    ("target", "key"),
    [
        (Target(kid_id="inconnu"), "unknown_kid"),
        (Target(resource_id="inconnue"), "unknown_resource"),
        (Target(resource_id="tv", service="youtube"), "invalid_target"),
        (Target(kid_id="gabin"), "invalid_target"),
        (Target(), "invalid_target"),
    ],
)
async def test_add_exception_rejects_invalid_target(
    hass, freezer, services, target, key
) -> None:
    _, engine = await setup(hass, freezer, at(TUESDAY, 16, 30))
    with pytest.raises(ServiceValidationError) as err:
        await engine.add_exception(target, True, 10)
    assert err.value.translation_key == key
    assert engine.decisions.exceptions == []


async def test_set_config_rebuilds_adapters(hass, freezer, services, hass_storage) -> None:
    _, engine = await setup(hass, freezer, at(TUESDAY, 16, 30))
    raw = {**EX, "resources": [{**EX["resources"][0], "entity_id": "media_player.autre"},
                               *EX["resources"][1:]]}
    await engine.set_config(parse_config(raw))
    assert engine.config.resource("tv").options["entity_id"] == "media_player.autre"
    hass.states.async_set("media_player.autre", "on")
    await hass.async_block_till_done()
    assert services.entities("media_player", "turn_off") == ["media_player.autre"]
    await hass.async_block_till_done()
    assert hass_storage["parental_control.config"]["data"]["resources"][0]["entity_id"] == (
        "media_player.autre"
    )


# --- revue finale --------------------------------------------------------------


def _without_tv() -> dict:
    return {**EX, "resources": [r for r in EX["resources"] if r["id"] != "tv"]}


async def test_set_config_prunes_exception_of_removed_resource(
    hass, freezer, services, caplog
) -> None:
    _, engine = await setup(hass, freezer, at(TUESDAY, 15, 30))
    await engine.add_exception(Target(resource_id="tv"), False, None)
    assert len(engine.decisions.exceptions) == 1
    with caplog.at_level(logging.INFO):
        await engine.set_config(parse_config(_without_tv()))
    assert engine.decisions.exceptions == []
    assert "tv" not in engine.snapshot.resources
    await tick(hass, freezer)
    assert engine.snapshot.resources["iphone_gabin"].open


async def test_restart_prunes_stored_exception_of_removed_resource(
    hass, freezer, services, hass_storage
) -> None:
    await ParentalStore(hass).save_config(parse_config(_without_tv()))
    hass_storage["parental_control.state"] = {
        "version": 1, "minor_version": 1, "key": "parental_control.state",
        "data": {"exceptions": [{
            "id": "e1", "target": {"resource_id": "tv", "kid_id": None, "service": None},
            "open": False, "created": at(TUESDAY, 15, 0).isoformat(), "until": None,
            "signature": [["tv", None, True]],
        }], "timers": [{"kid_id": "parti", "start": at(TUESDAY, 15, 0).isoformat(),
                        "end": at(TUESDAY, 15, 20).isoformat()}]},
    }
    freezer.move_to(at(TUESDAY, 15, 30))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": "x"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data
    assert engine.decisions.exceptions == []
    assert engine.decisions.timers == []
    assert engine.snapshot is not None


async def test_failed_start_cancels_listeners(hass, freezer, services, monkeypatch) -> None:
    from custom_components.parental_control import engine as engine_mod

    calls = []

    def boom(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("évaluation impossible")

    monkeypatch.setattr(engine_mod, "evaluate", boom)
    freezer.move_to(at(TUESDAY, 16, 30))
    await ParentalStore(hass).save_config(parse_config(EX))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": "x"})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert len(calls) == 1
    await tick(hass, freezer, 2)
    assert len(calls) == 1  # plus aucune écoute active


async def test_warning_before_service_exception_ends(hass, freezer, services) -> None:
    set_switches(hass, "on")
    events = async_capture_events(hass, EVENT_WARNING)
    _, engine = await setup(hass, freezer, at(TUESDAY, 19, 30))
    await engine.add_exception(
        Target(resource_id="iphone_gabin", service="youtube"), True, 30
    )
    key = "service:iphone_gabin:youtube"
    assert engine.closures[key] == at(TUESDAY, 20, 0)
    await tick(hass, freezer, 24)  # 19:54
    assert [e for e in events if e.data["target"] == key] == []
    await tick(hass, freezer)  # 19:55
    warned = [e.data for e in events if e.data["target"] == key]
    message = "youtube sur iPhone Gabin : coupure dans 5 min"
    assert warned == [{"target": key, "closes_at": at(TUESDAY, 20, 0).isoformat(),
                       "message": message}]
    assert [c.data for c in services.of("notify", NOTIFY)] == [
        {"title": "Contrôle parental", "message": message}
    ]


async def test_add_exception_rejects_nintendo(hass, freezer, services) -> None:
    _, engine = await setup(hass, freezer, at(TUESDAY, 16, 30))
    with pytest.raises(ServiceValidationError) as err:
        await engine.add_exception(Target(resource_id="switch"), True, 30)
    assert err.value.translation_key == "nintendo_use_bonus"
    assert engine.decisions.exceptions == []


async def test_nintendo_limit_raised_from_tablet_is_reset(hass, freezer, services) -> None:
    set_nintendo(hass)
    await setup(hass, freezer, at(SATURDAY, 10, 0))
    assert services.of("number", "set_value") == []
    hass.states.async_set(LIMIT, "120")  # number.set_value depuis la tablette
    await hass.async_block_till_done()
    assert [c.data for c in services.of("number", "set_value")] == [
        {"entity_id": LIMIT, "value": 0}
    ]
