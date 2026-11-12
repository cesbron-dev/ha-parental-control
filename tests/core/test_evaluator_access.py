import copy
from datetime import date, datetime, timedelta

from custom_components.parental_control.core.decisions import (
    Decisions,
    ManualException,
    Target,
)
from custom_components.parental_control.core.evaluator import (
    KidStatus,
    evaluate,
    rule_signature,
)
from custom_components.parental_control.core.model import (
    DayType,
    ResourceKind,
    SegmentType,
)
from tests.core.conftest import TZ, mixed_tv
from tests.fixtures import integration_of

TUESDAY = date(2026, 10, 27)
SCHOOL = {"hugo": DayType.SCHOOL, "zoe": DayType.SCHOOL, "alice": DayType.SCHOOL}


def at(h: int, m: int = 0, day: date = TUESDAY) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


def exc(target: Target, open_: bool, *, id_: str = "e1", created: datetime | None = None,
        until: datetime | None = None) -> ManualException:
    return ManualException(id=id_, target=target, open=open_,
                           created=created or at(12), until=until, signature=None)


def test_hugo_free_window(cfg):
    snap = evaluate(at(15, 40), cfg, Decisions(), SCHOOL)
    g = snap.kids["hugo"]
    assert g.status is KidStatus.ALLOWED
    assert g.until == at(16, 0)
    assert g.segment is SegmentType.FREE
    assert g.segment_end == at(16, 0)
    assert g.day_type is DayType.SCHOOL
    assert g.reason == "Écrans autorisés jusqu'à 16:00"
    assert g.remaining_minutes is None and g.timer_end is None
    assert snap.expired_exception_ids == frozenset()
    assert snap.resources["tv"].open
    assert snap.resources["tv"].until == at(16, 0)


def test_hugo_waits_homework_at_1630(cfg):
    snap = evaluate(at(16, 30), cfg, Decisions(), SCHOOL)
    g = snap.kids["hugo"]
    assert g.status is KidStatus.WAITING_HOMEWORK
    assert g.until == at(19, 0)
    assert snap.kids["zoe"].status is KidStatus.WAITING_HOMEWORK
    assert snap.kids["alice"].status is KidStatus.WAITING_HOMEWORK
    assert snap.resources["tv"].open is False
    assert snap.resources["tv"].until is None


def test_homework_done_opens_until_19(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY})
    g = evaluate(at(16, 30), cfg, dec, SCHOOL).kids["hugo"]
    assert g.status is KidStatus.ALLOWED
    assert g.until == at(19, 0)


def test_free_window_extends_through_homework_when_done(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY})
    g = evaluate(at(15, 40), cfg, dec, SCHOOL).kids["hugo"]
    assert g.until == at(19, 0)
    assert g.segment_end == at(16, 0)


def test_homework_done_yesterday_does_not_count(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY - timedelta(days=1)})
    g = evaluate(at(16, 30), cfg, dec, SCHOOL).kids["hugo"]
    assert g.status is KidStatus.WAITING_HOMEWORK


def test_after_19_blocked_even_with_homework(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY})
    snap = evaluate(at(19, 30), cfg, dec, SCHOOL)
    g = snap.kids["hugo"]
    assert g.status is KidStatus.BLOCKED
    assert g.until is None
    assert g.segment_end == at(0, 0, TUESDAY + timedelta(days=1))
    assert snap.resources["iphone_hugo"].open is False


def test_shared_tv_open_if_any_owner_allowed(cfg):
    dec = Decisions(homework_done={"hugo": TUESDAY})
    snap = evaluate(at(16, 30), cfg, dec, SCHOOL)
    assert snap.resources["tv"].open is True
    assert snap.resources["tv"].until == at(19, 0)
    assert snap.resources["iphone_hugo"].open is True
    assert snap.resources["iphone_zoe"].open is False


