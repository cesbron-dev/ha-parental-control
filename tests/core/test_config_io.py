import copy
import re
from datetime import time

import pytest

from custom_components.parental_control.core.config_io import (
    ConfigError,
    dump_config,
    migrate_v2,
    parse_client_config,
    parse_config,
)
from custom_components.parental_control.core.model import (
    DayType,
    ResourceKind,
    Segment,
    SegmentType,
)
from tests.core.conftest import family_config_dict
from tests.fixtures import EX, integration_of


def ex():
    return copy.deepcopy(EX)


def test_parse_example_config():
    cfg = parse_config(ex())
    assert cfg.kid("hugo").profile_for(DayType.SCHOOL).segments[1] == Segment(
        time(15, 25), SegmentType.FREE
    )
    assert cfg.resource("tv").integrations[0].options["entity_id"] == "media_player.tv_salon"
    assert cfg.resource("tv").quota_minutes[DayType.WEEKEND] == 180
    assert cfg.kid("hugo").profile_for(DayType.WEEKEND).quota_minutes == 120


def test_round_trip():
    assert parse_config(dump_config(parse_config(ex()))) == parse_config(ex())


def test_profile_must_start_at_midnight():
    d = ex()
    d["kids"][0]["profiles"]["school"]["segments"][0]["start"] = "00:30"
    with pytest.raises(ConfigError, match=r"kids\[0\]\.profiles\.school\.segments\[0\]"):
        parse_config(d)


def test_segments_strictly_increasing():
    d = ex()
    segs = d["kids"][0]["profiles"]["school"]["segments"]
    segs[1]["start"], segs[2]["start"] = "16:00", "15:25"
    with pytest.raises(ConfigError, match=r"kids\[0\]\.profiles\.school\.segments\[2\]"):
        parse_config(d)


def test_ecole_and_fin_de_semaine_required():
    d = ex()
    del d["kids"][0]["profiles"]["school"]
    with pytest.raises(ConfigError, match="school"):
        parse_config(d)
    d = ex()
    del d["kids"][0]["profiles"]["weekend"]
    with pytest.raises(ConfigError, match="weekend"):
        parse_config(d)


def test_profile_fallback():
    kid = parse_config(ex()).kid("hugo")
    assert kid.profile_for(DayType.HOLIDAYS) is kid.profile_for(DayType.WEEKEND)
    assert kid.profile_for(DayType.DAY_OFF) is kid.profile_for(DayType.WEEKEND)


def test_unknown_owner_rejected():
    d = ex()
    d["resources"][0]["owners"] = ["zoe"]
    with pytest.raises(ConfigError, match="zoe"):
        parse_config(d)


def test_resource_mode_unknown_resource_rejected():
    d = ex()
    d["kids"][0]["resource_modes"] = {"xbox": "free"}
    with pytest.raises(ConfigError, match="xbox"):
        parse_config(d)


@pytest.mark.parametrize(
    ("index", "key"),
    [(1, "device_id"), (0, "entity_id"), (2, "device_id"), (2, "limit_entity"),
     (2, "remaining_entity"), (2, "used_entity")],
)
def test_kind_options_required(index, key):
    d = ex()
    del integration_of(d["resources"][index])[key]
    with pytest.raises(ConfigError, match=key):
        parse_config(d)


def test_leisure_for():
    d = ex()
    d["kids"][0]["leisure_add"] = ["minecraft"]
    d["kids"][0]["leisure_remove"] = ["twitch"]
    leisure = parse_config(d).leisure_for("hugo")
    assert "minecraft" in leisure
    assert "twitch" not in leisure
    assert "youtube" in leisure


def test_leisure_for_resource_is_union_of_owners():
    d = ex()
    zoe = copy.deepcopy(d["kids"][0])
    zoe.update(id="zoe", name="Zoé", leisure_add=["minecraft"], leisure_remove=["youtube"])
    zoe["resource_modes"] = {}
    d["kids"].append(zoe)
    d["resources"][0]["owners"] = ["hugo", "zoe"]
    cfg = parse_config(d)
    shared = cfg.leisure_for_resource("tv")
    assert shared == cfg.leisure_for("hugo") | cfg.leisure_for("zoe")
    assert {"minecraft", "youtube"} <= shared


# --- version 2 : appareils physiques et intégrations ---------------------------


def _ex_v2(resources: list[dict]) -> dict:
    d = ex()
    d["version"] = 2
    d["kids"][0]["resource_modes"] = {}
    d["resources"] = resources
    return d


def _v2_resource(devices: list[dict], **extra) -> dict:
    return {"id": "tele", "name": "Télé", "owners": ["hugo"], "devices": devices, **extra}


