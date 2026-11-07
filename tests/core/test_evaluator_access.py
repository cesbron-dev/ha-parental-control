import copy
from datetime import date, datetime, timedelta

from custom_components.parental_control.core.decisions import (
    Decisions,
    ManualException,
    Target,
)
from custom_components.parental_control.core.evaluator import KidStatus, evaluate
from custom_components.parental_control.core.model import DayType, SegmentType
from tests.core.conftest import TZ, mixed_tv
from tests.fixtures import integration_of

TUESDAY = date(2026, 10, 27)
ECOLE = {"hugo": DayType.ECOLE, "zoe": DayType.ECOLE, "alice": DayType.ECOLE}


def at(h: int, m: int = 0, day: date = TUESDAY) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


def exc(target: Target, open_: bool, *, id_: str = "e1", created: datetime | None = None,
        until: datetime | None = None) -> ManualException:
    return ManualException(id=id_, target=target, open=open_,
                           created=created or at(12), until=until, signature=None)


def test_hugo_free_window(cfg):
    snap = evaluate(at(15, 40), cfg, Decisions(), ECOLE)
    g = snap.kids["hugo"]
    assert g.status is KidStatus.AUTORISE
    assert g.until == at(16, 0)
    assert g.segment is SegmentType.LIBRE
    assert g.segment_end == at(16, 0)
    assert g.day_type is DayType.ECOLE
    assert g.reason == "Écrans autorisés jusqu'à 16:00"
    assert g.remaining_minutes is None and g.timer_end is None
    assert snap.expired_exception_ids == frozenset()
    assert snap.resources["tv"].open
    assert snap.resources["tv"].until == at(16, 0)


def test_hugo_waits_homework_at_1630(cfg):
    snap = evaluate(at(16, 30), cfg, Decisions(), ECOLE)
    g = snap.kids["hugo"]
    assert g.status is KidStatus.ATTENTE_DEVOIRS
    assert g.until == at(19, 0)
    assert snap.kids["zoe"].status is KidStatus.ATTENTE_DEVOIRS
    assert snap.kids["alice"].status is KidStatus.ATTENTE_DEVOIRS
    assert snap.resources["tv"].open is False
    assert snap.resources["tv"].until is None


def test_homework_done_opens_until_19(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY})
    g = evaluate(at(16, 30), cfg, dec, ECOLE).kids["hugo"]
    assert g.status is KidStatus.AUTORISE
    assert g.until == at(19, 0)


def test_free_window_extends_through_homework_when_done(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY})
    g = evaluate(at(15, 40), cfg, dec, ECOLE).kids["hugo"]
    assert g.until == at(19, 0)
    assert g.segment_end == at(16, 0)


def test_homework_done_yesterday_does_not_count(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY - timedelta(days=1)})
    g = evaluate(at(16, 30), cfg, dec, ECOLE).kids["hugo"]
    assert g.status is KidStatus.ATTENTE_DEVOIRS


def test_after_19_blocked_even_with_homework(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY})
    snap = evaluate(at(19, 30), cfg, dec, ECOLE)
    g = snap.kids["hugo"]
    assert g.status is KidStatus.BLOQUE
    assert g.until is None
    assert g.segment_end == at(0, 0, TUESDAY + timedelta(days=1))
    assert snap.resources["iphone_hugo"].open is False


def test_shared_tv_open_if_any_owner_allowed(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY})
    snap = evaluate(at(16, 30), cfg, dec, ECOLE)
    assert snap.resources["tv"].open is True
    assert snap.resources["tv"].until == at(19, 0)
    assert snap.resources["iphone_hugo"].open is True
    assert snap.resources["iphone_zoe"].open is False


def test_missing_day_type_defaults_to_weekday(cfg):
    snap = evaluate(at(15, 40), cfg, Decisions(), {})
    assert snap.kids["hugo"].day_type is DayType.ECOLE
    sunday = date(2026, 10, 25)
    snap = evaluate(at(9, 30, sunday), cfg, Decisions(), {})
    assert snap.kids["alice"].day_type is DayType.FIN_DE_SEMAINE
    assert snap.kids["alice"].status is KidStatus.AUTORISE


def test_switch_sur_demande_mode_overrides_timeline(make_cfg):
    def modify(d):
        for kid in d["kids"]:
            kid["resource_modes"] = {"switch": "sur_demande"}

    cfg = make_cfg(modify)
    snap = evaluate(at(15, 40), cfg, Decisions(), ECOLE)
    assert snap.kids["hugo"].status is KidStatus.AUTORISE
    assert snap.resources["switch"].open is False
    assert snap.resources["tv"].open is True
    # Sans mode, la Switch suivrait la frise.
    assert evaluate(at(15, 40), make_cfg(), Decisions(), ECOLE).resources["switch"].open