def test_missing_day_type_defaults_to_weekday(cfg):
    snap = evaluate(at(15, 40), cfg, Decisions(), {})
    assert snap.kids["hugo"].day_type is DayType.SCHOOL
    sunday = date(2026, 10, 25)
    snap = evaluate(at(9, 30, sunday), cfg, Decisions(), {})
    assert snap.kids["alice"].day_type is DayType.WEEKEND
    assert snap.kids["alice"].status is KidStatus.ALLOWED


def test_switch_sur_demande_mode_overrides_timeline(make_cfg):
    def modify(d):
        for kid in d["kids"]:
            kid["resource_modes"] = {"switch": "on_demand"}

    cfg = make_cfg(modify)
    snap = evaluate(at(15, 40), cfg, Decisions(), SCHOOL)
    assert snap.kids["hugo"].status is KidStatus.ALLOWED
    assert snap.resources["switch"].open is False
    assert snap.resources["tv"].open is True
    # Sans mode, la Switch suivrait la frise.
    assert evaluate(at(15, 40), make_cfg(), Decisions(), SCHOOL).resources["switch"].open


def test_libre_mode_opens_resource_until_midnight(make_cfg):
    cfg = make_cfg(lambda d: d["kids"][0].update(resource_modes={"iphone_hugo": "free"}))
    snap = evaluate(at(20, 0), cfg, Decisions(), SCHOOL)
    assert snap.kids["hugo"].status is KidStatus.BLOCKED
    assert snap.resources["iphone_hugo"].open is True
    assert snap.resources["iphone_hugo"].until == at(0, 0, TUESDAY + timedelta(days=1))
    assert snap.resources["iphone_hugo"].blocked_services == frozenset()


def test_resource_exception_opens_and_closes(cfg):
    dec = Decisions(exceptions=[exc(Target(resource_id="tv"), True)])
    snap = evaluate(at(20, 0), cfg, dec, SCHOOL)
    assert snap.resources["tv"].open is True
    assert evaluate(at(20, 0), cfg, dec, SCHOOL, apply_exceptions=False).resources["tv"].open is False

    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_hugo"), False)])
    snap = evaluate(at(15, 40), cfg, dec, SCHOOL)
    assert snap.resources["iphone_hugo"].open is False
    assert snap.resources["iphone_hugo"].blocked_services == cfg.leisure_for_resource("iphone_hugo")


def test_latest_exception_wins(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="tv"), False, id_="new", created=at(13)),
        exc(Target(resource_id="tv"), True, id_="old", created=at(12)),
    ])
    assert evaluate(at(15, 40), cfg, dec, SCHOOL).resources["tv"].open is False


def test_expired_exception_ignored(cfg):
    dec = Decisions(exceptions=[exc(Target(resource_id="tv"), True, until=at(19, 30))])
    assert evaluate(at(19, 15), cfg, dec, SCHOOL).resources["tv"].open is True
    assert evaluate(at(20, 0), cfg, dec, SCHOOL).resources["tv"].open is False


def test_pause_beats_everything(cfg):
    dec = Decisions(
        paused=True,
        homework_done={"hugo": TUESDAY},
        exceptions=[
            exc(Target(resource_id="tv"), True, id_="a"),
            exc(Target(resource_id="iphone_hugo", service="youtube"), True, id_="b"),
            exc(Target(resource_id="iphone_hugo", service="minecraft"), False, id_="c"),
        ],
    )
    snap = evaluate(at(15, 40), cfg, dec, SCHOOL)
    for kid in snap.kids.values():
        assert kid.status is KidStatus.PAUSED
        assert kid.until is None
    assert not any(r.open for r in snap.resources.values())
    assert snap.resources["iphone_hugo"].blocked_services == (
        cfg.leisure_for_resource("iphone_hugo") | {"minecraft"}
    )
    assert snap.resources["tv"].blocked_services == frozenset()


def test_adguard_blocked_services_are_leisure_only(cfg):
    snap = evaluate(at(20, 0), cfg, Decisions(), SCHOOL)
    iphone = snap.resources["iphone_hugo"]
    assert iphone.open is False
    assert iphone.blocked_services == cfg.leisure_for_resource("iphone_hugo")
    assert snap.resources["tv"].blocked_services == frozenset()
    assert evaluate(at(15, 40), cfg, Decisions(), SCHOOL).resources[
        "iphone_hugo"].blocked_services == frozenset()


