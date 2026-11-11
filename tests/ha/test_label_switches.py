"""Interrupteurs labellisés : découverte et pilotage par le moteur."""

from __future__ import annotations

import copy
from datetime import timedelta

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parental_control.const import DOMAIN
from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.label_switches import (
    LabelSwitch,
    LabelSwitchIssue,
    discover,
)
from custom_components.parental_control.store import ParentalStore
from tests.fixtures import EX
from tests.ha.test_engine import (  # noqa: F401 - `services` est une fixture
    TUESDAY,
    at,
    config_for,
    services,
    setup,
    tick,
)

SWITCH = "switch.prise_tele"
BLOCKED = at(TUESDAY, 16, 30)  # Gabin : après-devoirs, écrans fermés
ALLOWED = at(TUESDAY, 15, 30)  # Gabin : libre


def label_config(*, managed: bool = True, on_means_allowed: bool = False,
                 services=None) -> dict:
    """Config d'exemple : label de service `ecran` (loisir de Gabin), label de cible `gabin`."""
    config = copy.deepcopy(config_for(services))
    config["label_services"] = [{"label_id": "ecran", "on_means_allowed": on_means_allowed}]
    kid = config["kids"][0]
    kid["target_label"] = "gabin"
    if managed:
        kid["leisure_add"] = ["label:ecran"]
    return config


def add_labels(hass: HomeAssistant) -> None:
    registry = lr.async_get(hass)
    registry.async_create("Écran")  # id « ecran »
    registry.async_create("gabin")


def add_switch(hass: HomeAssistant, labels: set[str] | None, state: str | None = "off",
               name: str = "Prise") -> None:
    registry = er.async_get(hass)
    entry = registry.async_get_or_create("switch", "test", "prise", suggested_object_id="prise_tele")
    assert entry.entity_id == SWITCH
    if labels is not None:
        registry.async_update_entity(SWITCH, labels=labels)
    if state is not None:
        hass.states.async_set(SWITCH, state, {"friendly_name": name})


async def start(hass, freezer, services, moment, config: dict):
    """Démarre le moteur puis laisse passer un tick : les services `switch` simulés ne sont
    enregistrés qu'après le démarrage (la plateforme de l'intégration prend la place)."""
    await ParentalStore(hass).save_config(parse_config(config))
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": "x"})
    entry.add_to_hass(hass)
    _, engine = await setup(hass, freezer, moment, entry=entry)
    await tick(hass, freezer)
    return engine


# --- découverte ----------------------------------------------------------------


async def test_discover_service_and_kid_target(hass) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"})
    er.async_get(hass).async_get_or_create("switch", "test", "autre", suggested_object_id="autre")
    cfg = parse_config(label_config())
    switches, issues = discover(hass, cfg)
    assert switches == [LabelSwitch(SWITCH, "label:ecran", False, (("kid", "gabin"),))]
    assert issues == []


async def test_discover_without_target_reports_issue(hass) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran"})
    switches, issues = discover(hass, parse_config(label_config()))
    assert switches == []
    assert issues == [LabelSwitchIssue(SWITCH, "label:ecran", "no_target")]


async def test_discover_unknown_label_reports_issue(hass) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"})
    lr.async_get(hass).async_delete("ecran")  # HA le retire aussi de l'interrupteur
    switches, issues = discover(hass, parse_config(label_config()))
    assert er.async_get(hass).async_get(SWITCH).labels == {"gabin"}
    assert switches == []
    assert issues == [LabelSwitchIssue("", "label:ecran", "unknown_label")]


async def test_discover_ignores_disabled_and_other_domains(hass) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"})
    registry = er.async_get(hass)
    registry.async_update_entity(SWITCH, disabled_by=er.RegistryEntryDisabler.USER)
    light = registry.async_get_or_create("light", "test", "lampe")
    registry.async_update_entity(light.entity_id, labels={"ecran", "gabin"})
    assert discover(hass, parse_config(label_config())) == ([], [])


# --- pilotage ------------------------------------------------------------------


