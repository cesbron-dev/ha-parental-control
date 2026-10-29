from datetime import date

from custom_components.parental_control.core.daytype import AllDayEvent, day_type
from custom_components.parental_control.core.model import DayType

CMAP = {
    "pédagogique": DayType.CONGE_PEDA,
    "vacances": DayType.VACANCES,
    "relâche": DayType.VACANCES,
}


def ev(summary, start, end):
    return AllDayEvent(summary, start, end)


def test_weekday_default():
    assert day_type(date(2026, 10, 27), [], CMAP) == DayType.ECOLE
    assert day_type(date(2026, 10, 31), [], CMAP) == DayType.FIN_DE_SEMAINE


def test_conge_peda_matches_accent_insensitive():
    events = [ev("Congé PEDAGOGIQUE", date(2026, 10, 27), date(2026, 10, 28))]
    assert day_type(date(2026, 10, 27), events, CMAP) == DayType.CONGE_PEDA


def test_multi_day_vacation_covers_weekend():
    events = [ev("Vacances de Noël", date(2026, 12, 21), date(2027, 1, 5))]
    assert day_type(date(2026, 12, 26), events, CMAP) == DayType.VACANCES


def test_end_is_exclusive():
    events = [ev("Congé pédagogique", date(2026, 10, 27), date(2026, 10, 28))]
    assert day_type(date(2026, 10, 28), events, CMAP) == DayType.ECOLE


def test_vacances_beats_conge_peda():
    events = [
        ev("Congé pédagogique", date(2026, 10, 27), date(2026, 10, 28)),
        ev("Vacances", date(2026, 10, 26), date(2026, 10, 30)),
    ]
    assert day_type(date(2026, 10, 27), events, CMAP) == DayType.VACANCES


def test_unmapped_event_ignored():
    events = [ev("Photo scolaire", date(2026, 10, 27), date(2026, 10, 28))]
    assert day_type(date(2026, 10, 27), events, CMAP) == DayType.ECOLE


def test_ecole_mapping_overrides_weekend_default_but_loses_to_conge():
    cmap = {**CMAP, "classe samedi": DayType.ECOLE}
    sat = date(2026, 10, 31)
    events = [ev("Classe samedi", sat, date(2026, 11, 1))]
    assert day_type(sat, events, cmap) == DayType.ECOLE
    events.append(ev("Congé pédagogique", sat, date(2026, 11, 1)))
    assert day_type(sat, events, cmap) == DayType.CONGE_PEDA


def test_ecole_vs_weekend_events_earliest_start_wins():
    cmap = {"classe": DayType.ECOLE, "relaxe": DayType.FIN_DE_SEMAINE}
    d = date(2026, 10, 27)
    events = [
        ev("relaxe", date(2026, 10, 27), date(2026, 10, 28)),
        ev("classe", date(2026, 10, 26), date(2026, 10, 28)),
    ]
    assert day_type(d, events, cmap) == DayType.ECOLE
    events = [
        ev("classe", date(2026, 10, 27), date(2026, 10, 28)),
        ev("relaxe", date(2026, 10, 27), date(2026, 10, 28)),
    ]
    # tie on start: summary alphabetical -> "classe"
    assert day_type(d, events, cmap) == DayType.ECOLE
