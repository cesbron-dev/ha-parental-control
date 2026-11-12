from datetime import datetime, timedelta, timezone

import pytest

from custom_components.parental_control.core.requests import (
    MAX_OPTIONS,
    MAX_PENDING_PER_KID,
    REQUEST_TIMEOUT,
    RESULT_DISPLAY,
    RequestBook,
    RequestError,
    RequestKind,
    RequestStatus,
    action_choices,
    choice_specs,
    duration_label,
    normalize_options,
)

TZ = timezone(timedelta(hours=-4))
NOW = datetime(2026, 11, 6, 17, 0, tzinfo=TZ)


def make(book, kind=RequestKind.OPEN, service=None, proposed=30, options=(30, 15, None)):
    return book.create(
        kind,
        "kid1",
        resource_id="res1",
        service=service,
        proposed=proposed,
        options=options,
        replace=(),
        now=NOW,
    )


def test_normalize_puts_proposed_first_and_dedupes():
    assert normalize_options(RequestKind.BONUS, 30, [15, 30, 60]) == (30, 15, 60)


def test_normalize_caps_at_six():
    res = normalize_options(RequestKind.OPEN, 15, [30, 60, 120, None, 45, 90, 10])
    assert len(res) == MAX_OPTIONS == 6
    assert res[0] == 15


def test_normalize_rejects_none_outside_open():
    with pytest.raises(RequestError) as e:
        normalize_options(RequestKind.BONUS, 30, [None])
    assert e.value.key == "invalid_request"


@pytest.mark.parametrize("value", [0, 241])
def test_normalize_rejects_out_of_range(value):
    with pytest.raises(RequestError) as e:
        normalize_options(RequestKind.TIMER, value, [])
    assert e.value.key == "invalid_request"


def test_normalize_homework_has_no_options():
    assert normalize_options(RequestKind.HOMEWORK, None, [15]) == ()


def test_create_rejects_duplicate_pending():
    book = RequestBook()
    make(book)
    with pytest.raises(RequestError) as e:
        make(book)
    assert e.value.key == "request_pending"
    assert make(book, service="youtube") is not None


def test_create_caps_pending_per_kid():
    book = RequestBook()
    services = ["youtube", "roblox", "tiktok"]
    assert MAX_PENDING_PER_KID == len(services)
    reqs = [make(book, service=s) for s in services]
    with pytest.raises(RequestError) as e:
        make(book, service="netflix")
    assert e.value.key == "too_many_requests"
    other = book.create(
        RequestKind.HOMEWORK, "kid2", resource_id=None, service=None,
        proposed=None, options=(), replace=(), now=NOW,
    )
    assert other is not None  # le plafond est par enfant
    book.finish(reqs[0], RequestStatus.REFUSED, NOW)
    assert make(book, service="netflix") is not None  # une demande résolue libère une place


def test_create_sets_fields():
    req = make(RequestBook())
    assert req.expires == NOW + REQUEST_TIMEOUT
    assert req.status == RequestStatus.PENDING
    assert req.id and req.token


def test_claim_once_with_token():
    book = RequestBook()
    req = make(book)
    assert book.claim(req.id, "mauvais", NOW) is None
    assert book.claim(req.id, req.token, NOW) is req
    assert book.claim(req.id, req.token, NOW) is None


def test_claim_after_expiry_is_none():
    book = RequestBook()
    req = make(book)
    assert book.claim(req.id, req.token, req.expires) is None


def test_expire_marks_expired():
    book = RequestBook()
    req = make(book)
    assert book.expire(NOW + timedelta(minutes=14)) == []
    assert book.expire(NOW + REQUEST_TIMEOUT) == [req]
    assert req.status == RequestStatus.EXPIRED


def test_visible_keeps_results_five_minutes():
    book = RequestBook()
    req = make(book)
    assert book.visible(NOW) == [req]
    book.claim(req.id, req.token, NOW)
    book.finish(req, RequestStatus.ACCEPTED, NOW, granted=30, answered_by="papa")
    assert book.visible(NOW + RESULT_DISPLAY - timedelta(seconds=1)) == [req]
    assert book.visible(NOW + RESULT_DISPLAY) == []
    assert book.get(req.id) is None


def test_action_choices_open():
    req = make(RequestBook())
    assert action_choices(req, "fr") == [
        ("0", "Accepter 30 min"),
        ("1", "15 min"),
        ("2", "Jusqu'au prochain changement"),
        ("refuse", "Refuser"),
    ]
    assert action_choices(req) == [
        ("0", "Accept 30 min"),
        ("1", "15 min"),
        ("2", "Until the next change"),
        ("refuse", "Refuse"),
    ]


def test_action_choices_open_without_proposal():
    req = make(RequestBook(), proposed=None, options=(None,))
    assert action_choices(req, "fr") == [
        ("0", "Accepter jusqu'au prochain changement"),
        ("refuse", "Refuser"),
    ]
    assert action_choices(req, "en") == [
        ("0", "Accept until the next change"),
        ("refuse", "Refuse"),
    ]


def test_action_choices_homework():
    req = make(RequestBook(), kind=RequestKind.HOMEWORK, proposed=None, options=())
    assert action_choices(req, "fr") == [("accept", "Accepter"), ("refuse", "Refuser")]
    assert action_choices(req, "en") == [("accept", "Accept"), ("refuse", "Refuse")]


def test_choice_specs_language_neutral():
    """Boutons sans texte : l'écran « Demandes » les rend dans la langue de l'utilisateur."""
    assert choice_specs(make(RequestBook())) == [
        {"choice": "0", "label": "accept_duration", "minutes": 30},
        {"choice": "1", "label": "duration", "minutes": 15},
        {"choice": "2", "label": "duration", "minutes": None},
        {"choice": "refuse", "label": "refuse", "minutes": None},
    ]
    assert choice_specs(make(RequestBook(), proposed=None, options=(None, 15))) == [
        {"choice": "0", "label": "accept_until", "minutes": None},
        {"choice": "1", "label": "duration", "minutes": 15},
        {"choice": "refuse", "label": "refuse", "minutes": None},
    ]
    homework = make(RequestBook(), kind=RequestKind.HOMEWORK, proposed=None, options=())
    assert choice_specs(homework) == [
        {"choice": "accept", "label": "accept", "minutes": None},
        {"choice": "refuse", "label": "refuse", "minutes": None},
    ]


def test_duration_label():
    assert duration_label(15) == "15 min"
    assert duration_label(60) == "1 h"
    assert duration_label(90) == "1 h 30 min"
    assert duration_label(120) == "2 h"
    assert duration_label(None) == "Until the next change"
    assert duration_label(None, "fr") == "Jusqu'au prochain changement"
    assert duration_label(65, "fr-CA") == "1 h 05"


def test_repr_does_not_leak_token():
    req = make(RequestBook())
    assert req.token not in repr(req)
