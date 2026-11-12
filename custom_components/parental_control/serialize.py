"""Instantané du moteur en dictionnaire JSON (entités, WebSocket)."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from .core.decisions import ManualException
from .core.display import exception_end, kid_timeline
from .core.label_services import switch_blocked
from .core.model import ResourceKind
from .core.requests import RequestStatus, action_choices

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
    """État courant : enfants (avec `closes_at`), ressources, fermetures, pause, simulation, exceptions.

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
        "simulation": engine.decisions.simulation,
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
    # Interrupteurs labellisés déjà découverts par le moteur : jamais redécouverts ici.
    switches = engine.label_switches
    # Services du parent, dans l'ordre de la config : les cartes y lisent noms et icônes.
    state["services"] = {
        s.id: {"name": s.name, "icon": s.icon, "adguard": s.has_adguard, "labels": s.has_labels}
        for s in cfg.services
    }
    for kid_id, data in state["kids"].items():
        kid = cfg.kid(kid_id)
        data |= {
            "name": kid.name,
            "emoji": kid.emoji,
            "color": kid.color,
            "timeline": kid_timeline(cfg, snap, kid_id, now),
            "on_demand": sorted(cfg.on_demand_for(kid_id)),
            "label_services": _kid_label_services(engine, switches, kid_id, now),
        }
    for resource_id, data in state["resources"].items():
        resource = cfg.resource(resource_id)
        data |= {
            "name": resource.name,
            "kind": resource.kind.value,
            "kinds": sorted(k.value for k in resource.kinds),
            "icon": resource.icon,
            "owners": list(resource.owners),
            "leisure": sorted(cfg.leisure_for_resource(resource_id)),
            "on_demand": sorted(cfg.on_demand_for_resource(resource_id)),
            "label_services": sorted({
                s["service"] for s in switches
                if {"kind": "resource", "id": resource_id} in s["targets"]
            }),
        }
        for integration in resource.integrations:
            if integration.kind is ResourceKind.NINTENDO:
                data["used_entity"] = integration.options["used_entity"]
                data["remaining_entity"] = integration.options["remaining_entity"]
    for data, exc in zip(state["exceptions"], engine.decisions.exceptions, strict=True):
        end = exception_end(cfg, snap, exc) if snap is not None else None
        data["ends_at"] = _value(end)
    state["requests_enabled"] = bool(cfg.request_notify)
    # Jamais `token`, `options`, `replace` ni `answered_by` : le jeton ne doit pas sortir.
    state["requests"] = [
        {
            "id": r.id,
            "kind": r.kind.value,
            "kid_id": r.kid_id,
            "resource_id": r.resource_id,
            "service": r.service,
            "proposed": r.proposed,
            "status": r.status.value,
            "granted": r.granted,
            "reason": r.reason,
            "expires": _value(r.expires),
        }
        for r in engine.requests.visible(now)
    ]
    state["now"] = now.isoformat()


def _kid_label_services(engine: ParentalEngine, switches: list[dict[str, Any]],
                        kid_id: str, now: datetime) -> list[dict[str, Any]]:
    """Services par label des interrupteurs qui visent l'enfant, `blocked` pour lui seul."""
    cfg, snap = engine.config, engine.snapshot
    result: dict[str, bool] = {}
    for sw in switches:
        if {"kind": "kid", "id": kid_id} not in sw["targets"] or snap is None:
            continue
        blocked = switch_blocked(now, cfg, engine.decisions, snap, sw["service"], [("kid", kid_id)])
        if blocked is not None:
            result[sw["service"]] = result.get(sw["service"], False) or blocked
    return [{"service": service, "blocked": blocked} for service, blocked in sorted(result.items())]


def serialize_requests(engine: ParentalEngine, *, can_answer: bool) -> dict[str, Any]:
    """Demandes pour l'écran « Demandes » : texte, choix des boutons, jamais le jeton."""
    now = dt_util.now()
    requests = []
    for r in engine.requests.visible(now) if engine.config is not None else ():
        pending = r.status == RequestStatus.PENDING
        requests.append(
            {
                "id": r.id,
                "kind": r.kind.value,
                "kid_id": r.kid_id,
                "message": engine.request_message(r),
                "status": r.status.value,
                "created": _value(r.created),
                "expires": _value(r.expires),
                "granted": r.granted,
                "reason": r.reason,
                "answered_by": r.answered_by,
                # Mêmes boutons que la notification ; seul l'identifiant du choix est exposé.
                "choices": [list(c) for c in action_choices(r)] if pending else [],
            }
        )
    return {"can_answer": can_answer, "requests": requests, "now": now.isoformat()}
