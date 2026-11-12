"""Modèle de données du moteur (pur, sans dépendance à Home Assistant)."""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DayType(StrEnum):
    SCHOOL = "school"
    WEEKEND = "weekend"
    DAY_OFF = "day_off"
    HOLIDAYS = "holidays"


class SegmentType(StrEnum):
    BLOCKED = "blocked"
    FREE = "free"
    AFTER_HOMEWORK = "after_homework"
    QUOTA = "quota"
    ON_DEMAND = "on_demand"


class ResourceMode(StrEnum):
    SCHEDULE = "schedule"
    ON_DEMAND = "on_demand"
    BLOCKED = "blocked"
    FREE = "free"


class ResourceKind(StrEnum):
    MEDIA_PLAYER = "media_player"
    SWITCH = "switch"
    ADGUARD = "adguard_services"
    NINTENDO = "nintendo"


@dataclass(frozen=True)
class Segment:
    """Plage de la frise ; se termine au début du suivant ou à 24:00."""

    start: datetime.time
    type: SegmentType
    warn_minutes: int = 5


@dataclass(frozen=True)
class Profile:
    segments: tuple[Segment, ...]
    quota_minutes: int | None = None  # budget journalier de l'enfant


@dataclass(frozen=True)
class Kid:
    id: str
    name: str
    emoji: str | None
    color: str | None
    calendar: str | None
    profiles: Mapping[DayType, Profile]
    resource_modes: Mapping[str, ResourceMode]
    leisure_add: frozenset[str]
    leisure_remove: frozenset[str]
    on_demand_add: frozenset[str] = frozenset()
    on_demand_remove: frozenset[str] = frozenset()
    # Label HA qui désigne les interrupteurs de cet enfant.
    target_label: str | None = None

    def profile_for(self, day: DayType) -> Profile:
        """Profil du jour ; congé pédagogique et vacances se replient sur la fin de semaine."""
        if day in self.profiles:
            return self.profiles[day]
        return self.profiles[DayType.WEEKEND]


@dataclass(frozen=True)
class Integration:
    """Intégration d'un appareil physique : `kind` et ses options (`entity_id`, `device_id`…)."""

    kind: ResourceKind
    options: Mapping[str, Any]


@dataclass(frozen=True)
class PhysicalDevice:
    """Appareil physique : une étiquette pour ranger des intégrations, sans règle propre."""

    name: str
    integrations: tuple[Integration, ...]


@dataclass(frozen=True)
class Resource:
    """Appareil logique : ses règles s'appliquent à toutes les intégrations de ses appareils."""

    id: str
    name: str
    owners: tuple[str, ...]
    devices: tuple[PhysicalDevice, ...]
    quota_minutes: Mapping[DayType, int] = field(default_factory=dict)
    icon: str | None = None
    # Label HA qui désigne les interrupteurs de cet appareil logique.
    target_label: str | None = None

    @property
    def integrations(self) -> tuple[Integration, ...]:
        """Intégrations de tous les appareils physiques, dans l'ordre de la config."""
        return tuple(i for device in self.devices for i in device.integrations)

    @property
    def kinds(self) -> frozenset[ResourceKind]:
        return frozenset(i.kind for i in self.integrations)

    def has(self, kind: ResourceKind) -> bool:
        return kind in self.kinds

    @property
    def measured(self) -> bool:
        """Temps d'usage mesuré par l'appareil lui-même : un lecteur ou un interrupteur allumé."""
        return self.has(ResourceKind.MEDIA_PLAYER) or self.has(ResourceKind.SWITCH)

    @property
    def kind(self) -> ResourceKind:
        """Type déduit : Nintendo, sinon lecteur, sinon interrupteur, sinon AdGuard."""
        for kind in (ResourceKind.NINTENDO, ResourceKind.MEDIA_PLAYER, ResourceKind.SWITCH):
            if self.has(kind):
                return kind
        return ResourceKind.ADGUARD


@dataclass(frozen=True)
class LabelLink:
    """Label HA dont les interrupteurs pilotent un service du parent."""

    label_id: str
    # Interrupteur allumé = service autorisé (sinon allumé = service coupé).
    on_means_allowed: bool = False