def test_libre_mode_opens_resource_until_midnight(make_cfg):
    cfg = make_cfg(lambda d: d["kids"][0].update(resource_modes={"iphone_hugo": "libre"}))
    snap = evaluate(at(20, 0), cfg, Decisions(), ECOLE)
    assert snap.kids["hugo"].status is KidStatus.BLOQUE
    assert snap.resources["iphone_hugo"].open is True
    assert snap.resources["iphone_hugo"].until == at(0, 0, TUESDAY + timedelta(days=1))
    assert snap.resources["iphone_hugo"].blocked_services == frozenset()


def test_resource_exception_opens_and_closes(cfg):
    dec = Decisions(exceptions=[exc(Target(resource_id="tv"), True)])
    snap = evaluate(at(20, 0), cfg, dec, ECOLE)
    assert snap.resources["tv"].open is True
    assert evaluate(at(20, 0), cfg, dec, ECOLE, apply_exceptions=False).resources["tv"].open is False

    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_hugo"), False)])
    snap = evaluate(at(15, 40), cfg, dec, ECOLE)
    assert snap.resources["iphone_hugo"].open is False
    assert snap.resources["iphone_hugo"].blocked_services == cfg.leisure_for_resource("iphone_hugo")


def test_latest_exception_wins(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="tv"), False, id_="new", created=at(13)),
        exc(Target(resource_id="tv"), True, id_="old", created=at(12)),
    ])
    assert evaluate(at(15, 40), cfg, dec, ECOLE).resources["tv"].open is False


def test_expired_exception_ignored(cfg):
    dec = Decisions(exceptions=[exc(Target(resource_id="tv"), True, until=at(19, 30))])
    assert evaluate(at(19, 15), cfg, dec, ECOLE).resources["tv"].open is True
    assert evaluate(at(20, 0), cfg, dec, ECOLE).resources["tv"].open is False


def test_pause_beats_everything(cfg):
    dec = Decisions(
        paused=True,
        homework_done={"hugo": TUESDAY},
        exceptions=[
            exc(Target(resource_id="tv"), True, id_="a"),
            exc(Target(resource_id="iphone_hugo", service="youtube"), True, id_="b"),
            exc(Target(resource_id="iphone_hugo", service="fortnite"), False, id_="c"),
        ],
    )
    snap = evaluate(at(15, 40), cfg, dec, ECOLE)
    for kid in snap.kids.values():
        assert kid.status is KidStatus.PAUSE
        assert kid.until is None
    assert not any(r.open for r in snap.resources.values())
    assert snap.resources["iphone_hugo"].blocked_services == (
        cfg.leisure_for_resource("iphone_hugo") | {"fortnite"}
    )
    assert snap.resources["tv"].blocked_services == frozenset()


def test_adguard_blocked_services_are_leisure_only(cfg):
    snap = evaluate(at(20, 0), cfg, Decisions(), ECOLE)
    iphone = snap.resources["iphone_hugo"]
    assert iphone.open is False
    assert iphone.blocked_services == cfg.leisure_for_resource("iphone_hugo")
    assert snap.resources["tv"].blocked_services == frozenset()
    assert evaluate(at(15, 40), cfg, Decisions(), ECOLE).resources[
        "iphone_hugo"].blocked_services == frozenset()


def test_mixed_device_blocks_leisure_when_closed(make_cfg):
    cfg = make_cfg(mixed_tv)
    tv = evaluate(at(20, 0), cfg, Decisions(), ECOLE).resources["tv"]
    assert tv.open is False
    assert tv.blocked_services == cfg.leisure_for_resource("tv") != frozenset()
    assert evaluate(at(15, 40), cfg, Decisions(), ECOLE).resources[
        "tv"].blocked_services == frozenset()
    # Les exceptions de service s'appliquent aussi à l'appareil mixte.
    dec = Decisions(exceptions=[exc(Target(resource_id="tv", service="youtube"), True)])
    blocked = evaluate(at(20, 0), cfg, dec, ECOLE).resources["tv"].blocked_services
    assert "youtube" not in blocked and "roblox" in blocked


def test_service_exception_opens_one_service(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo", service="youtube"), True),
    ])
    snap = evaluate(at(20, 0), cfg, dec, ECOLE)
    blocked = snap.resources["iphone_hugo"].blocked_services
    assert "youtube" not in blocked
    assert "roblox" in blocked
    assert "youtube" in snap.resources["iphone_zoe"].blocked_services


def test_service_exception_closes_one_service_when_open(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo", service="fortnite"), False),
    ])
    snap = evaluate(at(15, 40), cfg, dec, ECOLE)
    assert snap.resources["iphone_hugo"].open is True
    assert snap.resources["iphone_hugo"].blocked_services == frozenset({"fortnite"})


def test_kid_service_exception_applies_to_all_kid_devices(make_cfg):
    def modify(d):
        extra = copy.deepcopy(d["resources"][1])
        extra.update(id="ipad_hugo", name="iPad Hugo")
        integration_of(extra)["device_id"] = "adguard_ipad_hugo"
        d["resources"].append(extra)

    cfg = make_cfg(modify)
    dec = Decisions(exceptions=[exc(Target(kid_id="hugo", service="youtube"), True)])
    snap = evaluate(at(20, 0), cfg, dec, ECOLE)
    for rid in ("iphone_hugo", "ipad_hugo"):
        assert "youtube" not in snap.resources[rid].blocked_services
        assert "roblox" in snap.resources[rid].blocked_services
    assert "youtube" in snap.resources["iphone_zoe"].blocked_services


