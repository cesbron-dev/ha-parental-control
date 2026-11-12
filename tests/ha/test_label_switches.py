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
from custom_components.parental_control.serialize import serialize_snapshot
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
BLOCKED = at(TUESDAY, 16, 30)  # Hugo : après-devoirs, écrans fermés
ALLOWED = at(TUESDAY, 15, 30)  # Hugo : libre


def label_config(*, managed: bool = True, on_means_allowed: bool = False,
                 services=None) -> dict:
    """Config d'exemple : label de service `ecran` (loisir de Hugo), label de cible `hugo`."""
    config = copy.deepcopy(config_for(services))
    config["services"] = [{
        "id": "ecran", "name": "Écran", "adguard": [],
        "labels": [{"label_id": "ecran", "on_means_allowed": on_means_allowed}],
    }]
    kid = config["kids"][0]
    kid["target_label"] = "hugo"
    if managed:
        kid["leisure_add"] = ["ecran"]
    return config


def add_labels(hass: HomeAssistant) -> None:
    registry = lr.async_get(hass)
    registry.async_create("Écran")  # id « ecran »
    registry.async_create("hugo")


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
    add_switch(hass, {"ecran", "hugo"})
    er.async_get(hass).async_get_or_create("switch", "test", "autre", suggested_object_id="autre")
    cfg = parse_config(label_config())
    switches, issues = discover(hass, cfg)
    assert switches == [LabelSwitch(SWITCH, "ecran", False, (("kid", "hugo"),))]
    assert issues == []


async def test_discover_without_target_reports_issue(hass) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran"})
    switches, issues = discover(hass, parse_config(label_config()))
    assert switches == []
    assert issues == [LabelSwitchIssue(SWITCH, "ecran", "no_target")]


async def test_discover_unknown_label_reports_issue(hass) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"})
    lr.async_get(hass).async_delete("ecran")  # HA le retire aussi de l'interrupteur
    switches, issues = discover(hass, parse_config(label_config()))
    assert er.async_get(hass).async_get(SWITCH).labels == {"hugo"}
    assert switches == []
    assert issues == [LabelSwitchIssue("", "ecran", "unknown_label")]


async def test_discover_unknown_labels_reported_once_per_service(hass) -> None:
    add_labels(hass)
    config = label_config()
    config["services"][0]["labels"] += [{"label_id": "console"}, {"label_id": "tablette"}]
    lr.async_get(hass).async_delete("ecran")
    _, issues = discover(hass, parse_config(config))
    assert issues == [LabelSwitchIssue("", "ecran", "unknown_label")]  # 3 labels absents, 1 problème


async def test_discover_ignores_disabled_and_other_domains(hass) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"})
    registry = er.async_get(hass)
    registry.async_update_entity(SWITCH, disabled_by=er.RegistryEntryDisabler.USER)
    light = registry.async_get_or_create("light", "test", "lampe")
    registry.async_update_entity(light.entity_id, labels={"ecran", "hugo"})
    assert discover(hass, parse_config(label_config())) == ([], [])


# --- pilotage ------------------------------------------------------------------


async def test_engine_turns_switch_on_when_blocked(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "off")
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert services.entities("switch", "turn_on") == [SWITCH]
    assert hass.states.get(SWITCH).state == "on"


async def test_engine_turns_switch_off_when_allowed(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "on")
    await start(hass, freezer, services, ALLOWED, label_config(services=services))
    assert services.entities("switch", "turn_off") == [SWITCH]
    assert services.of("switch", "turn_on") == []


async def test_on_means_allowed_inverts(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "on")
    config = label_config(on_means_allowed=True, services=services)
    await start(hass, freezer, services, BLOCKED, config)
    assert services.entities("switch", "turn_off") == [SWITCH]
    assert services.of("switch", "turn_on") == []


async def test_unmanaged_switch_untouched(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "off")
    await start(hass, freezer, services, BLOCKED, label_config(managed=False, services=services))
    assert services.of("switch", "turn_on") == []
    assert services.of("switch", "turn_off") == []


