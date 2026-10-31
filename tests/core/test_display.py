from dataclasses import replace
from datetime import time, timedelta

from custom_components.parental_control.core.decisions import (
    Decisions,
    ManualException,
    Target,
)
from custom_components.parental_control.core.display import exception_end, kid_timeline
from custom_components.parental_control.core.evaluator import evaluate
from custom_components.parental_control.core.model import DayType, SegmentType
from tests.core.test_evaluator_access import ECOLE, at


def _exc(target: Target, until=None) -> ManualException:
    return ManualException("e1", target, True, at(20), until, None)


def test_kid_timeline_covers_day(cfg):
    snap = evaluate(at(16, 30), cfg, Decisions(), ECOLE)
    tl = kid_timeline(cfg, snap, "gabin", at(16, 30))
    assert tl[0]["start"] == at(0, 0).isoformat()
    assert tl[-1]["end"] == (at(0, 0) + timedelta(days=1)).isoformat()
    assert all(a["end"] == b["start"] for a, b in zip(tl, tl[1:]))
    assert {s["type"] for s in tl} <= {t.value for t in SegmentType}


def test_kid_timeline_first_segment_starts_at_midnight(cfg):
    # profil dont le premier segment commence à 08:00 (jusqu'à 15:25) : la frise reste sans trou
    kid = cfg.kid("gabin")
    profile = kid.profiles[DayType.ECOLE]
    segs = (replace(profile.segments[0], start=time(8)),) + profile.segments[1:]
    kid = replace(kid, profiles={**kid.profiles, DayType.ECOLE: replace(profile, segments=segs)})
    cfg2 = replace(cfg, kids=tuple(kid if k.id == "gabin" else k for k in cfg.kids))
    snap = evaluate(at(16, 30), cfg2, Decisions(), ECOLE)
    tl = kid_timeline(cfg2, snap, "gabin", at(16, 30))
    assert tl[0]["start"] == at(0, 0).isoformat()
    assert tl[0]["end"] == tl[1]["start"] == at(15, 25).isoformat()
    assert all(a["end"] == b["start"] for a, b in zip(tl, tl[1:]))


def test_exception_end_global_takes_minimum(cfg):
    # à 16:10 Gabin est en apres_devoirs (fin 19:00), Maël aussi (fin 19:00) ; à 15:40 Gabin
    # est en libre (fin 16:00) alors que Maël est en bloque jusqu'à 16:15
    snap = evaluate(at(15, 40), cfg, Decisions(), ECOLE)
    ends = {k.segment_end for k in snap.kids.values()}
    assert len(ends) > 1
    assert exception_end(cfg, snap, _exc(Target())) == min(ends)


def test_exception_end_uses_until(cfg):
    snap = evaluate(at(20), cfg, Decisions(), ECOLE)
    exc = _exc(Target(resource_id="tv"), until=at(21))
    assert exception_end(cfg, snap, exc) == at(21)


def test_exception_end_falls_back_to_segment_end(cfg):
    snap = evaluate(at(20), cfg, Decisions(), ECOLE)
    exc = _exc(Target(resource_id="tv"))
    ends = [snap.kids[o].segment_end for o in cfg.resource("tv").owners]
    assert exception_end(cfg, snap, exc) == min(ends)
    assert exception_end(cfg, snap, _exc(Target(kid_id="gabin"))) == snap.kids["gabin"].segment_end
    assert exception_end(cfg, snap, _exc(Target())) == min(k.segment_end for k in snap.kids.values())


def test_exception_ends_without_change(cfg):
    snap = evaluate(at(20), cfg, Decisions(), ECOLE)
    assert exception_end(cfg, snap, _exc(Target(kid_id="inconnu"))) is None
    assert exception_end(cfg, snap, _exc(Target(resource_id="inconnue"))) is None