MIXED_TV = [
    {"name": "Samsung", "integrations": [
        {"kind": "media_player", "entity_id": "media_player.samsung"},
        {"kind": "adguard_services", "device_id": "adguard_samsung"}]},
    {"name": "Google TV", "integrations": [
        {"kind": "media_player", "entity_id": "media_player.google_tv"},
        {"kind": "adguard_services", "device_id": "adguard_google_tv"},
        {"kind": "adguard_services", "device_id": "adguard_chromecast_vpn"}]},
]
NINTENDO_ALONE = r"^resources\[0\]\.devices : une console Nintendo ne se regroupe pas$"
AT_LEAST_ONE = r"^resources\[0\]\.devices : au moins une intégration$"
SWITCH = {"kind": "nintendo", "device_id": "dev", "limit_entity": "number.l",
          "remaining_entity": "sensor.r", "used_entity": "sensor.u"}


def test_example_dumps_back_unchanged():
    out = dump_config(parse_config(ex()))
    assert out["version"] == 3
    assert out["resources"] == [{"quota_minutes": {}, **r} for r in EX["resources"]]


def test_example_kinds_and_options():
    cfg = parse_config(ex())
    assert [r.kind for r in cfg.resources] == [
        ResourceKind.MEDIA_PLAYER, ResourceKind.ADGUARD, ResourceKind.NINTENDO]
    switch = cfg.resource("switch").integrations[0]
    assert switch.options["used_entity"] == integration_of(EX["resources"][2])["used_entity"]


def test_mixed_tv_kinds_and_integrations():
    res = parse_config(_ex_v2([_v2_resource(MIXED_TV, icon="mdi:television")])).resource("tele")
    assert res.kinds == {ResourceKind.MEDIA_PLAYER, ResourceKind.ADGUARD}
    assert res.kind is ResourceKind.MEDIA_PLAYER
    assert res.has(ResourceKind.ADGUARD)
    assert not res.has(ResourceKind.NINTENDO)
    assert len(res.integrations) == 5
    assert [i.options.get("entity_id") or i.options["device_id"] for i in res.integrations] == [
        "media_player.samsung", "adguard_samsung", "media_player.google_tv",
        "adguard_google_tv", "adguard_chromecast_vpn"]
    assert [d.name for d in res.devices] == ["Samsung", "Google TV"]
    assert res.integrations[0].options == {"entity_id": "media_player.samsung"}
    assert res.icon == "mdi:television"


def test_adguard_only_kind():
    devices = [{"name": "iPad", "integrations": [{"kind": "adguard_services", "device_id": "x"}]}]
    assert parse_config(_ex_v2([_v2_resource(devices)])).resource("tele").kind is (
        ResourceKind.ADGUARD)


def test_nintendo_mixed_rejected():
    devices = [{"name": "Switch", "integrations": [SWITCH]}, *MIXED_TV]
    with pytest.raises(ConfigError, match=NINTENDO_ALONE):
        parse_config(_ex_v2([_v2_resource(devices)]))


def test_two_nintendo_rejected():
    devices = [{"name": "Switch", "integrations": [SWITCH, dict(SWITCH)]}]
    with pytest.raises(ConfigError, match=NINTENDO_ALONE):
        parse_config(_ex_v2([_v2_resource(devices)]))


def test_single_nintendo_accepted():
    devices = [{"name": "Switch", "integrations": [SWITCH]}]
    res = parse_config(_ex_v2([_v2_resource(devices)])).resource("tele")
    assert res.kind is ResourceKind.NINTENDO


def test_zero_integration_rejected():
    devices = [{"name": "Samsung", "integrations": []}]
    with pytest.raises(ConfigError, match=AT_LEAST_ONE):
        parse_config(_ex_v2([_v2_resource(devices)]))
    with pytest.raises(ConfigError, match=AT_LEAST_ONE):
        parse_config(_ex_v2([_v2_resource([])]))


def test_empty_physical_device_accepted_if_another_has_integration():
    devices = [{"name": "Vide", "integrations": []}, *MIXED_TV]
    res = parse_config(_ex_v2([_v2_resource(devices)])).resource("tele")
    assert [d.name for d in res.devices] == ["Vide", "Samsung", "Google TV"]
    assert len(res.integrations) == 5


