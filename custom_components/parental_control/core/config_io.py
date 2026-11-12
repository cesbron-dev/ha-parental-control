"""Lecture, validation et écriture de la configuration JSON (validation manuelle)."""

from __future__ import annotations

import datetime
import logging
from dataclasses import replace
from typing import Any

from .model import (
    Config,
    DayType,
    Integration,
    Kid,
    LabelLink,
    PhysicalDevice,
    Profile,
    Resource,
    ResourceKind,
    ResourceMode,
    Segment,
    SegmentType,
    Service,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_VERSION = 2
# Interrupteur : le rallumer quand l'appareil redevient autorisé (désactivé par défaut).
TURN_ON_WHEN_ALLOWED = "turn_on_when_allowed"
DEFAULT_WARN_MINUTES = 5

_REQUIRED_OPTIONS = {
    ResourceKind.MEDIA_PLAYER: ("entity_id",),
    ResourceKind.SWITCH: ("entity_id",),
    ResourceKind.ADGUARD: ("device_id",),
    ResourceKind.NINTENDO: ("device_id", "limit_entity", "remaining_entity", "used_entity"),
}

class ConfigError(ValueError):
    """Configuration invalide ; le message cite le chemin fautif."""


def _fail(path: str, message: str) -> ConfigError:
    return ConfigError(f"{path} : {message}")


def _expect_dict(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise _fail(path, "objet attendu")
    return value


def _expect_list(value: Any, path: str) -> list:
    if not isinstance(value, list):
        raise _fail(path, "liste attendue")
    return value


def _str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(path, "texte non vide attendu")
    return value


def _opt_str(value: Any, path: str) -> str | None:
    return None if value is None else _str(value, path)


def _int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _fail(path, "entier positif ou nul attendu")
    return value


def _str_list(value: Any, path: str) -> list[str]:
    return [_str(v, f"{path}[{i}]") for i, v in enumerate(_expect_list(value, path))]


def _enum(enum_cls: Any, value: Any, path: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError:
        valid = ", ".join(m.value for m in enum_cls)
        raise _fail(path, f"valeur inconnue {value!r} (attendu : {valid})") from None


def _parse_time(value: Any, path: str) -> datetime.time:
    try:
        return datetime.time.fromisoformat(_str(value, path))
    except ValueError:
        raise _fail(path, f"heure invalide {value!r} (format HH:MM)") from None


def _parse_segments(raw: Any, path: str) -> tuple[Segment, ...]:
    items = _expect_list(raw, path)
    if not items:
        raise _fail(path, "au moins un segment est requis")
    segments: list[Segment] = []
    for i, item in enumerate(items):
        p = f"{path}[{i}]"
        item = _expect_dict(item, p)
        start = _parse_time(item.get("start"), f"{p}.start")
        if i == 0 and start != datetime.time(0, 0):
            raise _fail(p, "le premier segment doit commencer à 00:00")
        if segments and start <= segments[-1].start:
            raise _fail(p, "les heures de début doivent être strictement croissantes")
        segments.append(
            Segment(
                start,
                _enum(SegmentType, item.get("type"), f"{p}.type"),
                _int(item.get("warn_minutes", DEFAULT_WARN_MINUTES), f"{p}.warn_minutes"),
            )
        )
    return tuple(segments)


def _parse_profile(raw: Any, path: str) -> Profile:
    raw = _expect_dict(raw, path)
    quota = raw.get("quota_minutes")
    return Profile(
        _parse_segments(raw.get("segments"), f"{path}.segments"),
        None if quota is None else _int(quota, f"{path}.quota_minutes"),
    )


def _parse_kid(raw: Any, path: str) -> Kid:
    raw = _expect_dict(raw, path)
    profiles_raw = _expect_dict(raw.get("profiles"), f"{path}.profiles")
    profiles: dict[DayType, Profile] = {}
    for key, value in profiles_raw.items():
        day = _enum(DayType, key, f"{path}.profiles.{key}")
        profiles[day] = _parse_profile(value, f"{path}.profiles.{key}")
    for required in (DayType.ECOLE, DayType.FIN_DE_SEMAINE):
        if required not in profiles:
            raise _fail(f"{path}.profiles", f"le profil « {required.value} » est requis")
    modes_raw = _expect_dict(raw.get("resource_modes", {}), f"{path}.resource_modes")
    modes = {
        _str(rid, f"{path}.resource_modes"): _enum(
            ResourceMode, mode, f"{path}.resource_modes.{rid}"
        )
        for rid, mode in modes_raw.items()
    }
    return Kid(
        id=_str(raw.get("id"), f"{path}.id"),
        name=_str(raw.get("name"), f"{path}.name"),
        emoji=_opt_str(raw.get("emoji"), f"{path}.emoji"),
        color=_opt_str(raw.get("color"), f"{path}.color"),
        calendar=_opt_str(raw.get("calendar"), f"{path}.calendar"),
        profiles=profiles,
        resource_modes=modes,
        leisure_add=frozenset(_str_list(raw.get("leisure_add", []), f"{path}.leisure_add")),
        leisure_remove=frozenset(
            _str_list(raw.get("leisure_remove", []), f"{path}.leisure_remove")
        ),
        on_demand_add=frozenset(_str_list(raw.get("on_demand_add", []), f"{path}.on_demand_add")),
        on_demand_remove=frozenset(
            _str_list(raw.get("on_demand_remove", []), f"{path}.on_demand_remove")
        ),
        target_label=_opt_str(raw.get("target_label"), f"{path}.target_label"),
    )


def _parse_integration(kind_raw: Any, options: dict, kind_path: str, path: str) -> Integration:
    kind = _enum(ResourceKind, kind_raw, kind_path)
    for key in _REQUIRED_OPTIONS[kind]:
        _str(options.get(key), f"{path}.{key}")
    if kind is ResourceKind.SWITCH:
        if not str(options["entity_id"]).startswith("switch."):
            raise _fail(f"{path}.entity_id", "entité switch.* attendue")
        if not isinstance(options.get(TURN_ON_WHEN_ALLOWED, False), bool):
            raise _fail(f"{path}.{TURN_ON_WHEN_ALLOWED}", "booléen attendu")
    return Integration(kind, options)


def _parse_devices(raw: Any, path: str) -> tuple[PhysicalDevice, ...]:
    devices: list[PhysicalDevice] = []
    for j, device in enumerate(_expect_list(raw, path)):
        p = f"{path}[{j}]"
        device = _expect_dict(device, p)
        name = _str(device.get("name"), f"{p}.name")
        integrations = []
        for k, item in enumerate(_expect_list(device.get("integrations"), f"{p}.integrations")):
            q = f"{p}.integrations[{k}]"
            item = _expect_dict(item, q)
            options = {key: v for key, v in item.items() if key != "kind"}
            integrations.append(_parse_integration(item.get("kind"), options, f"{q}.kind", q))
        devices.append(PhysicalDevice(name, tuple(integrations)))
    kinds = [i.kind for d in devices for i in d.integrations]
    if not kinds:
        raise _fail(path, "au moins une intégration")
    if ResourceKind.NINTENDO in kinds and len(kinds) > 1:
        raise _fail(path, "une console Nintendo ne se regroupe pas")
    return tuple(devices)


def _parse_resource(raw: Any, path: str) -> Resource:
    raw = _expect_dict(raw, path)
    devices = _parse_devices(raw.get("devices"), f"{path}.devices")
    quotas_raw = _expect_dict(raw.get("quota_minutes", {}), f"{path}.quota_minutes")
    quotas = {
        _enum(DayType, day, f"{path}.quota_minutes.{day}"): _int(
            minutes, f"{path}.quota_minutes.{day}"
        )
        for day, minutes in quotas_raw.items()
    }
    return Resource(
        id=_str(raw.get("id"), f"{path}.id"),
        name=_str(raw.get("name"), f"{path}.name"),
        owners=tuple(_str_list(raw.get("owners"), f"{path}.owners")),
        devices=devices,
        quota_minutes=quotas,
        icon=_opt_str(raw.get("icon"), f"{path}.icon"),
        target_label=_opt_str(raw.get("target_label"), f"{path}.target_label"),
    )


def _parse_services(raw: Any, path: str) -> tuple[Service, ...]:
    services: list[Service] = []
    for i, item in enumerate(_expect_list(raw, path)):
        p = f"{path}[{i}]"
        item = _expect_dict(item, p)
        service_id = _str(item.get("id"), f"{p}.id")
        if any(s.id == service_id for s in services):
            raise _fail(f"{p}.id", f"identifiant en double : {service_id!r}")
        links: list[LabelLink] = []
        for j, link in enumerate(_expect_list(item.get("labels", []), f"{p}.labels")):
            q = f"{p}.labels[{j}]"
            link = _expect_dict(link, q)
            label_id = _str(link.get("label_id"), f"{q}.label_id")
            if any(label_id == lk.label_id for lk in links):
                raise _fail(f"{q}.label_id", f"label en double : {label_id!r}")
            on_means_allowed = link.get("on_means_allowed", False)
            if not isinstance(on_means_allowed, bool):
                raise _fail(f"{q}.on_means_allowed", "booléen attendu")
            links.append(LabelLink(label_id, on_means_allowed))
        services.append(
            Service(
                id=service_id,
                name=_str(item.get("name"), f"{p}.name"),
                icon=_opt_str(item.get("icon"), f"{p}.icon"),
                adguard=tuple(_str_list(item.get("adguard", []), f"{p}.adguard")),
                labels=tuple(links),
            )
        )
    return tuple(services)


def _check_labels(
    services: tuple[Service, ...], kids: tuple[Kid, ...], resources: tuple[Resource, ...]
) -> None:
    """Un label n'est rattaché qu'à un service, et n'est pas aussi un label de cible ;
    un label de cible n'est utilisé qu'une fois."""
    attached: dict[str, str] = {}
    for i, service in enumerate(services):
        for j, link in enumerate(service.labels):
            path = f"services[{i}].labels[{j}].label_id"
            if link.label_id in attached:
                raise _fail(
                    path,
                    f"label {link.label_id!r} déjà rattaché au service {attached[link.label_id]!r}",
                )
            attached[link.label_id] = service.id
    seen: set[str] = set()
    targets = [(f"kids[{i}]", k.target_label) for i, k in enumerate(kids)] + [
        (f"resources[{i}]", r.target_label) for i, r in enumerate(resources)
    ]
    for path, label in targets:
        if label is None:
            continue
        if label in attached:
            for i, service in enumerate(services):
                for j, link in enumerate(service.labels):
                    if link.label_id == label:
                        raise _fail(
                            f"services[{i}].labels[{j}].label_id",
                            f"le label {label!r} est aussi le label de cible de {path}",
                        )
        if label in seen:
            raise _fail(f"{path}.target_label", f"label de cible déjà utilisé : {label!r}")
        seen.add(label)


def _known_services(
    ids: list[str], known: set[str], path: str, strict: bool, indexed: bool = True
) -> list[str]:
    """Identifiants de service connus ; les autres lèvent une erreur (strict) ou sont retirés."""
    kept: list[str] = []
    for i, service_id in enumerate(ids):
        if service_id in known:
            kept.append(service_id)
        elif strict:
            raise _fail(f"{path}[{i}]" if indexed else path, f"service inconnu : {service_id!r}")
        else:
            _LOGGER.info("%s : service inconnu %r retiré", path, service_id)
    return kept


def _filter_kid_services(kid: Kid, index: int, known: set[str], strict: bool) -> Kid:
    changes = {}
    for attr in ("leisure_add", "leisure_remove", "on_demand_add", "on_demand_remove"):
        value = getattr(kid, attr)
        kept = _known_services(sorted(value), known, f"kids[{index}].{attr}", strict,
                               indexed=False)
        if len(kept) != len(value):
            changes[attr] = frozenset(kept)
    return replace(kid, **changes) if changes else kid


def parse_config(data: dict) -> Config:
    """Valide le JSON de configuration du stockage (tolérant : services inconnus retirés)."""
    return _parse(data, strict=False)


def _parse(data: dict, strict: bool) -> Config:
    data = _expect_dict(data, "config")
    version = data.get("version")
    if isinstance(version, bool) or version != CONFIG_VERSION:
        raise _fail("version", f"version non prise en charge : {version!r}")

    kids = tuple(
        _parse_kid(k, f"kids[{i}]") for i, k in enumerate(_expect_list(data.get("kids", []), "kids"))
    )
    resources = tuple(
        _parse_resource(r, f"resources[{i}]")
        for i, r in enumerate(_expect_list(data.get("resources", []), "resources"))
    )

    kid_ids = [k.id for k in kids]
    for i, kid in enumerate(kids):
        if kid_ids.count(kid.id) > 1:
            raise _fail(f"kids[{i}].id", f"identifiant en double : {kid.id!r}")
    resource_ids = [r.id for r in resources]
    for i, res in enumerate(resources):
        if resource_ids.count(res.id) > 1:
            raise _fail(f"resources[{i}].id", f"identifiant en double : {res.id!r}")
        for j, owner in enumerate(res.owners):
            if owner not in kid_ids:
                raise _fail(f"resources[{i}].owners[{j}]", f"enfant inconnu : {owner!r}")
    for i, kid in enumerate(kids):
        for rid in kid.resource_modes:
            if rid not in resource_ids:
                raise _fail(f"kids[{i}].resource_modes.{rid}", f"ressource inconnue : {rid!r}")

    services = _parse_services(data.get("services", []), "services")
    _check_labels(services, kids, resources)
    known = {s.id for s in services}
    default_leisure = _known_services(
        _str_list(data.get("default_leisure", []), "default_leisure"),
        known, "default_leisure", strict,
    )
    default_on_demand = _known_services(
        _str_list(data.get("default_on_demand", []), "default_on_demand"),
        known, "default_on_demand", strict,
    )
    kids = tuple(_filter_kid_services(k, i, known, strict) for i, k in enumerate(kids))

    calendar_raw = _expect_dict(data.get("calendar_map", {}), "calendar_map")
    calendar_map = {
        _str(word, "calendar_map"): _enum(DayType, day, f"calendar_map.{word}")
        for word, day in calendar_raw.items()
    }
    request_notify = tuple(_str_list(data.get("request_notify", []), "request_notify"))
    owners_raw = _expect_dict(data.get("request_notify_owners", {}), "request_notify_owners")
    request_notify_owners: dict[str, str] = {}
    for target, user_id in owners_raw.items():
        path = f"request_notify_owners.{target}"
        if target not in request_notify:
            raise _fail(path, "cible absente de request_notify")
        request_notify_owners[target] = _str(user_id, path)
    return Config(
        kids=kids,
        resources=resources,
        default_leisure=tuple(default_leisure),
        calendar_map=calendar_map,
        notify=tuple(_str_list(data.get("notify", []), "notify")),
        default_on_demand=tuple(default_on_demand),
        request_notify=request_notify,
        request_notify_owners=request_notify_owners,
        services=services,
    )


def parse_client_config(data: dict) -> Config:
    """`parse_config` strict d'une configuration reçue d'un client (panneau, import) : un
    identifiant de service inconnu est une erreur.

    `request_notify_owners` est retiré avant validation : les propriétaires sont déterminés par
    le serveur (`parents.bind_owners`), une valeur envoyée par le client est donc ignorée —
    y compris la clé d'un téléphone que le client vient de retirer de `request_notify`. La
    validation stricte de `parse_config` reste celle du chargement depuis le stockage.
    """
    data = _expect_dict(data, "config")
    return _parse({k: v for k, v in data.items() if k != "request_notify_owners"}, strict=True)


def _dump_segment(segment: Segment) -> dict:
    out: dict[str, Any] = {"start": segment.start.strftime("%H:%M"), "type": segment.type.value}
    if segment.warn_minutes != DEFAULT_WARN_MINUTES:
        out["warn_minutes"] = segment.warn_minutes
    return out


def _dump_profile(profile: Profile) -> dict:
    out: dict[str, Any] = {}
    if profile.quota_minutes is not None:
        out["quota_minutes"] = profile.quota_minutes
    out["segments"] = [_dump_segment(s) for s in profile.segments]
    return out


def _dump_kid(kid: Kid) -> dict:
    out: dict[str, Any] = {
        "id": kid.id,
        "name": kid.name,
        "emoji": kid.emoji,
        "color": kid.color,
        "calendar": kid.calendar,
        "leisure_add": sorted(kid.leisure_add),
        "leisure_remove": sorted(kid.leisure_remove),
        "on_demand_add": sorted(kid.on_demand_add),
        "on_demand_remove": sorted(kid.on_demand_remove),
        "resource_modes": {rid: mode.value for rid, mode in kid.resource_modes.items()},
        "profiles": {day.value: _dump_profile(p) for day, p in kid.profiles.items()},
    }
    if kid.target_label is not None:
        out["target_label"] = kid.target_label
    return out


def _dump_integration(integration: Integration) -> dict:
    return {"kind": integration.kind.value, **integration.options}


def _dump_resource(resource: Resource) -> dict:
    out: dict[str, Any] = {"id": resource.id, "name": resource.name}
    if resource.icon is not None:
        out["icon"] = resource.icon
    if resource.target_label is not None:
        out["target_label"] = resource.target_label
    out["owners"] = list(resource.owners)
    out["quota_minutes"] = {day.value: m for day, m in resource.quota_minutes.items()}
    out["devices"] = [
        {"name": d.name, "integrations": [_dump_integration(i) for i in d.integrations]}
        for d in resource.devices
    ]
    return out


def _dump_service(service: Service) -> dict:
    out: dict[str, Any] = {"id": service.id, "name": service.name}
    if service.icon is not None:
        out["icon"] = service.icon
    out["adguard"] = list(service.adguard)
    out["labels"] = [
        {"label_id": lk.label_id, "on_means_allowed": lk.on_means_allowed}
        for lk in service.labels
    ]
    return out


def dump_config(cfg: Config) -> dict:
    """Sérialise le modèle au format JSON de configuration."""
    return {
        "version": CONFIG_VERSION,
        "default_leisure": list(cfg.default_leisure),
        "default_on_demand": list(cfg.default_on_demand),
        "calendar_map": {word: day.value for word, day in cfg.calendar_map.items()},
        "notify": list(cfg.notify),
        "request_notify": list(cfg.request_notify),
        "request_notify_owners": dict(cfg.request_notify_owners),
        "services": [_dump_service(s) for s in cfg.services],
        "kids": [_dump_kid(k) for k in cfg.kids],
        "resources": [_dump_resource(r) for r in cfg.resources],
    }
