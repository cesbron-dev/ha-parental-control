"""Fixtures partagées du noyau : config d'exemple à trois enfants."""

import copy
from collections.abc import Callable
from zoneinfo import ZoneInfo

import pytest

from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.core.model import Config
from tests.fixtures import EX, integration_of

TZ = ZoneInfo("America/Toronto")


def family_config_dict() -> dict:
    """Config d'exemple de la tâche 1 complétée par Zoé et Alice.

    - Zoé : même profil que Hugo.
    - Alice : école `00:00 bloque → 16:15 apres_devoirs → 19:00 bloque`.
    - Ressources : TV et Switch partagées par les trois, un iPhone pour Hugo et Zoé.
    - Aucun mode par ressource par défaut (les tests les ajoutent au besoin).
    """
    d = copy.deepcopy(EX)
    hugo = d["kids"][0]
    hugo["resource_modes"] = {}

    zoe = copy.deepcopy(hugo)
    zoe.update(id="zoe", name="Zoé", emoji="⚽", color="#4ECDC4", calendar=None)

    alice = copy.deepcopy(hugo)
    alice.update(id="alice", name="Alice", emoji="🦖", color="#FFD93D", calendar=None)
    alice["profiles"] = {
        "ecole": {
            "segments": [
                {"start": "00:00", "type": "bloque"},
                {"start": "16:15", "type": "apres_devoirs"},
                {"start": "19:00", "type": "bloque"},
            ]
        },
        "fin_de_semaine": {
            "segments": [
                {"start": "00:00", "type": "bloque"},
                {"start": "09:00", "type": "libre"},
                {"start": "19:00", "type": "bloque"},
            ]
        },
    }
    d["kids"] = [hugo, zoe, alice]

    tv, iphone_hugo, switch = d["resources"]
    tv["owners"] = ["hugo", "zoe", "alice"]
    switch["owners"] = ["hugo", "zoe", "alice"]
    iphone_zoe = copy.deepcopy(iphone_hugo)
    iphone_zoe.update(id="iphone_zoe", name="iPhone Zoé", owners=["zoe"])
    iphone_zoe["devices"][0]["name"] = "iPhone Zoé"
    integration_of(iphone_zoe)["device_id"] = "adguard_iphone_zoe"
    d["resources"] = [tv, iphone_hugo, iphone_zoe, switch]
    return d


@pytest.fixture
def make_cfg() -> Callable[..., Config]:
    """Fabrique : `make_cfg(lambda d: ...)` modifie le dict avant le parsing."""

    def _make(modify: Callable[[dict], None] | None = None) -> Config:
        d = family_config_dict()
        if modify is not None:
            modify(d)
        return parse_config(d)

    return _make


@pytest.fixture
def cfg(make_cfg) -> Config:
    return make_cfg()


def weekend_quota(d: dict) -> None:
    """Fin de semaine : les trois enfants suivent le profil quota de Hugo (120 min,
    `00:00 bloque → 08:00 quota → 20:00 bloque`), pour que la TV partagée ne soit
    ouverte que par son propre quota."""
    hugo_weekend = d["kids"][0]["profiles"]["fin_de_semaine"]
    for kid in d["kids"]:
        kid["profiles"]["fin_de_semaine"] = copy.deepcopy(hugo_weekend)


@pytest.fixture
def weekend_cfg(make_cfg) -> Config:
    return make_cfg(weekend_quota)


def mixed_tv(d: dict) -> None:
    """La TV devient un appareil logique mixte : son lecteur plus un client AdGuard sur un second
    appareil physique."""
    d["resources"][0]["devices"].append({"name": "Google TV", "integrations": [
        {"kind": "adguard_services", "device_id": "adguard_google_tv"}]})
