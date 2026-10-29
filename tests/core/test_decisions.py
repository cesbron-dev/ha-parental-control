import json
from datetime import date, datetime, timedelta, timezone

from custom_components.parental_control.core.decisions import (
    Bonus,
    Decisions,
    ManualException,
    Target,
    Timer,
)

TZ = timezone(timedelta(hours=-4))


def dt(day, h, m=0):
    return datetime(2026, 10, day, h, m, tzinfo=TZ)


def exc(until, id="e1", signature=None):
    return ManualException(
        id=id, target=Target(resource_id="tv"), open=True,
        created=dt(27, 23, 50), until=until, signature=signature,
    )


def test_round_trip_all_fields():
    d = Decisions(paused=True)
    d.homework_done["max"] = date(2026, 10, 28)
    d.bonuses.append(Bonus(date(2026, 10, 28), 15, kid_id="max"))
    d.bonuses.append(Bonus(date(2026, 10, 28), 10, resource_id="switch"))
    d.exceptions.append(exc(dt(28, 0, 20), signature=(("a", True), ("b", "c"))))
    d.exceptions.append(ManualException(
        "e2", Target(kid_id="max", service="youtube"), False, dt(28, 9), None, None))
    d.timers.append(Timer("max", dt(28, 14), dt(28, 14, 30)))
    d.add_usage("switch", date(2026, 10, 28), 12.5)
    raw = json.loads(json.dumps(d.to_dict()))
    assert Decisions.from_dict(raw) == d
    assert Decisions.from_dict(raw).exceptions[0].signature == (("a", True), ("b", "c"))


def test_purge_drops_yesterday_homework_and_bonus():
    d = Decisions()
    d.homework_done["max"] = date(2026, 10, 27)
    d.homework_done["lea"] = date(2026, 10, 28)
    d.bonuses += [Bonus(date(2026, 10, 27), 5), Bonus(date(2026, 10, 28), 5)]
    d.add_usage("tv", date(2026, 10, 27), 3)
    d.add_usage("tv", date(2026, 10, 28), 4)
    d.timers.append(Timer("max", dt(27, 14), dt(27, 15)))
    d.purge(dt(28, 8))
    assert d.homework_done == {"lea": date(2026, 10, 28)}
    assert d.bonuses == [Bonus(date(2026, 10, 28), 5)]
    assert d.usage("tv", date(2026, 10, 27)) == 0.0
    assert d.usage("tv", date(2026, 10, 28)) == 4
    assert d.timers == []


def test_purge_keeps_exception_crossing_midnight():
    d = Decisions(exceptions=[exc(dt(28, 0, 20))])
    d.purge(dt(28, 0, 5))
    assert len(d.exceptions) == 1
    d.purge(dt(28, 0, 21))
    assert d.exceptions == []


def test_purge_keeps_until_next_decision_exception():
    d = Decisions(exceptions=[exc(None)])
    d.purge(dt(30, 12))
    assert len(d.exceptions) == 1


def test_kid_timer_minutes_counts_elapsed_only():
    d = Decisions(timers=[Timer("max", dt(28, 14), dt(28, 14, 30))])
    assert d.kid_timer_minutes("max", date(2026, 10, 28), dt(28, 14, 10)) == 10.0
    assert d.kid_timer_minutes("max", date(2026, 10, 28), dt(28, 15)) == 30.0
    assert d.kid_timer_minutes("lea", date(2026, 10, 28), dt(28, 15)) == 0.0
    assert d.active_timer("max", dt(28, 14, 10)) is not None
    assert d.active_timer("max", dt(28, 15)) is None


def test_bonus_minutes_filters_target_and_day():
    d = Decisions(bonuses=[
        Bonus(date(2026, 10, 28), 10, kid_id="max"),
        Bonus(date(2026, 10, 28), 5, kid_id="max"),
        Bonus(date(2026, 10, 28), 20, resource_id="tv"),
        Bonus(date(2026, 10, 27), 99, kid_id="max"),
    ])
    day = date(2026, 10, 28)
    assert d.bonus_minutes(day, kid_id="max") == 15
    assert d.bonus_minutes(day, resource_id="tv") == 20
    assert d.bonus_minutes(day, kid_id="lea") == 0