async def test_engine_turns_switch_on_when_blocked(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert services.entities("switch", "turn_on") == [SWITCH]
    assert hass.states.get(SWITCH).state == "on"


async def test_engine_turns_switch_off_when_allowed(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "on")
    await start(hass, freezer, services, ALLOWED, label_config(services=services))
    assert services.entities("switch", "turn_off") == [SWITCH]
    assert services.of("switch", "turn_on") == []


async def test_on_means_allowed_inverts(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "on")
    config = label_config(on_means_allowed=True, services=services)
    await start(hass, freezer, services, BLOCKED, config)
    assert services.entities("switch", "turn_off") == [SWITCH]
    assert services.of("switch", "turn_on") == []


async def test_unmanaged_switch_untouched(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    await start(hass, freezer, services, BLOCKED, label_config(managed=False, services=services))
    assert services.of("switch", "turn_on") == []
    assert services.of("switch", "turn_off") == []


async def test_drift_corrected_once_per_cooldown(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    calls: list[ServiceCall] = []

    @callback
    def lagging(call: ServiceCall) -> None:
        calls.append(call)  # l'état ne change pas tout de suite

    hass.services.async_register("switch", "turn_on", lagging)
    freezer.tick(timedelta(seconds=31))
    hass.states.async_set(SWITCH, "off", {"friendly_name": "Prise", "n": 1})  # basculé à la main
    await hass.async_block_till_done()
    assert len(calls) == 1
    for i in range(2, 5):
        freezer.tick(timedelta(seconds=5))
        hass.states.async_set(SWITCH, "off", {"friendly_name": "Prise", "n": i})
        await hass.async_block_till_done()
    assert len(calls) == 1
    freezer.tick(timedelta(seconds=20))  # 35 s après la commande
    hass.states.async_set(SWITCH, "off", {"friendly_name": "Prise", "n": 9})
    await hass.async_block_till_done()
    assert len(calls) == 2


async def test_unavailable_switch_no_crash(hass, freezer, services, caplog) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "unavailable")
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    for _ in range(3):
        await tick(hass, freezer)
    assert services.of("switch", "turn_on") == []
    assert caplog.text.count(f"{SWITCH} indisponible") == 1


async def test_missing_switch_no_crash(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, None)  # dans le registre, sans état
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert services.of("switch", "turn_on") == []


async def test_failing_call_does_not_stop_others(hass, freezer, services, caplog) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    registry = er.async_get(hass)
    other = registry.async_get_or_create("switch", "test", "deux", suggested_object_id="deux")
    registry.async_update_entity(other.entity_id, labels={"ecran", "gabin"})
    hass.states.async_set(other.entity_id, "off")
    await start(hass, freezer, services, ALLOWED, label_config(services=services))
    seen: list[str] = []

    @callback
    def broken(call: ServiceCall) -> None:
        seen.append(call.data["entity_id"])
        if call.data["entity_id"] == SWITCH:
            raise RuntimeError("panne")

    hass.services.async_register("switch", "turn_on", broken)
    await tick(hass, freezer, 20)  # 15:51 -> 16:00 passé : fermé
    await tick(hass, freezer, 20)
    assert sorted(set(seen)) == sorted([SWITCH, other.entity_id])
    assert "panne" in caplog.text


async def test_label_added_triggers_rebuild(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, None, "off")  # pas encore de label
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert services.of("switch", "turn_on") == []
    er.async_get(hass).async_update_entity(SWITCH, labels={"ecran", "gabin"})
    await hass.async_block_till_done()
    assert services.entities("switch", "turn_on") == [SWITCH]


async def test_label_service_removed_stops_driving(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert len(services.of("switch", "turn_on")) == 1
    er.async_get(hass).async_update_entity(SWITCH, labels={"gabin"})
    hass.states.async_set(SWITCH, "off", {"friendly_name": "Prise"})
    await hass.async_block_till_done()
    await tick(hass, freezer, 5)
    assert len(services.of("switch", "turn_on")) == 1


async def test_issue_logged_once(hass, freezer, services, caplog) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran"}, "off")  # aucune cible
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    registry = er.async_get(hass)
    registry.async_update_entity(SWITCH, labels={"ecran", "autre"})  # reconstruction, même problème
    await hass.async_block_till_done()
    assert caplog.text.count(f"{SWITCH} : Écran ignoré (aucune cible") == 1


async def test_simulation_records_without_calling(hass, freezer, services, caplog) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    engine = await start(hass, freezer, services, ALLOWED, label_config(services=services))
    await engine.set_simulation(True)
    await tick(hass, freezer, 60)  # 16:30 : bloqué
    assert services.of("switch", "turn_on") == []
    assert "Simulation : Prise : allumer (bloquer Écran)" in caplog.text


async def test_label_switches_for_websocket(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    engine = await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert engine.label_switches == [{
        "entity_id": SWITCH,
        "name": hass.states.get(SWITCH).name,
        "service": "label:ecran",
        "service_name": "Écran",
        "targets": [{"kind": "kid", "id": "gabin"}],
        "blocked": True,
        "state": "on",
    }]
    assert engine.label_issues == []


async def test_registry_event_without_label_service_ignored(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    config = label_config(services=services)
    config["label_services"] = []
    engine = await start(hass, freezer, services, BLOCKED, config)
    evaluations: list[str] = []
    real = engine.async_evaluate

    async def spy(reason: str) -> None:
        evaluations.append(reason)
        await real(reason)

    engine.async_evaluate = spy
    er.async_get(hass).async_update_entity(SWITCH, labels={"gabin"})
    lr.async_get(hass).async_create("autre")
    await hass.async_block_till_done()
    assert "labels" not in evaluations
    assert services.of("switch", "turn_on") == []


async def test_leaving_simulation_resends_command(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "off")
    engine = await start(hass, freezer, services, ALLOWED, label_config(services=services))
    await engine.set_simulation(True)
    await tick(hass, freezer, 60)  # 16:30 : bloqué, rien n'est envoyé
    assert services.of("switch", "turn_on") == []
    await engine.set_simulation(False)
    assert services.entities("switch", "turn_on") == [SWITCH]


async def test_simulation_silent_when_already_in_wanted_state(
    hass, freezer, services, caplog
) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "gabin"}, "on")
    engine = await start(hass, freezer, services, BLOCKED, label_config(services=services))
    await engine.set_simulation(True)
    await engine.async_evaluate("test")
    assert "Simulation : " not in caplog.text