@dataclass(frozen=True)
class Service:
    """Service défini par le parent : regroupe des services AdGuard et/ou des labels."""

    id: str
    name: str
    icon: str | None = None
    adguard: tuple[str, ...] = ()
    labels: tuple[LabelLink, ...] = ()

    @property
    def has_adguard(self) -> bool:
        return bool(self.adguard)

    @property
    def has_labels(self) -> bool:
        return bool(self.labels)


@dataclass(frozen=True)
class Config:
    kids: tuple[Kid, ...]
    resources: tuple[Resource, ...]
    default_leisure: tuple[str, ...]
    calendar_map: Mapping[str, DayType]
    notify: tuple[str, ...]
    # Services « sur demande » : toujours bloqués, sauf autorisation explicite (exception).
    default_on_demand: tuple[str, ...] = ()
    # Services notify des parents : reçoivent les demandes de temps et y répondent.
    request_notify: tuple[str, ...] = ()
    # Propriétaire mémorisé de chaque téléphone de demandes : cible notify complète -> user_id.
    request_notify_owners: Mapping[str, str] = field(default_factory=dict)
    # Services définis par le parent.
    services: tuple[Service, ...] = ()

    def kid(self, kid_id: str) -> Kid:
        for kid in self.kids:
            if kid.id == kid_id:
                return kid
        raise KeyError(kid_id)

    def resource(self, resource_id: str) -> Resource:
        for resource in self.resources:
            if resource.id == resource_id:
                return resource
        raise KeyError(resource_id)

    def service(self, service_id: str) -> Service | None:
        for service in self.services:
            if service.id == service_id:
                return service
        return None

    def has_adguard(self, service_id: str) -> bool:
        service = self.service(service_id)
        return service is not None and service.has_adguard

    def has_labels(self, service_id: str) -> bool:
        service = self.service(service_id)
        return service is not None and service.has_labels

    def adguard_ids(self, service_ids: Iterable[str]) -> frozenset[str]:
        """Union des identifiants AdGuard des services donnés ; les inconnus sont ignorés."""
        result: frozenset[str] = frozenset()
        for service_id in service_ids:
            service = self.service(service_id)
            if service is not None:
                result |= frozenset(service.adguard)
        return result

    def service_for_label(self, label_id: str) -> tuple[Service, LabelLink] | None:
        """Premier service (dans l'ordre de la config) auquel le label est rattaché."""
        for service in self.services:
            for link in service.labels:
                if link.label_id == label_id:
                    return service, link
        return None

    def label_target(self, label_id: str) -> tuple[str, str] | None:
        """Cible d'un label : `("kid", id)` ou `("resource", id)`, `None` s'il ne cible rien."""
        for kid in self.kids:
            if kid.target_label == label_id:
                return ("kid", kid.id)
        for resource in self.resources:
            if resource.target_label == label_id:
                return ("resource", resource.id)
        return None

    def leisure_for(self, kid_id: str) -> frozenset[str]:
        kid = self.kid(kid_id)
        return (frozenset(self.default_leisure) | kid.leisure_add) - kid.leisure_remove

    def leisure_for_resource(self, resource_id: str) -> frozenset[str]:
        """Union des listes de loisirs des propriétaires de la ressource."""
        result: frozenset[str] = frozenset()
        for owner in self.resource(resource_id).owners:
            result |= self.leisure_for(owner)
        return result

    def on_demand_for(self, kid_id: str) -> frozenset[str]:
        kid = self.kid(kid_id)
        return (frozenset(self.default_on_demand) | kid.on_demand_add) - kid.on_demand_remove

    def on_demand_for_resource(self, resource_id: str) -> frozenset[str]:
        """Union des services sur demande des propriétaires : un appareil partagé bloque le
        service dès qu'il est sur demande pour l'un d'eux."""
        result: frozenset[str] = frozenset()
        for owner in self.resource(resource_id).owners:
            result |= self.on_demand_for(owner)
        return result

    def managed_services_for_resource(self, resource_id: str) -> frozenset[str]:
        """Services que le moteur bloque ou débloque sur les clients AdGuard de la ressource."""
        return self.leisure_for_resource(resource_id) | self.on_demand_for_resource(resource_id)