def test_mixed_device_blocks_leisure_when_closed(make_cfg):
    cfg = make_cfg(mixed_tv)
    tv = evaluate(at(20, 0), cfg, Decisions(), SCHOOL).resources["tv"]
    assert tv.open is False
    assert tv.blocked_services == cfg.leisure_for_resource("tv") != frozenset()
    assert evaluate(at(15, 40), cfg, Decisions(), SCHOOL).resources[
        "tv"].blocked_services == frozenset()
    # Les exceptions de service s'appliquent aussi à l'appareil mixte.
    dec = Decisions(exceptions=[exc(Target(resource_id="tv", service="youtube"), True)])
    blocked = evaluate(at(20, 0), cfg, dec, SCHOOL).resources["tv"].blocked_services
    assert "youtube" not in blocked and "roblox" in blocked


def test_service_exception_opens_one_service(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo", service="youtube"), True),
    ])
    snap = evaluate(at(20, 0), cfg, dec, SCHOOL)
    blocked = snap.resources["iphone_hugo"].blocked_services
    assert "youtube" not in blocked
    assert "roblox" in blocked
    assert "youtube" in snap.resources["iphone_zoe"].blocked_services


def test_service_exception_closes_one_service_when_open(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo", service="minecraft"), False),
    ])
    snap = evaluate(at(15, 40), cfg, dec, SCHOOL)
    assert snap.resources["iphone_hugo"].open is True
    assert snap.resources["iphone_hugo"].blocked_services == frozenset({"minecraft"})


def test_kid_service_exception_applies_to_all_kid_devices(make_cfg):
    def modify(d):
        extra = copy.deepcopy(d["resources"][1])
        extra.update(id="ipad_hugo", name="iPad Hugo")
        integration_of(extra)["device_id"] = "adguard_ipad_hugo"
        d["resources"].append(extra)

    cfg = make_cfg(modify)
    dec = Decisions(exceptions=[exc(Target(kid_id="hugo", service="youtube"), True)])
    snap = evaluate(at(20, 0), cfg, dec, SCHOOL)
    for rid in ("iphone_hugo", "ipad_hugo"):
        assert "youtube" not in snap.resources[rid].blocked_services
        assert "roblox" in snap.resources[rid].blocked_services
    assert "youtube" in snap.resources["iphone_zoe"].blocked_services


def test_resource_close_beats_older_service_open(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo", service="youtube"), True, id_="yt", created=at(19)),
        exc(Target(resource_id="iphone_hugo"), False, id_="stop", created=at(20)),
    ])
    snap = evaluate(at(20, 30), cfg, dec, SCHOOL)
    assert snap.resources["iphone_hugo"].blocked_services == cfg.leisure_for_resource("iphone_hugo")


def test_newer_service_open_beats_resource_close(cfg):
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo"), False, id_="stop", created=at(19)),
        exc(Target(resource_id="iphone_hugo", service="youtube"), True, id_="yt", created=at(20)),
    ])
    assert "youtube" not in evaluate(at(20, 30), cfg, dec, SCHOOL).resources["iphone_hugo"].blocked_services


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
    snap = evaluate(at(20, 30), cfg, dec, SCHOOL)
    assert "youtube" in snap.resources["iphone_hugo"].blocked_services
    assert "youtube" not in snap.resources["ipad_hugo"].blocked_services


def test_global_service_exception_applies_to_all_adguard(cfg):
    dec = Decisions(exceptions=[exc(Target(service="youtube"), True)])
    snap = evaluate(at(20, 0), cfg, dec, SCHOOL)
    assert "youtube" not in snap.resources["iphone_hugo"].blocked_services
    assert "youtube" not in snap.resources["iphone_zoe"].blocked_services


