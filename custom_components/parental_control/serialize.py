"""Instantané du moteur en dictionnaire JSON (entités, WebSocket)."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from .core.decisions import ManualException
from .core.display import exception_end, kid_timeline
from .core.model import ResourceKind

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


def serialize_snapshot(engine: ParentalEngine, display: bool = False) -> dict[str, Any]:
    """État courant : enfants (avec `closes_at`), ressources, fermetures, pause, exceptions.

    `display=True` (WebSocket, lisible sans être admin) ajoute les données d'affichage des cartes :
    identité, frise, propriétaires, loisirs, `ends_at` des exceptions et `now`. Seules des valeurs
    sûres sont copiées : jamais le code, les calendriers, les cibles de notification ni les `options`.
    """
    snap = engine.snapshot
    closures = engine.closures
    kids: dict[str, dict[str, Any]] = {}
    resources: dict[str, dict[str, Any]] = {}
    if snap is not None:
        for kid_id, kid in snap.kids.items():
            kids[kid_id] = _dataclass(kid) | {"closes_at": _value(closures.get(f"kid:{kid_id}"))}
        for resource_id, resource in snap.resources.items():
            resources[resource_id] = _dataclass(resource)
    exceptions = [serialize_exception(e) for e in engine.decisions.exceptions]
    state = {
        "kids": kids,
        "resources": resources,
        "closures": {key: _value(moment) for key, moment in closures.items()},
        "paused": engine.decisions.paused,
        "exceptions": exceptions,
    }
    if display:
        _add_display(engine, state)
    return state


def _add_display(engine: ParentalEngine, state: dict[str, Any]) -> None:
    cfg = engine.config
    snap = engine.snapshot
    now = dt_util.now()
    # Pendant `set_config` le snapshot est l'ancien alors que la config est déjà la nouvelle : les
    # enfants et ressources retirés sont omis du payload (le snapshot suivant les supprimera).
    for kind, known in (("kids", {k.id for k in cfg.kids}), ("resources", {r.id for r in cfg.resources})):
        for stale in [i for i in state[kind] if i not in known]:
            del state[kind][stale]
    for kid_id, data in state["kids"].items():
        kid = cfg.kid(kid_id)
        data |= {
            "name": kid.name,
            "emoji": kid.emoji,
            "color": kid.color,
            "timeline": kid_timeline(cfg, snap, kid_id, now),
        }
    for resource_id, data in state["resources"].items():
        resource = cfg.resource(resource_id)
        data |= {
            "name": resource.name,
            "kind": resource.kind.value,
            "owners": list(resource.owners),
            "leisure": sorted(cfg.leisure_for_resource(resource_id)),
        }
        if resource.kind is ResourceKind.NINTENDO:
            data["used_entity"] = resource.options["used_entity"]
            data["remaining_entity"] = resource.options["remaining_entity"]
    for data, exc in zip(state["exceptions"], engine.decisions.exceptions, strict=True):
        end = exception_end(cfg, snap, exc) if snap is not None else None
        data["ends_at"] = _value(end)
    state["now"] = now.isoformat()