async def test_drift_corrected_once_per_cooldown(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "off")
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
    add_switch(hass, {"ecran", "hugo"}, "unavailable")
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    for _ in range(3):
        await tick(hass, freezer)
    assert services.of("switch", "turn_on") == []
    assert caplog.text.count(f"{SWITCH} indisponible") == 1


async def test_missing_switch_no_crash(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, None)  # dans le registre, sans état
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert services.of("switch", "turn_on") == []


async def test_failing_call_does_not_stop_others(hass, freezer, services, caplog) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "off")
    registry = er.async_get(hass)
    other = registry.async_get_or_create("switch", "test", "deux", suggested_object_id="deux")
    registry.async_update_entity(other.entity_id, labels={"ecran", "hugo"})
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
    er.async_get(hass).async_update_entity(SWITCH, labels={"ecran", "hugo"})
    await hass.async_block_till_done()
    assert services.entities("switch", "turn_on") == [SWITCH]


async def test_label_service_removed_stops_driving(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "off")
    await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert len(services.of("switch", "turn_on")) == 1
    er.async_get(hass).async_update_entity(SWITCH, labels={"hugo"})
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
    add_switch(hass, {"ecran", "hugo"}, "off")
    engine = await start(hass, freezer, services, ALLOWED, label_config(services=services))
    await engine.set_simulation(True)
    await tick(hass, freezer, 60)  # 16:30 : bloqué
    assert services.of("switch", "turn_on") == []
    assert "Simulation : Prise : allumer (bloquer Écran)" in caplog.text


async def test_label_switches_for_websocket(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "off")
    engine = await start(hass, freezer, services, BLOCKED, label_config(services=services))
    assert engine.label_switches == [{
        "entity_id": SWITCH,
        "name": hass.states.get(SWITCH).name,
        "service": "ecran",
        "service_name": "Écran",
        "targets": [{"kind": "kid", "id": "hugo"}],
        "blocked": True,
        "state": "on",
    }]
    assert engine.label_issues == []


async def test_registry_event_without_label_service_ignored(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "off")
    config = label_config(services=services)
    config["services"] = []
    config["kids"][0]["leisure_add"] = []
    engine = await start(hass, freezer, services, BLOCKED, config)
    evaluations: list[str] = []
    real = engine.async_evaluate

    async def spy(reason: str) -> None:
        evaluations.append(reason)
        await real(reason)

    engine.async_evaluate = spy
    er.async_get(hass).async_update_entity(SWITCH, labels={"hugo"})
    lr.async_get(hass).async_create("autre")
    await hass.async_block_till_done()
    assert "labels" not in evaluations
    assert services.of("switch", "turn_on") == []


async def test_leaving_simulation_resends_command(hass, freezer, services) -> None:
    add_labels(hass)
    add_switch(hass, {"ecran", "hugo"}, "off")
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
    add_switch(hass, {"ecran", "hugo"}, "on")
    engine = await start(hass, freezer, services, BLOCKED, label_config(services=services))
    await engine.set_simulation(True)
    await engine.async_evaluate("test")
    assert "Simulation : " not in caplog.text


