from datetime import date, datetime, timedelta

from custom_components.parental_control.core.decisions import (
    Bonus,
    Decisions,
    ManualException,
    Target,
    Timer,
)
from custom_components.parental_control.core.evaluator import (
    KidStatus,
    evaluate,
    rule_signature,
    upcoming_closures,
)
from custom_components.parental_control.core.model import DayType
from tests.core.conftest import TZ, mixed_tv, weekend_quota

SATURDAY = date(2026, 10, 31)
TUESDAY = date(2026, 10, 27)
WEEKEND = {k: DayType.FIN_DE_SEMAINE for k in ("hugo", "zoe", "alice")}
ECOLE = {k: DayType.ECOLE for k in ("hugo", "zoe", "alice")}


def at(h: int, m: int = 0, day: date = SATURDAY) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


def tue(h: int, m: int = 0) -> datetime:
    return at(h, m, TUESDAY)


def with_usage(minutes: float, resource_id: str = "tv", day: date = SATURDAY) -> Decisions:
    dec = Decisions()
    dec.add_usage(resource_id, day, minutes)
    return dec


# --------------------------------------------------------------------------- TV mesurable


def test_tv_quota_open_until_exhausted(weekend_cfg):
    tv = evaluate(at(10), weekend_cfg, with_usage(170), WEEKEND).resources["tv"]
    assert tv.open is True
    assert tv.remaining_minutes == 10
    assert tv.used_minutes == 170
    assert tv.until == at(20)  # évaluer ignore l'épuisement projeté

    tv = evaluate(at(10), weekend_cfg, with_usage(180), WEEKEND).resources["tv"]
    assert tv.open is False
    assert tv.remaining_minutes == 0
    assert tv.until is None
    assert tv.reason == "Quota épuisé"


def test_tv_bonus_extends_resource_quota(weekend_cfg):
    dec = with_usage(180)
    dec.bonuses.append(Bonus(SATURDAY, 30, resource_id="tv"))
    tv = evaluate(at(10), weekend_cfg, dec, WEEKEND).resources["tv"]
    assert tv.open is True
    assert tv.remaining_minutes == 30


def test_kid_bonus_does_not_extend_tv_quota(weekend_cfg):
    dec = with_usage(180)
    dec.bonuses.append(Bonus(SATURDAY, 30, kid_id="hugo"))
    assert evaluate(at(10), weekend_cfg, dec, WEEKEND).resources["tv"].open is False


def _tv_without_device_quota(d, others_quota: int | None = 60) -> None:
    """Fin de semaine en quota ; TV sans quota d'appareil ; Hugo 120 min, Zoé et Alice
    `others_quota`."""
    weekend_quota(d)
    d["resources"][0]["quota_minutes"] = {}
    for kid in d["kids"][1:]:
        kid["profiles"]["fin_de_semaine"]["quota_minutes"] = others_quota


def test_tv_without_device_quota_uses_most_generous_kid_quota(make_cfg):
    # Décision de Marc : sans quota d'appareil pour le jour, chaque enfant apporte son
    # quota de temps d'écran ; la TV partagée retient le plus généreux (Hugo, 120 min).
    cfg = make_cfg(_tv_without_device_quota)
    tv = evaluate(at(10), cfg, with_usage(100), WEEKEND).resources["tv"]
    assert tv.open is True
    assert tv.used_minutes == 100
    assert tv.remaining_minutes == 20

    closures = upcoming_closures(at(10), cfg, with_usage(100), WEEKEND, {"tv": True})
    assert closures["resource:tv"] == at(10, 20)

    tv = evaluate(at(10), cfg, with_usage(120), WEEKEND).resources["tv"]
    assert tv.open is False
    assert tv.remaining_minutes == 0
    assert tv.reason == "Quota épuisé"


def test_tv_fallback_quota_adds_kid_and_device_bonus(make_cfg):
    dec = with_usage(120)
    dec.bonuses += [Bonus(SATURDAY, 15, kid_id="hugo"), Bonus(SATURDAY, 10, resource_id="tv")]
    tv = evaluate(at(10), make_cfg(_tv_without_device_quota), dec, WEEKEND).resources["tv"]
    assert tv.open is True
    assert tv.remaining_minutes == 25


