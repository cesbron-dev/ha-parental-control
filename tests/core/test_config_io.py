import copy
from datetime import time

import pytest

from custom_components.parental_control.core.config_io import (
    ConfigError,
    dump_config,
    parse_config,
)
from custom_components.parental_control.core.model import (
    DayType,
    ResourceKind,
    Segment,
    SegmentType,
)
from tests.fixtures import EX


def ex():
    return copy.deepcopy(EX)


def test_parse_example_config():
    cfg = parse_config(ex())
    assert cfg.kid("hugo").profile_for(DayType.ECOLE).segments[1] == Segment(
        time(15, 25), SegmentType.LIBRE
    )
    assert cfg.resource("tv").integrations[0].options["entity_id"] == "media_player.tv_salon"
    assert cfg.resource("tv").quota_minutes[DayType.FIN_DE_SEMAINE] == 180
    assert cfg.kid("hugo").profile_for(DayType.FIN_DE_SEMAINE).quota_minutes == 120


def test_round_trip():
    assert parse_config(dump_config(parse_config(ex()))) == parse_config(ex())


def test_profile_must_start_at_midnight():
    d = ex()
    d["kids"][0]["profiles"]["ecole"]["segments"][0]["start"] = "00:30"
    with pytest.raises(ConfigError, match=r"kids\[0\]\.profiles\.ecole\.segments\[0\]"):
        parse_config(d)


def test_segments_strictly_increasing():
    d = ex()
    segs = d["kids"][0]["profiles"]["ecole"]["segments"]
    segs[1]["start"], segs[2]["start"] = "16:00", "15:25"
    with pytest.raises(ConfigError, match=r"kids\[0\]\.profiles\.ecole\.segments\[2\]"):
        parse_config(d)


def test_ecole_and_fin_de_semaine_required():
    d = ex()
    del d["kids"][0]["profiles"]["ecole"]
    with pytest.raises(ConfigError, match="ecole"):
        parse_config(d)
    d = ex()
    del d["kids"][0]["profiles"]["fin_de_semaine"]
    with pytest.raises(ConfigError, match="fin_de_semaine"):
        parse_config(d)


def test_profile_fallback():
    kid = parse_config(ex()).kid("hugo")
    assert kid.profile_for(DayType.VACANCES) is kid.profile_for(DayType.FIN_DE_SEMAINE)
    assert kid.profile_for(DayType.CONGE_PEDA) is kid.profile_for(DayType.FIN_DE_SEMAINE)


def test_unknown_owner_rejected():
    d = ex()
    d["resources"][0]["owners"] = ["zoe"]
    with pytest.raises(ConfigError, match="zoe"):
        parse_config(d)


def test_resource_mode_unknown_resource_rejected():
    d = ex()
    d["kids"][0]["resource_modes"] = {"xbox": "libre"}
    with pytest.raises(ConfigError, match="xbox"):
        parse_config(d)


@pytest.mark.parametrize(
    ("index", "key"),
    [(1, "device_id"), (0, "entity_id"), (2, "device_id"), (2, "limit_entity"),
     (2, "remaining_entity"), (2, "used_entity")],
)
def test_kind_options_required(index, key):
    d = ex()
    del d["resources"][index][key]
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


def test_v1_resource_is_converted_to_one_device_with_one_integration():
    out = dump_config(parse_config(ex()))
    assert out["version"] == 2
    assert out["resources"][0] == {
        "id": "tv",
        "name": "Télé salon",
        "owners": ["hugo"],
        "quota_minutes": {"fin_de_semaine": 180},
        "devices": [{"name": "Télé salon", "integrations": [
            {"kind": "media_player", "entity_id": "media_player.tv_salon",
             "notify_service": None},
        ]}],
    }
    assert [r["id"] for r in out["resources"]] == ["tv", "iphone_hugo", "switch"]
    assert all("kind" not in r for r in out["resources"])


def test_v1_keeps_kind_and_options():
    cfg = parse_config(ex())
    assert [r.kind for r in cfg.resources] == [
        ResourceKind.MEDIA_PLAYER, ResourceKind.ADGUARD, ResourceKind.NINTENDO]
    switch = cfg.resource("switch").integrations[0]
    assert switch.options["used_entity"] == EX["resources"][2]["used_entity"]


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
                             quota_minutes={"fin_de_semaine": 90}),
                {"id": "sw", "name": "Switch", "owners": ["hugo"],
                 "devices": [{"name": "Switch", "integrations": [SWITCH]}]}])
    cfg = parse_config(d)
    out = dump_config(cfg)
    assert parse_config(out) == cfg
    assert out["resources"][0] == {**d["resources"][0]}
    assert "icon" not in out["resources"][1]


def test_unsupported_version_rejected():
    d = ex()
    d["version"] = 3
    with pytest.raises(ConfigError, match=r"^version : version non prise en charge : 3"):
        parse_config(d)