@pytest.mark.parametrize(
    ("resource", "path"),
    [
        (_v2_resource("pas une liste"), r"resources\[0\]\.devices : liste attendue"),
        (_v2_resource([{"integrations": []}]), r"resources\[0\]\.devices\[0\]\.name : texte"),
        (_v2_resource([{"name": "A", "integrations": [{"kind": "xbox"}]}]),
         r"resources\[0\]\.devices\[0\]\.integrations\[0\]\.kind : valeur inconnue"),
        (_v2_resource([*MIXED_TV, {"name": "B", "integrations": [{"kind": "media_player"}]}]),
         r"resources\[0\]\.devices\[2\]\.integrations\[0\]\.entity_id : texte"),
        (_v2_resource([{"name": "S", "integrations": [{**SWITCH, "used_entity": ""}]}]),
         r"resources\[0\]\.devices\[0\]\.integrations\[0\]\.used_entity : texte"),
    ],
)
def test_v2_error_paths(resource, path):
    with pytest.raises(ConfigError, match=f"^{path}"):
        parse_config(_ex_v2([resource]))


def test_v2_round_trip():
    d = _ex_v2([_v2_resource(MIXED_TV, icon="mdi:television",
                             quota_minutes={"weekend": 90}),
                {"id": "sw", "name": "Switch", "owners": ["hugo"],
                 "devices": [{"name": "Switch", "integrations": [SWITCH]}]}])
    cfg = parse_config(d)
    out = dump_config(cfg)
    assert parse_config(out) == cfg
    assert out["resources"][0] == {**d["resources"][0]}
    assert "icon" not in out["resources"][1]


@pytest.mark.parametrize("version", [1, 4, None, True])
def test_unsupported_version_rejected(version):
    d = ex()
    d["version"] = version
    with pytest.raises(ConfigError, match=rf"^version : version non prise en charge : {version!r}"):
        parse_config(d)


def test_missing_version_rejected():
    d = ex()
    del d["version"]
    with pytest.raises(ConfigError, match=r"^version : version non prise en charge : None"):
        parse_config(d)


def test_flat_resource_rejected():
    """Une ressource sans `devices` (ancien format plat) est refusée."""
    d = ex()
    d["resources"][0] = {"id": "tv", "name": "Télé", "kind": "media_player",
                         "owners": ["hugo"], "entity_id": "media_player.tv"}
    with pytest.raises(ConfigError, match=r"^resources\[0\]\.devices"):
        parse_config(d)


def _with_switch(integration: dict) -> dict:
    d = dump_config(parse_config(EX))
    d["resources"].append({"id": "pc", "name": "PC", "owners": ["hugo"], "quota_minutes": {},
                           "devices": [{"name": "Prise", "integrations": [integration]}]})
    return d


def test_switch_integration_parsed_and_counted() -> None:
    cfg = parse_config(_with_switch({"kind": "switch", "entity_id": "switch.prise_pc",
                                     "turn_on_when_allowed": True}))
    pc = cfg.resource("pc")
    assert pc.kind is ResourceKind.SWITCH
    assert pc.measured
    assert pc.integrations[0].options["turn_on_when_allowed"] is True
    assert parse_config(dump_config(cfg)) == cfg


def test_switch_integration_validation() -> None:
    path = "resources[3].devices[0].integrations[0]"
    with pytest.raises(ConfigError, match=re.escape(f"{path}.entity_id : entité switch.* attendue")):
        parse_config(_with_switch({"kind": "switch", "entity_id": "light.lampe"}))
    with pytest.raises(ConfigError, match=re.escape(f"{path}.turn_on_when_allowed : booléen attendu")):
        parse_config(_with_switch({"kind": "switch", "entity_id": "switch.x",
                                   "turn_on_when_allowed": "oui"}))


def test_on_demand_services_roundtrip() -> None:
    d = dump_config(parse_config(EX))
    assert d["default_on_demand"] == []
    d["default_on_demand"] = ["youtube"]
    d["kids"][0]["on_demand_remove"] = ["youtube"]
    cfg = parse_config(d)
    assert cfg.on_demand_for("hugo") == frozenset()
    assert parse_config(dump_config(cfg)) == cfg
    with pytest.raises(ConfigError, match=re.escape("default_on_demand")):
        parse_config({**d, "default_on_demand": "youtube"})


def test_request_notify_round_trip() -> None:
    cfg = parse_config(EX | {"request_notify": ["notify.mobile_app_iphone_de_julie"]})
    assert cfg.request_notify == ("notify.mobile_app_iphone_de_julie",)
    assert dump_config(cfg)["request_notify"] == ["notify.mobile_app_iphone_de_julie"]
    assert parse_config(dump_config(cfg)) == cfg


def test_request_notify_defaults_empty() -> None:
    assert parse_config(EX).request_notify == ()


def test_request_notify_must_be_strings() -> None:
    with pytest.raises(ConfigError, match=re.escape("request_notify")):
        parse_config(EX | {"request_notify": [3]})