def test_dst_end_day_uses_wall_clock(make_cfg):
    def modify(d):
        d["kids"][0]["profiles"]["weekend"]["segments"][1]["type"] = "free"

    cfg = make_cfg(modify)
    sunday = date(2026, 11, 1)  # passage à l'heure normale à 02:00
    now = at(8, 30, sunday)
    g = evaluate(now, cfg, Decisions(), {"hugo": DayType.WEEKEND}).kids["hugo"]
    assert g.status is KidStatus.ALLOWED
    assert g.segment is SegmentType.FREE
    assert g.segment_end == datetime(2026, 11, 1, 20, 0, tzinfo=TZ)
    assert g.segment_end.utcoffset() == timedelta(hours=-5)
    assert g.until == datetime(2026, 11, 1, 20, 0, tzinfo=TZ)


def test_shared_until_spans_owner_handoff(make_cfg):
    def modify(d):
        d["kids"][2]["profiles"]["school"]["segments"][1]["start"] = "16:00"

    cfg = make_cfg(modify)
    dec = Decisions(homework_done={"alice": TUESDAY})
    snap = evaluate(at(15, 40), cfg, dec, SCHOOL)
    # Hugo/Zoé libres jusqu'à 16:00, Alice (devoirs faits) prend le relais jusqu'à 19:00.
    assert snap.resources["tv"].open is True
    assert snap.resources["tv"].until == at(19, 0)
    assert snap.resources["switch"].until == at(19, 0)
    assert snap.resources["iphone_hugo"].until == at(16, 0)
    assert evaluate(at(16, 0), cfg, dec, SCHOOL).resources["tv"].until == at(19, 0)


def test_shared_until_stops_at_gap(make_cfg):
    def modify(d):
        d["kids"][2]["profiles"]["school"]["segments"][1]["start"] = "16:30"

    cfg = make_cfg(modify)
    dec = Decisions(homework_done={"alice": TUESDAY})
    assert evaluate(at(15, 40), cfg, dec, SCHOOL).resources["tv"].until == at(16, 0)


def test_service_exception_created_at_resource_close_is_ignored(cfg):
    # Borne : `created` égal à celui de la fermeture -> l'exception de service est ignorée (bloquée).
    dec = Decisions(exceptions=[
        exc(Target(resource_id="iphone_hugo", service="youtube"), True, id_="yt", created=at(20)),
        exc(Target(resource_id="iphone_hugo"), False, id_="stop", created=at(20)),
    ])
    snap = evaluate(at(20, 30), cfg, dec, SCHOOL)
    assert snap.resources["iphone_hugo"].blocked_services == cfg.leisure_for_resource("iphone_hugo")


def _tv_only_switch(d: dict) -> None:
    """La TV n'a qu'un interrupteur (pas d'AdGuard) ; les loisirs de tous contiennent
    le service `internet` (interrupteurs seuls)."""
    d["services"] = [*d["services"], {"id": "internet", "name": "Internet", "adguard": [],
                                      "labels": [{"label_id": "internet"}]}]
    d["default_leisure"] = [*d["default_leisure"], "internet"]
    d["resources"][0]["devices"] = [{"name": "TV", "integrations": [
        {"kind": "switch", "entity_id": "switch.tv"}]}]


def test_blocked_services_computed_without_adguard(make_cfg):
    cfg = make_cfg(_tv_only_switch)
    assert not cfg.resource("tv").has(ResourceKind.ADGUARD)
    closed = evaluate(at(20, 0), cfg, Decisions(), SCHOOL).resources["tv"]
    assert "internet" in closed.blocked_services
    opened = evaluate(at(15, 40), cfg, Decisions(), SCHOOL).resources["tv"]
    assert opened.open is True
    assert "internet" not in opened.blocked_services


def test_label_service_exception_on_non_adguard_resource(make_cfg):
    cfg = make_cfg(_tv_only_switch)
    dec = Decisions(exceptions=[
        exc(Target(resource_id="tv", service="internet"), True)])
    tv = evaluate(at(20, 0), cfg, dec, SCHOOL).resources["tv"]
    assert "internet" not in tv.blocked_services
    assert tv.opened_services == frozenset()


