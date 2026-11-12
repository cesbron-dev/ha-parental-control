"""Découverte des interrupteurs labellisés (adaptateur Home Assistant).

Tout `switch` portant un label rattaché à un service du parent (`Service.labels`) est piloté
comme ce service : ses autres labels, s'ils ciblent un enfant ou un appareil, disent pour qui.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr

from .core.label_services import LabelTarget
from .core.model import Config, LabelLink, Service

PROBLEM_NO_TARGET = "no_target"
PROBLEM_UNKNOWN_LABEL = "unknown_label"


@dataclass(frozen=True)
class LabelSwitch:
    entity_id: str
    service: str
    on_means_allowed: bool
    targets: tuple[LabelTarget, ...]


@dataclass(frozen=True)
class LabelSwitchIssue:
    entity_id: str
    service: str
    problem: str


def discover(
    hass: HomeAssistant, cfg: Config
) -> tuple[list[LabelSwitch], list[LabelSwitchIssue]]:
    """Interrupteurs actifs portant un label de service, et les problèmes rencontrés.

    Un interrupteur n'est piloté que pour un service : s'il porte plusieurs labels rattachés,
    le premier dont le label existe l'emporte (ordre de `cfg.services`, puis des labels).
    """
    switches: list[LabelSwitch] = []
    issues: list[LabelSwitchIssue] = []
    if not any(s.has_labels for s in cfg.services):
        return switches, issues
    labels = lr.async_get(hass)
    # HA retire un label supprimé de toutes les entités : le problème ne tient pas à un interrupteur.
    # Un seul problème par service, même si plusieurs de ses labels manquent.
    for service in cfg.services:
        if any(labels.async_get_label(link.label_id) is None for link in service.labels):
            issues.append(LabelSwitchIssue("", service.id, PROBLEM_UNKNOWN_LABEL))
    order = {s.id: i for i, s in enumerate(cfg.services)}
    entries = sorted(
        (e for e in er.async_get(hass).entities.values()
         if e.domain == "switch" and e.disabled_by is None and e.labels),
        key=lambda e: e.entity_id,
    )
    for entry in entries:
        found = [
            pair for label_id in entry.labels
            if (pair := cfg.service_for_label(label_id)) is not None
        ]
        found.sort(key=lambda p: (order[p[0].id], p[0].labels.index(p[1])))
        attached = {link.label_id for _, link in found}
        targets = tuple(sorted(
            t for label_id in entry.labels - attached
            if (t := cfg.label_target(label_id)) is not None
        ))
        chosen: tuple[Service, LabelLink] | None = next(
            (p for p in found if labels.async_get_label(p[1].label_id) is not None), None
        )
        if chosen is None:
            continue
        service, link = chosen
        if not targets:
            issues.append(LabelSwitchIssue(entry.entity_id, service.id, PROBLEM_NO_TARGET))
            continue
        switches.append(LabelSwitch(entry.entity_id, service.id, link.on_means_allowed, targets))
    return switches, issues