def test_tv_fallback_counts_device_usage_not_kid_timer(make_cfg):
    dec = Decisions(timers=[Timer("hugo", at(8), at(10))])  # quota de Hugo épuisé
    tv = evaluate(at(10, 30), make_cfg(_tv_without_device_quota), dec, WEEKEND).resources["tv"]
    assert tv.open is True
    assert tv.remaining_minutes == 120


def test_tv_without_any_quota_is_unlimited(make_cfg):
    def modify(d):
        _tv_without_device_quota(d, others_quota=None)
        del d["kids"][0]["profiles"]["fin_de_semaine"]["quota_minutes"]

    tv = evaluate(at(10), make_cfg(modify), with_usage(500), WEEKEND).resources["tv"]
    assert tv.open is True
    assert tv.until == at(20)
    assert tv.remaining_minutes is None
    assert tv.used_minutes == 500


def test_device_quota_still_wins(make_cfg):
    cfg = make_cfg(lambda d: (_tv_without_device_quota(d),
                              d["resources"][0].update(quota_minutes={"fin_de_semaine": 180})))
    tv = evaluate(at(10), cfg, with_usage(150), WEEKEND).resources["tv"]
    assert tv.open is True
    assert tv.remaining_minutes == 30
    assert evaluate(at(10), cfg, with_usage(180), WEEKEND).resources["tv"].open is False


def test_mixed_device_counts_device_quota(make_cfg):
    # Lecteur + client AdGuard : compteur et budget de l'appareil, pas de minuteur.
    cfg = make_cfg(lambda d: (weekend_quota(d), mixed_tv(d)))
    tv = evaluate(at(10), cfg, with_usage(170), WEEKEND).resources["tv"]
    assert tv.open is True
    assert tv.remaining_minutes == 10
    assert tv.blocked_services == frozenset()
    tv = evaluate(at(10), cfg, with_usage(180), WEEKEND).resources["tv"]
    assert tv.open is False
    assert tv.blocked_services == cfg.leisure_for_resource("tv")


def test_adguard_only_device_unchanged(make_cfg):
    # Sans lecteur : minuteur et budget de l'enfant, comme avant (l'usage TV ne compte pas).
    cfg = make_cfg(lambda d: (_tv_without_device_quota(d), mixed_tv(d)))
    phone = evaluate(at(10), cfg, with_usage(500), WEEKEND).resources["iphone_hugo"]
    assert phone.open is False
    assert phone.reason == "En attente du minuteur"
    assert phone.remaining_minutes is None
    dec = Decisions(timers=[Timer("hugo", at(8), at(9, 50)), Timer("hugo", at(10), at(10, 30))])
    phone = evaluate(at(10), cfg, dec, WEEKEND).resources["iphone_hugo"]
    assert phone.open is True
    assert phone.until == at(10, 10)


# --------------------------------------------------------------------------- minuteur


def test_adguard_closed_without_timer(weekend_cfg):
    snap = evaluate(at(10), weekend_cfg, Decisions(), WEEKEND)
    assert snap.resources["iphone_hugo"].open is False
    assert snap.resources["iphone_hugo"].reason == "En attente du minuteur"
    g = snap.kids["hugo"]
    assert g.status is KidStatus.ATTENTE_MINUTEUR
    assert g.remaining_minutes == 120
    assert g.until is None and g.timer_end is None


def test_timer_opens_adguard_and_counts_quota(weekend_cfg):
    dec = Decisions(timers=[Timer("hugo", at(10), at(10, 30))])
    snap = evaluate(at(10, 10), weekend_cfg, dec, WEEKEND)
    g = snap.kids["hugo"]
    assert g.status is KidStatus.AUTORISE
    assert g.remaining_minutes == 110
    assert g.until == at(10, 30)
    assert g.timer_end == at(10, 30)
    phone = snap.resources["iphone_hugo"]
    assert phone.open is True
    assert phone.until == at(10, 30)
    assert phone.blocked_services == frozenset()
    # Le minuteur de Hugo n'ouvre pas l'iPhone de Zoé.
    assert snap.resources["iphone_zoe"].open is False
    assert snap.kids["zoe"].status is KidStatus.ATTENTE_MINUTEUR