async def test_state_exposes_label_services(hass, freezer, services) -> None:
    """Les cartes lisent les services par label de l'enfant (avec `blocked`) et de l'appareil."""
    add_labels(hass)
    lr.async_get(hass).async_create("tele")
    add_switch(hass, {"ecran", "hugo"}, "off")
    config = label_config(services=services)
    config["kids"][0]["on_demand_add"] = ["ecran"]
    config["kids"][0]["leisure_add"] = []
    config["resources"][0]["target_label"] = "tele"  # « tv »
    # Service par label déclaré sans aucun interrupteur : nommé quand même.
    lr.async_get(hass).async_create("Console")
    config["services"].append({
        "id": "console", "name": "Console", "adguard": [],
        "labels": [{"label_id": "console", "on_means_allowed": False}],
    })
    engine = await start(hass, freezer, services, BLOCKED, config)
    # Un second interrupteur vise l'appareil.
    registry = er.async_get(hass)
    registry.async_get_or_create("switch", "test", "autre", suggested_object_id="autre")
    registry.async_update_entity("switch.autre", labels={"ecran", "tele"})
    hass.states.async_set("switch.autre", "off")
    engine._discover_labels()
    await engine.async_evaluate("test")
    data = serialize_snapshot(engine, display=True)
    assert data["kids"]["hugo"]["label_services"] == [{"service": "ecran", "blocked": True}]
    assert data["kids"]["hugo"]["on_demand"] == ["ecran"]
    assert data["resources"]["tv"]["label_services"] == ["ecran"]
    assert data["resources"]["iphone_hugo"]["label_services"] == []
    assert data["services"]["ecran"] == {"name": "Écran", "icon": None, "adguard": False, "labels": True}
    assert list(data["services"]) == ["ecran", "console"]
    assert "label_services" not in serialize_snapshot(engine)["kids"]["hugo"]


# --- services mixtes et labels multiples ----------------------------------------


async def test_mixed_service_drives_adguard_and_switch(hass, freezer, services) -> None:
    """Service mixte dans les loisirs d'un enfant fermé : AdGuard bloque ET l'interrupteur s'allume."""
    add_labels(hass)
    add_switch(hass, {"console", "hugo"}, "off")
    lr.async_get(hass).async_create("Console")
    config = label_config(services=services)
    config["services"] = [{
        "id": "jeux", "name": "Jeux", "adguard": ["roblox"],
        "labels": [{"label_id": "console", "on_means_allowed": False}],
    }]
    config["default_leisure"] = []
    config["kids"][0]["leisure_add"] = ["jeux"]
    services.adguard.set_blocked([])
    await start(hass, freezer, services, BLOCKED, config)
    assert services.adguard.blocks() == ["roblox"]
    assert services.entities("switch", "turn_on") == [SWITCH]
    assert hass.states.get(SWITCH).state == "on"


async def test_per_label_on_means_allowed(hass, freezer, services) -> None:
    """Deux labels du même service, l'un inversé : un interrupteur allumé, l'autre éteint."""
    registry = lr.async_get(hass)
    for name in ("Normal", "Inverse", "hugo"):
        registry.async_create(name)
    add_switch(hass, {"normal", "hugo"}, "off")
    er.async_get(hass).async_get_or_create("switch", "test", "autre", suggested_object_id="autre")
    er.async_get(hass).async_update_entity("switch.autre", labels={"inverse", "hugo"})
    hass.states.async_set("switch.autre", "on", {"friendly_name": "Autre"})
    config = label_config(services=services)
    config["services"] = [{
        "id": "ecran", "name": "Écran", "adguard": [],
        "labels": [
            {"label_id": "normal", "on_means_allowed": False},
            {"label_id": "inverse", "on_means_allowed": True},
        ],
    }]
    await start(hass, freezer, services, BLOCKED, config)
    assert services.entities("switch", "turn_on") == [SWITCH]
    assert services.entities("switch", "turn_off") == ["switch.autre"]


async def test_discover_first_service_wins(hass) -> None:
    """Deux labels rattachés à deux services : le premier service de la config l'emporte."""
    registry = lr.async_get(hass)
    for name in ("A", "B", "hugo"):
        registry.async_create(name)
    add_switch(hass, {"a", "b", "hugo"})
    config = label_config()
    config["services"] = [
        {"id": "svc_b", "name": "B", "adguard": [], "labels": [{"label_id": "b"}]},
        {"id": "svc_a", "name": "A", "adguard": [], "labels": [{"label_id": "a"}]},
    ]
    config["kids"][0]["leisure_add"] = []
    switches, issues = discover(hass, parse_config(config))
    assert switches == [LabelSwitch(SWITCH, "svc_b", False, (("kid", "hugo"),))]
    assert issues == []
