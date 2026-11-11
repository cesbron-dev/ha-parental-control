from datetime import date, datetime

from custom_components.parental_control.core.decisions import (
    Decisions,
    ManualException,
    Target,
)
from custom_components.parental_control.core.evaluator import evaluate
from custom_components.parental_control.core.label_services import switch_blocked
from custom_components.parental_control.core.model import DayType
from tests.core.conftest import TZ

TUESDAY = date(2026, 10, 27)
ECOLE = {"hugo": DayType.ECOLE, "zoe": DayType.ECOLE, "alice": DayType.ECOLE}
SVC = "label:internet"
DEMANDE = "label:console"


def at(h: int, m: int = 0) -> datetime:
    return datetime(TUESDAY.year, TUESDAY.month, TUESDAY.day, h, m, tzinfo=TZ)


def exc(target: Target, open_: bool, *, id_: str = "e1", created: datetime | None = None,
        until: datetime | None = None) -> ManualException:
    return ManualException(id=id_, target=target, open=open_,
                           created=created or at(12), until=until, signature=None)


def _labels(d: dict) -> None:
    d["default_leisure"] = [*d["default_leisure"], SVC]
    d["default_on_demand"] = [DEMANDE]


def _blocked(make_cfg, now, targets, *, dec=None, service=SVC):
    cfg = make_cfg(_labels)
    dec = dec or Decisions()
    snap = evaluate(now, cfg, dec, ECOLE)
    return switch_blocked(now, cfg, dec, snap, service, targets)


def test_resource_target_follows_blocked_services(make_cfg):
    assert _blocked(make_cfg, at(20), [("resource", "tv")]) is True
    assert _blocked(make_cfg, at(15, 40), [("resource", "tv")]) is False


def test_kid_target_leisure_blocked_when_kid_not_autorise(make_cfg):
    assert _blocked(make_cfg, at(16, 30), [("kid", "hugo")]) is True


def test_kid_target_leisure_open_when_autorise(make_cfg):
    assert _blocked(make_cfg, at(15, 40), [("kid", "hugo")]) is False


def test_kid_target_on_demand_always_blocked(make_cfg):
    assert _blocked(make_cfg, at(15, 40), [("kid", "hugo")], service=DEMANDE) is True


def test_kid_target_opened_by_exception_on_one_of_his_devices(make_cfg):
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_hugo", service=SVC), True)])
    assert _blocked(make_cfg, at(20), [("kid", "hugo")], dec=dec) is False
    # Un appareil qui n'est pas à lui ne compte pas.
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_zoe", service=SVC), True)])
    assert _blocked(make_cfg, at(20), [("kid", "hugo")], dec=dec) is True


def test_kid_target_exceptions_last_wins_and_everyone_scope(make_cfg):
    dec = Decisions(exceptions=[
        exc(Target(kid_id="hugo", service=SVC), True, id_="a", created=at(12)),
        exc(Target(service=SVC), False, id_="b", created=at(13)),
    ])
    assert _blocked(make_cfg, at(15, 40), [("kid", "hugo")], dec=dec) is True
    dec = Decisions(exceptions=[exc(Target(service=SVC), True)])
    assert _blocked(make_cfg, at(20), [("kid", "hugo")], dec=dec) is False
    assert _blocked(make_cfg, at(15, 40), [("kid", "hugo")], dec=Decisions(
        exceptions=[exc(Target(kid_id="zoe", service=SVC), False)])) is False


def test_kid_target_paused_blocks_leisure(make_cfg):
    assert _blocked(make_cfg, at(15, 40), [("kid", "hugo")],
                    dec=Decisions(paused=True)) is True


def test_unmanaged_service_returns_none(make_cfg):
    assert _blocked(make_cfg, at(15, 40), [("kid", "hugo")], service="label:autre") is None
    assert _blocked(make_cfg, at(15, 40), [("resource", "tv")], service="label:autre") is None
    assert _blocked(make_cfg, at(15, 40), [("kid", "inconnu")]) is None
    assert _blocked(make_cfg, at(15, 40), []) is None


def test_any_target_blocking_wins(make_cfg):
    # Hugo autorisé, mais l'iPhone de Zoé est fermé par une exception.
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_zoe"), False)])
    targets = [("kid", "hugo"), ("resource", "iphone_zoe")]
    assert _blocked(make_cfg, at(15, 40), targets, dec=dec) is True


def test_expired_exception_ignored(make_cfg):
    dec = Decisions(exceptions=[exc(Target(kid_id="hugo", service=SVC), True,
                                    until=at(19))])
    assert _blocked(make_cfg, at(20), [("kid", "hugo")], dec=dec) is True
    # Ignorée aussi quand le snapshot la déclare échue (« jusqu'à la prochaine décision »).
    cfg = make_cfg(_labels)
    dec = Decisions(exceptions=[exc(Target(kid_id="hugo", service=SVC), True)])
    snap = evaluate(at(20), cfg, dec, ECOLE)
    snap = type(snap)(snap.kids, snap.resources, frozenset({"e1"}))
    assert switch_blocked(at(20), cfg, dec, snap, SVC, [("kid", "hugo")]) is True
