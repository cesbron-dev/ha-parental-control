"""Découverte des interrupteurs labellisés (adaptateur Home Assistant).

Tout `switch` portant un label de service déclaré (`Config.label_services`) est piloté comme un
service : ses autres labels, s'ils ciblent un enfant ou un appareil, disent pour qui.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr

from .core.label_services import LabelTarget
from .core.model import Config, LabelService

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


def label_name(hass: HomeAssistant, label_id: str) -> str:
    """Nom du label dans le registre des labels (jamais stocké), à défaut son identifiant."""
    label = lr.async_get(hass).async_get_label(label_id)
    return label.name if label is not None else label_id


def discover(
    hass: HomeAssistant, cfg: Config
) -> tuple[list[LabelSwitch], list[LabelSwitchIssue]]:
    """Interrupteurs actifs portant un label de service, et les problèmes rencontrés.

    Un interrupteur n'est piloté que pour un service : s'il en porte plusieurs, le premier
    de `cfg.label_services` qui est utilisable l'emporte.
    """
    switches: list[LabelSwitch] = []
    issues: list[LabelSwitchIssue] = []
    if not cfg.label_services:
        return switches, issues
    labels = lr.async_get(hass)
    # HA retire un label supprimé de toutes les entités : le problème ne tient pas à un interrupteur.
    for service in cfg.label_services:
        if labels.async_get_label(service.label_id) is None:
            issues.append(LabelSwitchIssue("", service.service, PROBLEM_UNKNOWN_LABEL))
    entries = sorted(
        (e for e in er.async_get(hass).entities.values()
         if e.domain == "switch" and e.disabled_by is None and e.labels),
        key=lambda e: e.entity_id,
    )
    for entry in entries:
        service_labels = [s for s in cfg.label_services if s.label_id in entry.labels]
        chosen: LabelService | None = None
        service_ids = {s.label_id for s in service_labels}
        targets = tuple(sorted(
            t for label_id in entry.labels - service_ids
            if (t := cfg.label_target(label_id)) is not None
        ))
        for service in service_labels:
            if labels.async_get_label(service.label_id) is not None:
                chosen = service
                break
        if chosen is None:
            continue
        if not targets:
            issues.append(LabelSwitchIssue(entry.entity_id, chosen.service, PROBLEM_NO_TARGET))
            continue
        switches.append(
            LabelSwitch(entry.entity_id, chosen.service, chosen.on_means_allowed, targets)
        )
    return switches, issues
