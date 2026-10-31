from datetime import timedelta

from custom_components.parental_control.core.decisions import (
    Decisions,
    ManualException,
    Target,
)
from custom_components.parental_control.core.display import exception_end, kid_timeline
from custom_components.parental_control.core.evaluator import evaluate
from custom_components.parental_control.core.model import SegmentType
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
    # le premier segment du profil de Gabin commence après 00:00
    snap = evaluate(at(16, 30), cfg, Decisions(), ECOLE)
    first = cfg.kid("gabin").profile_for(snap.kids["gabin"].day_type).segments[0]
    tl = kid_timeline(cfg, snap, "gabin", at(16, 30))
    assert tl[0]["start"] == at(0, 0).isoformat()
    assert tl[0]["type"] == first.type.value


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