def test_timer_cut_by_quota_exhaustion(weekend_cfg):
    dec = Decisions(timers=[Timer("hugo", at(8), at(9, 50)),     # 110 min consommées
                            Timer("hugo", at(10), at(10, 30))])
    snap = evaluate(at(10), weekend_cfg, dec, WEEKEND)
    assert snap.kids["hugo"].until == at(10, 10)
    assert snap.kids["hugo"].remaining_minutes == 10
    assert snap.resources["iphone_hugo"].until == at(10, 10)


def test_timer_cut_by_segment_end(weekend_cfg):
    dec = Decisions(timers=[Timer("hugo", at(19, 45), at(20, 15))])
    snap = evaluate(at(19, 50), weekend_cfg, dec, WEEKEND)
    assert snap.kids["hugo"].until == at(20)
    assert snap.resources["iphone_hugo"].until == at(20)


def test_quota_exhausted_status(weekend_cfg):
    dec = Decisions(timers=[Timer("hugo", at(8), at(10))])  # 120 min
    snap = evaluate(at(10, 30), weekend_cfg, dec, WEEKEND)
    g = snap.kids["hugo"]
    assert g.status is KidStatus.QUOTA_EPUISE
    assert g.remaining_minutes == 0
    assert g.reason == "Quota épuisé"
    assert snap.resources["iphone_hugo"].open is False
    assert snap.resources["iphone_hugo"].reason == "Quota épuisé"


def test_quota_exhausted_even_with_running_timer(weekend_cfg):
    dec = Decisions(timers=[Timer("hugo", at(8), at(12))])
    g = evaluate(at(11), weekend_cfg, dec, WEEKEND).kids["hugo"]
    assert g.status is KidStatus.QUOTA_EPUISE
    assert g.timer_end == at(12)


def test_kid_bonus_extends_kid_quota(weekend_cfg):
    dec = Decisions(timers=[Timer("hugo", at(8), at(10)), Timer("hugo", at(11), at(11, 30))],
                    bonuses=[Bonus(SATURDAY, 15, kid_id="hugo")])
    g = evaluate(at(11), weekend_cfg, dec, WEEKEND).kids["hugo"]
    assert g.status is KidStatus.AUTORISE
    assert g.remaining_minutes == 15
    assert g.until == at(11, 15)


def test_nintendo_follows_timer_in_quota_segment(weekend_cfg):
    assert evaluate(at(10), weekend_cfg, Decisions(), WEEKEND).resources["switch"].open is False
    dec = Decisions(timers=[Timer("hugo", at(10), at(10, 30))])
    switch = evaluate(at(10, 10), weekend_cfg, dec, WEEKEND).resources["switch"]
    assert switch.open is True
    assert switch.until == at(10, 30)


def test_remaining_none_outside_quota_segment(cfg):
    g = evaluate(tue(15, 40), cfg, Decisions(), ECOLE).kids["hugo"]
    assert g.remaining_minutes is None


# ----------------------------------------------------- « jusqu'à la prochaine décision »


def _tv_close_until_next_decision(cfg, created: datetime) -> ManualException:
    target = Target(resource_id="tv")
    rule = evaluate(created, cfg, Decisions(), ECOLE, apply_exceptions=False)
    return ManualException(id="e1", target=target, open=False, created=created,
                           until=None, signature=rule_signature(target, rule, cfg))


def test_until_next_decision_expires_on_rule_change(cfg):
    dec = Decisions(exceptions=[_tv_close_until_next_decision(cfg, tue(15, 40))])
    snap = evaluate(tue(16, 30), cfg, dec, ECOLE)
    assert snap.expired_exception_ids == frozenset({"e1"})
    assert snap.resources["tv"].reason != "Fermée manuellement"


def test_until_next_decision_holds_while_rule_unchanged(cfg):
    dec = Decisions(exceptions=[_tv_close_until_next_decision(cfg, tue(15, 40))])
    snap = evaluate(tue(15, 55), cfg, dec, ECOLE)
    assert snap.expired_exception_ids == frozenset()
    assert snap.resources["tv"].open is False
    assert snap.resources["tv"].reason == "Fermée manuellement"


