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
    Segment,
    SegmentType,
)

EX = {
    "version": 1,
    "default_leisure": ["youtube", "roblox", "tiktok", "netflix", "disneyplus", "twitch"],
    "calendar_map": {"pédagogique": "conge_peda", "vacances": "vacances", "relâche": "vacances"},
    "notify": ["notify.mobile_app_iphone_de_olivier"],
    "kids": [
        {
            "id": "gabin",
            "name": "Gabin",
            "emoji": "🎮",
            "color": "#FF6B6B",
            "calendar": "calendar.ecole_primaire",
            "leisure_add": [],
            "leisure_remove": [],
            "resource_modes": {"switch": "sur_demande"},
            "profiles": {
                "ecole": {
                    "segments": [
                        {"start": "00:00", "type": "bloque"},
                        {"start": "15:25", "type": "libre"},
                        {"start": "16:00", "type": "apres_devoirs"},
                        {"start": "19:00", "type": "bloque"},
                    ]
                },
                "fin_de_semaine": {
                    "quota_minutes": 120,
                    "segments": [
                        {"start": "00:00", "type": "bloque"},
                        {"start": "08:00", "type": "quota"},
                        {"start": "20:00", "type": "bloque"},
                    ],
                },
            },
        }
    ],
    "resources": [
        {
            "id": "tv",
            "name": "Télé salon",
            "kind": "media_player",
            "owners": ["gabin"],
            "entity_id": "media_player.tv_salon",
            "notify_service": None,
            "quota_minutes": {"fin_de_semaine": 180},
        },
        {
            "id": "iphone_gabin",
            "name": "iPhone Gabin",
            "kind": "adguard_services",
            "owners": ["gabin"],
            "client": "iphone_gabin",
        },
        {
            "id": "switch",
            "name": "Switch",
            "kind": "nintendo",
            "owners": ["gabin"],
            "device_id": "b64d274dc045916f9a6de862a104fbb5",
            "limit_entity": "number.switch_papa_temps_d_ecran_max_aujourd_hui",
            "remaining_entity": "sensor.switch_papa_temps_d_ecran_restant",
            "used_entity": "sensor.switch_papa_temps_d_ecran_utilise",
        },
    ],
}


def ex():
    return copy.deepcopy(EX)


def test_parse_example_config():
    cfg = parse_config(ex())
    assert cfg.kid("gabin").profile_for(DayType.ECOLE).segments[1] == Segment(
        time(15, 25), SegmentType.LIBRE
    )
    assert cfg.resource("tv").options["entity_id"] == "media_player.tv_salon"
    assert cfg.resource("tv").quota_minutes[DayType.FIN_DE_SEMAINE] == 180
    assert cfg.kid("gabin").profile_for(DayType.FIN_DE_SEMAINE).quota_minutes == 120


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
    kid = parse_config(ex()).kid("gabin")
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
    ("index", "key"), [(1, "client"), (0, "entity_id"), (2, "device_id")]
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
    leisure = parse_config(d).leisure_for("gabin")
    assert "minecraft" in leisure
    assert "twitch" not in leisure
    assert "youtube" in leisure


def test_leisure_for_resource_is_union_of_owners():
    d = ex()
    zoe = copy.deepcopy(d["kids"][0])
    zoe.update(id="zoe", name="Zoé", leisure_add=["minecraft"], leisure_remove=["youtube"])
    zoe["resource_modes"] = {}
    d["kids"].append(zoe)
    d["resources"][0]["owners"] = ["gabin", "zoe"]
    cfg = parse_config(d)
    shared = cfg.leisure_for_resource("tv")
    assert shared == cfg.leisure_for("gabin") | cfg.leisure_for("zoe")
    assert {"minecraft", "youtube"} <= shared