def test_request_notify_owners_round_trip() -> None:
    raw = EX | {
        "request_notify": ["notify.mobile_app_ipad"],
        "request_notify_owners": {"notify.mobile_app_ipad": "u1"},
    }
    cfg = parse_config(raw)
    assert cfg.request_notify_owners == {"notify.mobile_app_ipad": "u1"}
    assert dump_config(cfg)["request_notify_owners"] == {"notify.mobile_app_ipad": "u1"}
    assert parse_config(dump_config(cfg)) == cfg


def test_request_notify_owners_absent_defaults_empty() -> None:
    assert parse_config(EX).request_notify_owners == {}
    # Toujours écrite, même vide : sa présence marque la migration des téléphones comme faite.
    assert dump_config(parse_config(EX))["request_notify_owners"] == {}


def test_request_notify_owners_unknown_target_rejected() -> None:
    raw = EX | {
        "request_notify": ["notify.mobile_app_ipad"],
        "request_notify_owners": {"notify.mobile_app_autre": "u1"},
    }
    with pytest.raises(ConfigError, match=r"^request_notify_owners"):
        parse_config(raw)


def test_request_notify_owners_empty_user_rejected() -> None:
    raw = EX | {
        "request_notify": ["notify.mobile_app_ipad"],
        "request_notify_owners": {"notify.mobile_app_ipad": ""},
    }
    with pytest.raises(ConfigError, match=re.escape("request_notify_owners")):
        parse_config(raw)


def _jeux(**over):
    svc = {
        "id": "jeux",
        "name": "Jeux vidéo",
        "icon": "mdi:gamepad-variant",
        "adguard": ["roblox", "fortnite"],
        "labels": [{"label_id": "console", "on_means_allowed": True}],
    }
    return {**svc, **over}


def test_label_fields_absent_keep_defaults():
    d = family_config_dict()
    cfg = parse_config(d)
    assert all(k.target_label is None for k in cfg.kids)
    assert all(r.target_label is None for r in cfg.resources)
    assert "target_label" not in str(dump_config(cfg))


def test_services_round_trip():
    d = family_config_dict()
    d["services"] = [_jeux()]
    d["default_leisure"] = ["jeux"]
    cfg = parse_config(d)
    assert dump_config(cfg)["services"] == d["services"]
    assert cfg.adguard_ids(["jeux"]) == {"roblox", "fortnite"}
    assert cfg.service_for_label("console")[0].id == "jeux"
    assert cfg.service_for_label("console")[1].on_means_allowed is True
    assert cfg.service_for_label("autre") is None
    assert cfg.has_adguard("jeux") and cfg.has_labels("jeux")
    assert not cfg.has_adguard("inconnu") and not cfg.has_labels("inconnu")
    assert cfg.adguard_ids(["inconnu"]) == frozenset()
    assert parse_config(dump_config(cfg)) == cfg


def test_service_icon_omitted_when_none():
    d = family_config_dict()
    d["services"] = [{"id": "x", "name": "X", "adguard": ["x"], "labels": []}]
    out = dump_config(parse_config(d))
    assert "icon" not in out["services"][0]


def _unknown_cfg():
    d = family_config_dict()
    d["services"] = [_jeux()]
    d["default_leisure"] = ["youtube", "jeux"]
    d["default_on_demand"] = ["tiktok"]
    d["kids"][0]["leisure_add"] = ["roblox"]
    return d


def test_stored_config_drops_unknown_services():
    cfg = parse_config(_unknown_cfg())
    assert cfg.default_leisure == ("jeux",)
    assert cfg.default_on_demand == ()
    assert cfg.kids[0].leisure_add == frozenset()


def test_client_config_rejects_unknown_service():
    with pytest.raises(ConfigError, match="default_leisure"):
        parse_client_config(_unknown_cfg())


def test_client_config_rejects_unknown_kid_service():
    d = family_config_dict()
    d["kids"][0]["on_demand_remove"] = ["nope"]
    with pytest.raises(ConfigError, match=r"kids\[0\]\.on_demand_remove : service inconnu : .nope."):
        parse_client_config(d)


def test_legacy_label_services_key_ignored():
    d = family_config_dict()
    d.pop("services", None)
    d["label_services"] = [{"label_id": "internet"}]
    assert parse_config(d).services == ()


def test_missing_default_leisure_is_empty():
    d = family_config_dict()
    d.pop("default_leisure", None)
    assert parse_config(d).default_leisure == ()