def _kid_with_switch_device(d: dict) -> None:
    switch_device = copy.deepcopy(d["resources"][0])
    switch_device.update(id="lampe_hugo", name="Lampe", owners=["hugo"])
    switch_device["devices"] = [{"name": "Lampe", "integrations": [
        {"kind": "switch", "entity_id": "switch.lampe"}]}]
    d["resources"].append(switch_device)


def test_adguard_signature_unchanged(make_cfg):
    cfg = make_cfg(_kid_with_switch_device)
    snap = evaluate(at(20, 0), cfg, Decisions(), SCHOOL)
    sig = rule_signature(Target(kid_id="hugo", service="youtube"), snap, cfg)
    assert [item[0] for item in sig] == ["iphone_hugo"]


def test_label_signature_covers_all_kid_resources(make_cfg):
    cfg = make_cfg(lambda d: (_extra_services(d), _kid_with_switch_device(d)))
    snap = evaluate(at(20, 0), cfg, Decisions(), SCHOOL)
    sig = rule_signature(Target(kid_id="hugo", service="internet"), snap, cfg)
    assert {item[0] for item in sig} == {"tv", "iphone_hugo", "switch", "lampe_hugo"}


def test_adguard_service_exception_ignored_on_non_adguard_resource(cfg):
    dec = Decisions(exceptions=[exc(Target(resource_id="tv", service="youtube"), False)])
    tv = evaluate(at(15, 40), cfg, dec, SCHOOL).resources["tv"]
    assert tv.blocked_services == frozenset()


def _extra_services(d: dict) -> None:
    d["services"] = [*d["services"],
                     {"id": "internet", "name": "Internet", "adguard": [],
                      "labels": [{"label_id": "internet"}]},
                     {"id": "youtube_svc", "name": "YouTube", "adguard": ["youtube"],
                      "labels": []},
                     {"id": "mixte", "name": "Mixte", "adguard": ["roblox"],
                      "labels": [{"label_id": "console"}]}]


def _tv_switch_only(d: dict, leisure: list[str]) -> None:
    _extra_services(d)
    d["default_leisure"] = leisure
    d["resources"][0]["devices"] = [{"name": "TV", "integrations": [
        {"kind": "switch", "entity_id": "switch.tv"}]}]


def test_label_only_service_kept_without_adguard(make_cfg):
    cfg = make_cfg(lambda d: _tv_switch_only(d, ["internet", "youtube_svc"]))
    tv = evaluate(at(20, 0), cfg, Decisions(), SCHOOL).resources["tv"]
    assert tv.open is False
    assert "internet" in tv.blocked_services
    assert "youtube_svc" not in tv.blocked_services


def test_mixed_service_exception_opens_on_non_adguard_resource(make_cfg):
    cfg = make_cfg(lambda d: _tv_switch_only(d, ["mixte"]))
    closed = evaluate(at(20, 0), cfg, Decisions(), SCHOOL).resources["tv"]
    assert "mixte" in closed.blocked_services
    dec = Decisions(exceptions=[exc(Target(resource_id="tv", service="mixte"), True)])
    tv = evaluate(at(20, 0), cfg, dec, SCHOOL).resources["tv"]
    assert "mixte" not in tv.blocked_services


def test_opened_services_ignores_label_only(make_cfg):
    cfg = make_cfg(lambda d: (_extra_services(d),
                              d.__setitem__("default_leisure", ["internet"])))
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_hugo", service="internet"),
                                    True)])
    state = evaluate(at(20, 0), cfg, dec, SCHOOL).resources["iphone_hugo"]
    assert state.opened_services == frozenset()


def test_unknown_service_exception_ignored(make_cfg):
    cfg = make_cfg(lambda d: d.__setitem__("services", [
        s for s in d["services"] if s["id"] != "youtube"]))
    base = evaluate(at(20, 0), cfg, Decisions(), SCHOOL).resources["iphone_hugo"]
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_hugo", service="youtube"),
                                    True)])
    snap = evaluate(at(20, 0), cfg, dec, SCHOOL)
    assert snap.resources["iphone_hugo"] == base
    assert rule_signature(Target(service="youtube"), snap, cfg) == ()