def test_exception_without_signature_never_auto_expires(cfg):
    e = ManualException(id="e1", target=Target(resource_id="tv"), open=False,
                        created=tue(15, 40), until=None, signature=None)
    snap = evaluate(tue(16, 30), cfg, Decisions(exceptions=[e]), ECOLE)
    assert snap.expired_exception_ids == frozenset()
    assert snap.resources["tv"].reason == "Fermée manuellement"


def test_rule_signature_covers_kid_service_targets(cfg):
    rule = evaluate(tue(15, 40), cfg, Decisions(), ECOLE, apply_exceptions=False)
    assert rule_signature(Target(kid_id="zoe", service="youtube"), rule, cfg) == (
        ("iphone_zoe", "youtube", True),
    )
    assert rule_signature(Target(service="youtube"), rule, cfg) == (
        ("iphone_hugo", "youtube", True),
        ("iphone_zoe", "youtube", True),
    )
    assert rule_signature(Target(resource_id="tv"), rule, cfg) == (("tv", None, True),)


# --------------------------------------------------------------------------- fermetures à venir


def test_upcoming_closure_at_segment_end(cfg):
    closures = upcoming_closures(tue(15, 40), cfg, Decisions(), ECOLE, {})
    assert closures["kid:hugo"] == tue(16)
    assert closures["resource:tv"] == tue(16)
    assert "kid:alice" not in closures  # fermé maintenant


def test_upcoming_closure_quota_projection_only_when_in_use(weekend_cfg):
    dec = with_usage(170)
    closures = upcoming_closures(at(10), weekend_cfg, dec, WEEKEND, {"tv": True})
    assert closures["resource:tv"] == at(10, 10)
    assert dec.usage("tv", SATURDAY) == 170  # pas de mutation
    closures = upcoming_closures(at(10), weekend_cfg, dec, WEEKEND, {"tv": False})
    assert closures["resource:tv"] == at(20)


def test_upcoming_closure_timer_end(weekend_cfg):
    dec = Decisions(timers=[Timer("hugo", at(10), at(10, 30))])
    closures = upcoming_closures(at(10, 10), weekend_cfg, dec, WEEKEND, {})
    assert closures["kid:hugo"] == at(10, 30)
    assert closures["resource:iphone_hugo"] == at(10, 30)


def test_upcoming_closure_exception_until(cfg):
    e = ManualException(id="e1", target=Target(resource_id="iphone_hugo"), open=True,
                        created=tue(19, 30), until=tue(20, 15), signature=None)
    closures = upcoming_closures(tue(19, 30), cfg, Decisions(exceptions=[e]), ECOLE, {})
    assert closures["resource:iphone_hugo"] == tue(20, 15)


def test_upcoming_closure_midnight_only_if_closed_then(make_cfg):
    cfg = make_cfg(lambda d: d["kids"][0].update(resource_modes={"iphone_hugo": "libre"}))
    closures = upcoming_closures(tue(20), cfg, Decisions(), ECOLE, {})
    assert "resource:iphone_hugo" not in closures  # toujours ouvert à minuit


# --------------------------------------------------------------------------- correctifs (revue)


def test_tv_quota_falls_back_to_weekend_on_vacances(weekend_cfg):
    vacances = {k: DayType.VACANCES for k in WEEKEND}
    tv = evaluate(at(10), weekend_cfg, with_usage(500), vacances).resources["tv"]
    assert tv.open is False
    assert tv.reason == "Quota épuisé"
    tv = evaluate(at(10), weekend_cfg, with_usage(170), vacances).resources["tv"]
    assert tv.open is True
    assert tv.remaining_minutes == 10


def test_tv_quota_uses_each_owner_day_type(weekend_cfg):
    mixed = {"hugo": DayType.ECOLE, "zoe": DayType.FIN_DE_SEMAINE,
             "alice": DayType.FIN_DE_SEMAINE}
    tv = evaluate(at(10), weekend_cfg, with_usage(500), mixed).resources["tv"]
    assert tv.open is False
    tv = evaluate(at(10), weekend_cfg, with_usage(170), mixed).resources["tv"]
    assert tv.open is True
    assert tv.remaining_minutes == 10


def test_tv_remaining_none_when_no_owner_in_quota_segment(weekend_cfg):
    tv = evaluate(at(21), weekend_cfg, with_usage(170), WEEKEND).resources["tv"]
    assert tv.remaining_minutes is None
    assert tv.used_minutes == 170