def test_resource_close_beats_older_service_open(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo", service="youtube"), True, id_="yt", created=at(19)),
        exc(Target(resource_id="iphone_hugo"), False, id_="stop", created=at(20)),
    ])
    snap = evaluate(at(20, 30), cfg, dec, ECOLE)
    assert snap.resources["iphone_hugo"].blocked_services == cfg.leisure_for_resource("iphone_hugo")


def test_newer_service_open_beats_resource_close(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo"), False, id_="stop", created=at(19)),
        exc(Target(resource_id="iphone_hugo", service="youtube"), True, id_="yt", created=at(20)),
    ])
    assert "youtube" not in evaluate(at(20, 30), cfg, dec, ECOLE).resources["iphone_hugo"].blocked_services


def test_resource_close_keeps_kid_service_open_on_other_devices(make_cfg):
    def modify(d):
        extra = copy.deepcopy(d["resources"][1])
        extra.update(id="ipad_hugo", name="iPad Hugo")
        integration_of(extra)["device_id"] = "adguard_ipad_hugo"
        d["resources"].append(extra)

    cfg = make_cfg(modify)
    dec = Decisions(exceptions=[
        exc(Target(kid_id="hugo", service="youtube"), True, id_="yt", created=at(19)),
        exc(Target(resource_id="iphone_hugo"), False, id_="stop", created=at(20)),
    ])
    snap = evaluate(at(20, 30), cfg, dec, ECOLE)
    assert "youtube" in snap.resources["iphone_hugo"].blocked_services
    assert "youtube" not in snap.resources["ipad_hugo"].blocked_services


def test_global_service_exception_applies_to_all_adguard(cfg):
    dec = Decisions(exceptions=[exc(Target(service="youtube"), True)])
    snap = evaluate(at(20, 0), cfg, dec, ECOLE)
    assert "youtube" not in snap.resources["iphone_hugo"].blocked_services
    assert "youtube" not in snap.resources["iphone_zoe"].blocked_services


def test_dst_end_day_uses_wall_clock(make_cfg):
    def modify(d):
        d["kids"][0]["profiles"]["fin_de_semaine"]["segments"][1]["type"] = "libre"

    cfg = make_cfg(modify)
    sunday = date(2026, 11, 1)  # passage à l'heure normale à 02:00
    now = at(8, 30, sunday)
    g = evaluate(now, cfg, Decisions(), {"hugo": DayType.FIN_DE_SEMAINE}).kids["hugo"]
    assert g.status is KidStatus.AUTORISE
    assert g.segment is SegmentType.LIBRE
    assert g.segment_end == datetime(2026, 11, 1, 20, 0, tzinfo=TZ)
    assert g.segment_end.utcoffset() == timedelta(hours=-5)
    assert g.until == datetime(2026, 11, 1, 20, 0, tzinfo=TZ)


def test_shared_until_spans_owner_handoff(make_cfg):
    def modify(d):
        d["kids"][2]["profiles"]["ecole"]["segments"][1]["start"] = "16:00"

    cfg = make_cfg(modify)
    dec = Decisions(homework_done={"alice": TUESDAY})
    snap = evaluate(at(15, 40), cfg, dec, ECOLE)
    # Hugo/Zoé libres jusqu'à 16:00, Alice (devoirs faits) prend le relais jusqu'à 19:00.
    assert snap.resources["tv"].open is True
    assert snap.resources["tv"].until == at(19, 0)
    assert snap.resources["switch"].until == at(19, 0)
    assert snap.resources["iphone_hugo"].until == at(16, 0)
    assert evaluate(at(16, 0), cfg, dec, ECOLE).resources["tv"].until == at(19, 0)


def test_shared_until_stops_at_gap(make_cfg):
    def modify(d):
        d["kids"][2]["profiles"]["ecole"]["segments"][1]["start"] = "16:30"

    cfg = make_cfg(modify)
    dec = Decisions(homework_done={"alice": TUESDAY})
    assert evaluate(at(15, 40), cfg, dec, ECOLE).resources["tv"].until == at(16, 0)


def test_service_exception_created_at_resource_close_is_ignored(cfg):
    # Borne : `created` égal à celui de la fermeture -> l'exception de service est ignorée (bloquée).
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo", service="youtube"), True, id_="yt", created=at(20)),
        exc(Target(resource_id="iphone_hugo"), False, id_="stop", created=at(20)),
    ])
    snap = evaluate(at(20, 30), cfg, dec, ECOLE)
    assert snap.resources["iphone_hugo"].blocked_services == cfg.leisure_for_resource("iphone_hugo")
