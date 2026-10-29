"""Instantané du moteur en dictionnaire JSON (entités, WebSocket)."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from .core.decisions import ManualException

if TYPE_CHECKING:
    from .engine import ParentalEngine


def _value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    return value


def _dataclass(obj: Any) -> dict[str, Any]:
    return {f.name: _value(getattr(obj, f.name)) for f in fields(obj)}


def serialize_exception(exc: ManualException) -> dict[str, Any]:
    target = exc.target
    return {
        "id": exc.id,
        "target": {
            "resource_id": target.resource_id,
            "kid_id": target.kid_id,
            "service": target.service,
        },
        "open": exc.open,
        "until": _value(exc.until),
    }


def serialize_snapshot(engine: ParentalEngine) -> dict[str, Any]:
    """État courant : enfants (avec `closes_at`), ressources, fermetures, pause, exceptions."""
    snap = engine.snapshot
    closures = engine.closures
    kids: dict[str, dict[str, Any]] = {}
    resources: dict[str, dict[str, Any]] = {}
    if snap is not None:
        for kid_id, kid in snap.kids.items():
            kids[kid_id] = _dataclass(kid) | {"closes_at": _value(closures.get(f"kid:{kid_id}"))}
        for resource_id, resource in snap.resources.items():
            resources[resource_id] = _dataclass(resource)
    return {
        "kids": kids,
        "resources": resources,
        "closures": {key: _value(moment) for key, moment in closures.items()},
        "paused": engine.decisions.paused,
        "exceptions": [serialize_exception(e) for e in engine.decisions.exceptions],
    }
