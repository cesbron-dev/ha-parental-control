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
from tests.fixtures import EX


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
