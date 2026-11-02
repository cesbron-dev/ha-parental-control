"""Modèle de données du moteur (pur, sans dépendance à Home Assistant)."""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DayType(StrEnum):
    ECOLE = "ecole"
    FIN_DE_SEMAINE = "fin_de_semaine"
    CONGE_PEDA = "conge_peda"
    VACANCES = "vacances"


class SegmentType(StrEnum):
    BLOQUE = "bloque"
    LIBRE = "libre"
    APRES_DEVOIRS = "apres_devoirs"
    QUOTA = "quota"
    SUR_DEMANDE = "sur_demande"


class ResourceMode(StrEnum):
    SUIT_FRISE = "suit_frise"
    SUR_DEMANDE = "sur_demande"
    BLOQUE = "bloque"
    LIBRE = "libre"


class ResourceKind(StrEnum):
    MEDIA_PLAYER = "media_player"
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

    def profile_for(self, day: DayType) -> Profile:
        """Profil du jour ; congé pédagogique et vacances se replient sur la fin de semaine."""
        if day in self.profiles:
            return self.profiles[day]
        return self.profiles[DayType.FIN_DE_SEMAINE]


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
    def kind(self) -> ResourceKind:
        """Type déduit : Nintendo s'il y en a une, sinon lecteur s'il y en a un, sinon AdGuard."""
        if self.has(ResourceKind.NINTENDO):
            return ResourceKind.NINTENDO
        if self.has(ResourceKind.MEDIA_PLAYER):
            return ResourceKind.MEDIA_PLAYER
        return ResourceKind.ADGUARD


@dataclass(frozen=True)
class Config:
    kids: tuple[Kid, ...]
    resources: tuple[Resource, ...]
    default_leisure: tuple[str, ...]
    calendar_map: Mapping[str, DayType]
    notify: tuple[str, ...]

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

    def leisure_for(self, kid_id: str) -> frozenset[str]:
        kid = self.kid(kid_id)
        return (frozenset(self.default_leisure) | kid.leisure_add) - kid.leisure_remove

    def leisure_for_resource(self, resource_id: str) -> frozenset[str]:
        """Union des listes de loisirs des propriétaires de la ressource."""
        result: frozenset[str] = frozenset()
        for owner in self.resource(resource_id).owners:
            result |= self.leisure_for(owner)
        return result