def test_label_fields_roundtrip():
    d = family_config_dict()
    d["resources"][0]["target_label"] = "tablette_alice"
    d["kids"][2]["target_label"] = "alice"
    cfg = parse_config(d)
    assert cfg.label_target("alice") == ("kid", "alice")
    assert cfg.label_target("tablette_alice") == ("resource", d["resources"][0]["id"])
    assert cfg.label_target("inconnu") is None
    out = dump_config(cfg)
    assert out["kids"][2]["target_label"] == "alice"
    assert out["resources"][0]["target_label"] == "tablette_alice"
    assert parse_config(out) == cfg


def test_label_both_service_and_target_rejected():
    d = family_config_dict()
    d["services"] = [_jeux()]
    d["kids"][0]["target_label"] = "console"
    with pytest.raises(ConfigError, match=r"^services\[0\]\.labels\[0\]"):
        parse_config(d)


def test_target_label_used_twice_rejected():
    d = family_config_dict()
    d["kids"][0]["target_label"] = "partage"
    d["resources"][0]["target_label"] = "partage"
    with pytest.raises(ConfigError, match="partage"):
        parse_config(d)


def test_service_duplicate_id_rejected():
    d = family_config_dict()
    d["services"] = [_jeux(labels=[]), _jeux(labels=[])]
    with pytest.raises(ConfigError, match=r"services\[1\]\.id"):
        parse_config(d)


def test_service_empty_name_rejected():
    d = family_config_dict()
    d["services"] = [_jeux(name="")]
    with pytest.raises(ConfigError, match=r"services\[0\]\.name"):
        parse_config(d)


def test_label_in_two_services_rejected():
    d = family_config_dict()
    d["services"] = [_jeux(), _jeux(id="autre")]
    with pytest.raises(ConfigError, match=r"services\[1\]\.labels\[0\]"):
        parse_config(d)


def test_service_adguard_must_be_list():
    d = family_config_dict()
    d["services"] = [_jeux(adguard="roblox")]
    with pytest.raises(ConfigError, match=r"services\[0\]\.adguard"):
        parse_config(d)


def test_service_on_means_allowed_must_be_bool():
    d = family_config_dict()
    d["services"] = [_jeux(labels=[{"label_id": "console", "on_means_allowed": "oui"}])]
    with pytest.raises(ConfigError, match=r"on_means_allowed"):
        parse_config(d)


# --- version 3 : identifiants en anglais ---------------------------------------


def test_v2_converted_to_v3():
    v2 = {"version": 2, "calendar_map": {"vacances": "vacances", "pédagogique": "conge_peda"},
          "kids": [{"id": "hugo", "name": "Hugo",
                    "resource_modes": {"tv": "suit_frise", "switch": "sur_demande"},
                    "profiles": {
                        "ecole": {"segments": [{"start": "00:00", "type": "bloque"},
                                               {"start": "16:00", "type": "apres_devoirs"}]},
                        "fin_de_semaine": {"segments": [{"start": "00:00", "type": "libre"}]},
                        "conge_peda": {"segments": [{"start": "00:00", "type": "sur_demande"}]}}}],
          "resources": [{"id": "tv", "name": "TV", "owners": ["hugo"],
                         "quota_minutes": {"fin_de_semaine": 60},
                         "devices": [{"name": "TV", "integrations": [
                             {"kind": "media_player", "entity_id": "media_player.tv"}]}]},
                        {"id": "switch", "name": "S", "owners": ["hugo"], "devices": [{"name": "S",
                         "integrations": [{"kind": "media_player", "entity_id": "media_player.s"}]}]}]}
    cfg = parse_config(v2)
    out = dump_config(cfg)
    assert out["version"] == 3
    assert out["calendar_map"] == {"vacances": "holidays", "pédagogique": "day_off"}
    kid = out["kids"][0]
    assert set(kid["profiles"]) == {"school", "weekend", "day_off"}
    assert [s["type"] for s in kid["profiles"]["school"]["segments"]] == ["blocked", "after_homework"]
    assert kid["resource_modes"] == {"tv": "schedule", "switch": "on_demand"}
    assert out["resources"][0]["quota_minutes"] == {"weekend": 60}


def test_v2_input_not_mutated():
    v2 = {"version": 2, "kids": [], "resources": []}
    assert migrate_v2(v2)["version"] == 3
    assert v2["version"] == 2


def test_client_config_v2_accepted():
    assert parse_client_config({"version": 2, "kids": [], "resources": []}) is not None


def test_v2_unknown_value_still_rejected():
    v2 = ex()
    v2["version"] = 2
    v2["kids"][0]["profiles"]["school"]["segments"][0]["type"] = "inconnu"
    with pytest.raises(ConfigError, match="inconnu"):
        parse_config(v2)
