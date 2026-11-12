from datetime import date

from custom_components.parental_control.core.daytype import AllDayEvent, day_type
from custom_components.parental_control.core.model import DayType

CMAP = {
    "pédagogique": DayType.DAY_OFF,
    "vacances": DayType.HOLIDAYS,
    "relâche": DayType.HOLIDAYS,
}


def ev(summary, start, end):
    return AllDayEvent(summary, start, end)


def test_weekday_default():
    assert day_type(date(2026, 10, 27), [], CMAP) == DayType.SCHOOL
    assert day_type(date(2026, 10, 31), [], CMAP) == DayType.WEEKEND


def test_day_off_matches_accent_insensitive():
    events = [ev("Congé PEDAGOGIQUE", date(2026, 10, 27), date(2026, 10, 28))]
    assert day_type(date(2026, 10, 27), events, CMAP) == DayType.DAY_OFF


def test_multi_day_vacation_covers_weekend():
    events = [ev("Vacances de Noël", date(2026, 12, 21), date(2027, 1, 5))]
    assert day_type(date(2026, 12, 26), events, CMAP) == DayType.HOLIDAYS


def test_end_is_exclusive():
    events = [ev("Congé pédagogique", date(2026, 10, 27), date(2026, 10, 28))]
    assert day_type(date(2026, 10, 28), events, CMAP) == DayType.SCHOOL


def test_holidays_beats_day_off():
    events = [
        ev("Congé pédagogique", date(2026, 10, 27), date(2026, 10, 28)),
        ev("Vacances", date(2026, 10, 26), date(2026, 10, 30)),
    ]
    assert day_type(date(2026, 10, 27), events, CMAP) == DayType.HOLIDAYS


def test_unmapped_event_ignored():
    events = [ev("Photo scolaire", date(2026, 10, 27), date(2026, 10, 28))]
    assert day_type(date(2026, 10, 27), events, CMAP) == DayType.SCHOOL


def test_school_mapping_overrides_weekend_default_but_loses_to_day_off():
    cmap = {**CMAP, "classe samedi": DayType.SCHOOL}
    sat = date(2026, 10, 31)
    events = [ev("Classe samedi", sat, date(2026, 11, 1))]
    assert day_type(sat, events, cmap) == DayType.SCHOOL
    events.append(ev("Congé pédagogique", sat, date(2026, 11, 1)))
    assert day_type(sat, events, cmap) == DayType.DAY_OFF


def test_school_vs_weekend_events_earliest_start_wins():
    cmap = {"classe": DayType.SCHOOL, "relaxe": DayType.WEEKEND}
    d = date(2026, 10, 27)
    events = [
        ev("relaxe", date(2026, 10, 27), date(2026, 10, 28)),
        ev("classe", date(2026, 10, 26), date(2026, 10, 28)),
    ]
    assert day_type(d, events, cmap) == DayType.SCHOOL
    events = [
        ev("classe", date(2026, 10, 27), date(2026, 10, 28)),
        ev("relaxe", date(2026, 10, 27), date(2026, 10, 28)),
    ]
    # tie on start: summary alphabetical -> "classe"
    assert day_type(d, events, cmap) == DayType.SCHOOL