def test_upcoming_closure_at_midnight_when_closed_then(make_cfg):
    def modify(d):
        d["kids"][2]["profiles"]["ecole"]["segments"] = [
            {"start": "00:00", "type": "bloque"},
            {"start": "19:00", "type": "libre"},
        ]

    closures = upcoming_closures(tue(20), make_cfg(modify), Decisions(), ECOLE, {})
    midnight = tue(0) + timedelta(days=1)
    assert closures["kid:alice"] == midnight
    assert closures["resource:tv"] == midnight


def test_upcoming_closure_kid_quota_runs_out_before_timer_end(weekend_cfg):
    dec = Decisions(timers=[Timer("hugo", at(8), at(9, 50)),     # 110 min consommées
                            Timer("hugo", at(10), at(10, 30))])
    closures = upcoming_closures(at(10), weekend_cfg, dec, WEEKEND, {})
    assert closures["kid:hugo"] == at(10, 10)
    assert closures["resource:iphone_hugo"] == at(10, 10)


# --------------------------------------------------------------------------- revue finale


def test_signature_tolerates_removed_resource(cfg, make_cfg):
    """Exception « prochaine décision » sur une ressource retirée : échue, pas d'erreur."""
    dec = Decisions(exceptions=[_tv_close_until_next_decision(cfg, tue(15, 40))])

    def drop_tv(d):
        d["resources"] = [r for r in d["resources"] if r["id"] != "tv"]

    without_tv = make_cfg(drop_tv)
    assert rule_signature(Target(resource_id="tv"),
                          evaluate(tue(15, 45), without_tv, Decisions(), ECOLE,
                                   apply_exceptions=False), without_tv) == ()
    snap = evaluate(tue(15, 45), without_tv, dec, ECOLE)
    assert snap.expired_exception_ids == frozenset({"e1"})
    assert "tv" not in snap.resources


def test_prune_unknown_removes_entries_of_removed_kids_and_resources():
    dec = Decisions(
        homework_done={"hugo": TUESDAY, "parti": TUESDAY},
        bonuses=[Bonus(TUESDAY, 10, kid_id="hugo"), Bonus(TUESDAY, 10, kid_id="parti"),
                 Bonus(TUESDAY, 10, resource_id="tv"), Bonus(TUESDAY, 10, resource_id="vieux")],
        timers=[Timer("hugo", tue(10), tue(11)), Timer("parti", tue(10), tue(11))],
        exceptions=[
            ManualException("ok", Target(resource_id="tv"), True, tue(10), None, None),
            ManualException("r", Target(resource_id="vieux"), True, tue(10), None, None),
            ManualException("k", Target(kid_id="parti", service="youtube"), True, tue(10),
                            None, None),
            ManualException("g", Target(service="youtube"), True, tue(10), None, None),
        ],
    )
    removed = dec.prune_unknown({"hugo"}, {"tv"})
    assert removed == 6
    assert dec.homework_done == {"hugo": TUESDAY}
    assert dec.bonuses == [Bonus(TUESDAY, 10, kid_id="hugo"),
                           Bonus(TUESDAY, 10, resource_id="tv")]
    assert dec.timers == [Timer("hugo", tue(10), tue(11))]
    assert [e.id for e in dec.exceptions] == ["ok", "g"]


def test_upcoming_closure_service_opened_by_exception(cfg):
    e = ManualException(id="e1", target=Target(resource_id="iphone_hugo", service="youtube"),
                        open=True, created=tue(19, 30), until=tue(20), signature=None)
    closures = upcoming_closures(tue(19, 30), cfg, Decisions(exceptions=[e]), ECOLE, {})
    assert closures["service:iphone_hugo:youtube"] == tue(20)
    assert "resource:iphone_hugo" not in closures  # la ressource reste fermée
    assert not any(k.startswith("service:iphone_zoe:") for k in closures)


def test_upcoming_closure_service_keys_absent_when_resource_closes(cfg):
    """La fermeture de la ressource entière couvre déjà ses services de loisirs."""
    closures = upcoming_closures(tue(15, 40), cfg, Decisions(), ECOLE, {})
    assert closures["resource:iphone_hugo"] == tue(16)
    assert not any(k.startswith("service:") for k in closures)
