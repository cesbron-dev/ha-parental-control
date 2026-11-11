"""État voulu d'un interrupteur labellisé (pur).

Un interrupteur HA porte un label de service (`label:...`) et un ou plusieurs labels de cible
(enfant ou appareil logique). `switch_blocked` dit s'il doit être bloqué.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from .decisions import Decisions
from .evaluator import KidStatus, Snapshot, _active_exceptions
from .model import Config

# `("kid", id)` ou `("resource", id)`, comme `Config.label_target`.
LabelTarget = tuple[str, str]


def _kid_blocked(now: datetime, cfg: Config, dec: Decisions, snap: Snapshot,
                 service: str, kid_id: str) -> bool | None:
    leisure = service in cfg.leisure_for(kid_id)
    on_demand = service in cfg.on_demand_for(kid_id)
    if not (leisure or on_demand):
        return None
    blocked = on_demand or snap.kids[kid_id].status is not KidStatus.AUTORISE
    devices = {r.id for r in cfg.resources if kid_id in r.owners}
    for e in _active_exceptions(now, dec, snap.expired_exception_ids):
        t = e.target
        if t.service != service:
            continue
        if t.kid_id == kid_id or (t.resource_id in devices) or (
                t.kid_id is None and t.resource_id is None):
            blocked = not e.open
    return blocked


def _resource_blocked(cfg: Config, snap: Snapshot, service: str,
                      resource_id: str) -> bool | None:
    if service not in cfg.managed_services_for_resource(resource_id):
        return None
    return service in snap.resources[resource_id].blocked_services


def switch_blocked(now: datetime, cfg: Config, dec: Decisions, snap: Snapshot,
                   service: str, targets: Sequence[LabelTarget]) -> bool | None:
    """`None` : service géré pour aucune cible (interrupteur laissé tel quel) ; sinon `True`
    dès qu'une cible gérée le bloque."""
    result: bool | None = None
    for kind, target_id in targets:
        if kind == "kid":
            if all(k.id != target_id for k in cfg.kids):
                continue
            blocked = _kid_blocked(now, cfg, dec, snap, service, target_id)
        else:
            if all(r.id != target_id for r in cfg.resources):
                continue
            blocked = _resource_blocked(cfg, snap, service, target_id)
        if blocked is None:
            continue
        result = blocked if result is None else (result or blocked)
    return result
