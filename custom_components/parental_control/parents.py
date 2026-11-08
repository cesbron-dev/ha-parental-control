"""Qui est parent : un administrateur HA, ou le propriétaire mémorisé d'un téléphone de demandes.

Le nom `notify.mobile_app_<x>` vient du nom de l'appareil, que tout utilisateur choisit. Un
téléphone de `request_notify` ne donne donc de droits que si le propriétaire **actuel** de
l'unique appareil de ce nom est le propriétaire **mémorisé** dans la configuration
(`request_notify_owners`), déterminé par le serveur et jamais reçu du client.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import DOMAIN
from .core.config_io import ConfigError
from .core.model import Config

if TYPE_CHECKING:
    from .engine import ParentalEngine

_LOGGER = logging.getLogger(__name__)

MOBILE_APP = "mobile_app"
MOBILE_APP_SERVICE = "mobile_app_"
# Cibles déjà signalées comme ambiguës : `is_parent` est appelé à chaque action, on n'avertit
# qu'une fois par cible et par exécution de HA.
_AMBIGUOUS_WARNED = f"{DOMAIN}_ambiguous_phones_warned"


def _is_mobile_app_target(target: str) -> bool:
    domain, _, service = target.partition(".")
    return domain == "notify" and service.startswith(MOBILE_APP_SERVICE)


def current_phone_owners(hass: HomeAssistant, targets: Iterable[str]) -> dict[str, list[str]]:
    """Cible `notify.mobile_app_<x>` → `user_id` des entrées `mobile_app` qui y mènent.

    Les cibles qui ne sont pas des téléphones `mobile_app` sont absentes du résultat ; un
    téléphone sans appareil a une liste vide. Une entrée sans `user_id` valide compte comme
    `""` : elle rend le nom ambigu sans jamais désigner personne.
    """
    owners: dict[str, list[str]] = {t: [] for t in targets if _is_mobile_app_target(t)}
    for entry in hass.config_entries.async_entries(MOBILE_APP):
        device_name = entry.data.get("device_name")
        if not isinstance(device_name, str):
            continue
        target = f"notify.{MOBILE_APP_SERVICE}{slugify(device_name)}"
        if target in owners:
            user_id = entry.data.get("user_id")
            owners[target].append(user_id if isinstance(user_id, str) else "")
    return owners


def trusted_phone_owners(hass: HomeAssistant, cfg: Config | None) -> set[str]:
    """Propriétaires mémorisés dont le téléphone mène aujourd'hui à eux seuls."""
    if cfg is None:
        return set()
    users: set[str] = set()
    warned: set[str] = hass.data.setdefault(_AMBIGUOUS_WARNED, set())
    for target, current in current_phone_owners(hass, cfg.request_notify).items():
        if len(current) > 1:
            if target in warned:
                continue
            warned.add(target)
            _LOGGER.warning(
                "%s : plusieurs appareils mobile_app portent ce nom ; ce téléphone ne donne "
                "aucun droit de parent ni de réponse aux demandes",
                target,
            )
            continue
        remembered = cfg.request_notify_owners.get(target)
        if remembered and current == [remembered]:
            users.add(remembered)
    return users


async def is_parent(hass: HomeAssistant, cfg: Config | None, user_id: str | None) -> bool:
    """Administrateur, ou propriétaire reconnu d'un téléphone de demandes.

    `user_id is None` (automatisation, système) ⇒ `False` : à l'appelant de traiter ce cas.
    """
    if user_id is None:
        return False
    user = await hass.auth.async_get_user(user_id)
    if user is None or not user.is_active:
        return False
    return user.is_admin or user_id in trusted_phone_owners(hass, cfg)


async def phone_status(hass: HomeAssistant, cfg: Config) -> dict[str, dict]:
    """État de chaque téléphone `mobile_app` de la liste, pour le panneau.

    `unbound` : aucun propriétaire mémorisé ; `missing` : aucun appareil de ce nom ;
    `ambiguous` : plusieurs appareils ; `changed` : appareil d'un autre compte ; `ok` sinon.
    `owner_name` : nom HA du propriétaire mémorisé (un parent non administrateur ne peut pas
    lister les utilisateurs), `None` s'il n'y en a pas ou s'il n'existe plus.
    `current_name` : nom HA du propriétaire actuel de l'unique appareil de ce nom — celui qui
    deviendrait parent en réassociant —, `None` sans appareil, avec plusieurs, ou inconnu.
    """
    result: dict[str, dict] = {}
    for target, current in current_phone_owners(hass, cfg.request_notify).items():
        owner = cfg.request_notify_owners.get(target) or None
        if owner is None:
            status = "unbound"
        elif not current:
            status = "missing"
        elif len(current) > 1:
            status = "ambiguous"
        elif current[0] != owner:
            status = "changed"
        else:
            status = "ok"
        user = await hass.auth.async_get_user(owner) if owner else None
        unique = current[0] if len(current) == 1 and current[0] else None
        current_user = await hass.auth.async_get_user(unique) if unique else None
        result[target] = {
            "owner": owner,
            "owner_name": user.name if user else None,
            "current_name": current_user.name if current_user else None,
            "status": status,
        }
    return result


def bind_owners(
    hass: HomeAssistant, new: Config, old: Config | None, rebind: Iterable[str] = ()
) -> Config:
    """Propriétaires mémorisés de `new`, déterminés par le serveur.

    Ceux de `new` (envoyés par le client) sont ignorés. Un téléphone déjà présent dans `old`
    garde son propriétaire mémorisé (ou reste sans propriétaire) ; un téléphone ajouté, ou
    listé dans `rebind`, prend le propriétaire actuel unique de l'appareil, sinon
    `ConfigError`. Les cibles qui ne sont pas des téléphones `mobile_app` n'en ont pas.
    """
    rebind = set(rebind)
    kept = set(old.request_notify) if old is not None else set()
    old_owners = old.request_notify_owners if old is not None else {}
    owners: dict[str, str] = {}
    for target, current in current_phone_owners(hass, new.request_notify).items():
        if target in kept and target not in rebind:
            if remembered := old_owners.get(target):
                owners[target] = remembered
            continue
        if len(current) != 1 or not current[0]:
            raise ConfigError(f"request_notify : {target} — appareil introuvable ou en double")
        owners[target] = current[0]
    return dataclasses.replace(new, request_notify_owners=owners)


async def migrate_phone_owners(hass: HomeAssistant, engine: ParentalEngine) -> None:
    """Associe, une seule fois, les téléphones de l'ancien format de configuration.

    Ne fait rien si la configuration stockée contenait déjà `request_notify_owners`
    (`store.owners_migration_pending` faux) : un téléphone non associé le reste jusqu'à
    « Réassocier », même si un appareil de ce nom apparaît plus tard. Sinon, un téléphone
    `mobile_app` dont l'unique appareil a un `user_id` valide est associé à cet utilisateur ;
    les autres restent sans propriétaire (et sans droits). La configuration est toujours
    réécrite, même si rien n'a été associé : la clé enregistrée empêche toute nouvelle
    migration.
    """
    cfg = engine.config
    if cfg is None or not engine.store.owners_migration_pending:
        return
    owners = dict(cfg.request_notify_owners)
    for target, current in current_phone_owners(hass, cfg.request_notify).items():
        if owners.get(target) or len(current) != 1 or not current[0]:
            continue
        owners[target] = current[0]
        user = await hass.auth.async_get_user(current[0])
        name = user.name if user else current[0]
        _LOGGER.info("Téléphone %s associé à l'utilisateur %s", target, name)
    await engine.set_config(dataclasses.replace(cfg, request_notify_owners=owners))
