from datetime import date, datetime

from custom_components.parental_control.core.decisions import (
    Decisions,
    ManualException,
    Target,
)
from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.core.evaluator import evaluate, upcoming_closures
from custom_components.parental_control.core.label_services import switch_blocked
from custom_components.parental_control.core.model import DayType
from tests.core.conftest import TZ, family_config_dict, mixed_tv

TUESDAY = date(2026, 10, 27)
ECOLE = {"gabin": DayType.ECOLE, "leo": DayType.ECOLE, "mael": DayType.ECOLE}
SVC = "internet"
DEMANDE = "console"


def at(h: int, m: int = 0) -> datetime:
    return datetime(TUESDAY.year, TUESDAY.month, TUESDAY.day, h, m, tzinfo=TZ)


def exc(target: Target, open_: bool, *, id_: str = "e1", created: datetime | None = None,
        until: datetime | None = None) -> ManualException:
    return ManualException(id=id_, target=target, open=open_,
                           created=created or at(12), until=until, signature=None)


def _labels(d: dict) -> None:
    d["services"] = [
        *d["services"],
        {"id": SVC, "name": "Internet", "adguard": [], "labels": [{"label_id": "internet"}]},
        {"id": DEMANDE, "name": "Console", "adguard": [], "labels": [{"label_id": "console"}]},
    ]
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
    assert _blocked(make_cfg, at(16, 30), [("kid", "gabin")]) is True


def test_kid_target_leisure_open_when_autorise(make_cfg):
    assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")]) is False


def test_kid_target_on_demand_always_blocked(make_cfg):
    assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")], service=DEMANDE) is True


def test_kid_target_opened_by_exception_on_one_of_his_devices(make_cfg):
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_gabin", service=SVC), True)])
    assert _blocked(make_cfg, at(20), [("kid", "gabin")], dec=dec) is False
    # Un appareil qui n'est pas à lui ne compte pas.
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_leo", service=SVC), True)])
    assert _blocked(make_cfg, at(20), [("kid", "gabin")], dec=dec) is True


def test_kid_target_exceptions_last_wins_and_everyone_scope(make_cfg):
    dec = Decisions(exceptions=[
        exc(Target(kid_id="gabin", service=SVC), True, id_="a", created=at(12)),
        exc(Target(service=SVC), False, id_="b", created=at(13)),
    ])
    assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")], dec=dec) is True
    dec = Decisions(exceptions=[exc(Target(service=SVC), True)])
    assert _blocked(make_cfg, at(20), [("kid", "gabin")], dec=dec) is False
    assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")], dec=Decisions(
        exceptions=[exc(Target(kid_id="leo", service=SVC), False)])) is False


def test_kid_target_paused_blocks_leisure(make_cfg):
    assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")],
                    dec=Decisions(paused=True)) is True


def test_unmanaged_service_returns_none(make_cfg):
    assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")], service="autre") is None
    assert _blocked(make_cfg, at(15, 40), [("resource", "tv")], service="autre") is None
    assert _blocked(make_cfg, at(15, 40), [("kid", "inconnu")]) is None
    assert _blocked(make_cfg, at(15, 40), []) is None


def test_any_target_blocking_wins(make_cfg):
    # Gabin autorisé, mais l'iPhone de Léo est fermé par une exception.
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_leo"), False)])
    targets = [("kid", "gabin"), ("resource", "iphone_leo")]
    assert _blocked(make_cfg, at(15, 40), targets, dec=dec) is True


def test_expired_exception_ignored(make_cfg):
    dec = Decisions(exceptions=[exc(Target(kid_id="gabin", service=SVC), True,
                                    until=at(19))])
    assert _blocked(make_cfg, at(20), [("kid", "gabin")], dec=dec) is True
    # Ignorée aussi quand le snapshot la déclare échue (« jusqu'à la prochaine décision »).
    cfg = make_cfg(_labels)
    dec = Decisions(exceptions=[exc(Target(kid_id="gabin", service=SVC), True)])
    snap = evaluate(at(20), cfg, dec, ECOLE)
    snap = type(snap)(snap.kids, snap.resources, frozenset({"e1"}))
    assert switch_blocked(at(20), cfg, dec, snap, SVC, [("kid", "gabin")]) is True


def test_label_exception_does_not_keep_mixed_device_on():
    # Une exception sur un service par label ne doit pas garder allumé le lecteur ni
    # l'interrupteur d'un appareil mixte fermé (`opened_services` : AdGuard seulement).
    d = family_config_dict()
    _labels(d)
    mixed_tv(d)
    cfg = parse_config(d)
    dec = Decisions(exceptions=[exc(Target(kid_id="gabin", service=SVC), True)])
    state = evaluate(at(20), cfg, dec, ECOLE).resources["tv"]
    assert state.open is False
    assert state.opened_services == frozenset()
    assert SVC not in state.blocked_services


def test_pause_ignores_opening_exceptions(make_cfg):
    for target in (Target(kid_id="gabin", service=SVC),
                   Target(resource_id="iphone_gabin", service=SVC),
                   Target(service=SVC)):
        dec = Decisions(paused=True, exceptions=[exc(target, True)])
        assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")], dec=dec) is True, target
        assert _blocked(make_cfg, at(15, 40), [("resource", "iphone_gabin")],
                        dec=dec) is True, target


def test_pause_keeps_closing_exceptions_and_unmanaged(make_cfg):
    dec = Decisions(paused=True, exceptions=[exc(Target(kid_id="gabin", service=SVC), False)])
    assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")], dec=dec) is True
    # La pause ne touche pas un service non géré.
    assert _blocked(make_cfg, at(15, 40), [("kid", "gabin")], dec=Decisions(paused=True),
                    service="autre") is None
    assert _blocked(make_cfg, at(15, 40), [("resource", "tv")], dec=Decisions(paused=True),
                    service="autre") is None


def test_no_closure_warning_key_for_label_services(make_cfg):
    cfg = make_cfg(_labels)
    dec = Decisions(exceptions=[exc(Target(resource_id="iphone_gabin", service=SVC), True,
                                    until=at(20, 30))])
    closures = upcoming_closures(at(20), cfg, dec, ECOLE, {})
    assert not any(k.startswith("service:") and SVC in k for k in closures)
