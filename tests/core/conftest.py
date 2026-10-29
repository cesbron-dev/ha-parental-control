"""Fixtures partagées du noyau : config d'exemple à trois enfants."""

import copy
from collections.abc import Callable
from zoneinfo import ZoneInfo

import pytest

from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.core.model import Config
from tests.core.test_config_io import EX

TZ = ZoneInfo("America/Toronto")


def family_config_dict() -> dict:
    """Config d'exemple de la tâche 1 complétée par Léo et Maël.

    - Léo : même profil que Gabin.
    - Maël : école `00:00 bloque → 16:15 apres_devoirs → 19:00 bloque`.
    - Ressources : TV et Switch partagées par les trois, un iPhone pour Gabin et Léo.
    - Aucun mode par ressource par défaut (les tests les ajoutent au besoin).
    """
    d = copy.deepcopy(EX)
    gabin = d["kids"][0]
    gabin["resource_modes"] = {}

    leo = copy.deepcopy(gabin)
    leo.update(id="leo", name="Léo", emoji="⚽", color="#4ECDC4", calendar=None)

    mael = copy.deepcopy(gabin)
    mael.update(id="mael", name="Maël", emoji="🦖", color="#FFD93D", calendar=None)
    mael["profiles"] = {
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
    d["kids"] = [gabin, leo, mael]

    tv, iphone_gabin, switch = d["resources"]
    tv["owners"] = ["gabin", "leo", "mael"]
    switch["owners"] = ["gabin", "leo", "mael"]
    iphone_leo = copy.deepcopy(iphone_gabin)
    iphone_leo.update(id="iphone_leo", name="iPhone Léo", owners=["leo"], client="iphone_leo")
    d["resources"] = [tv, iphone_gabin, iphone_leo, switch]
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
    """Fin de semaine : les trois enfants suivent le profil quota de Gabin (120 min,
    `00:00 bloque → 08:00 quota → 20:00 bloque`), pour que la TV partagée ne soit
    ouverte que par son propre quota."""
    gabin_weekend = d["kids"][0]["profiles"]["fin_de_semaine"]
    for kid in d["kids"]:
        kid["profiles"]["fin_de_semaine"] = copy.deepcopy(gabin_weekend)


@pytest.fixture
def weekend_cfg(make_cfg) -> Config:
    return make_cfg(weekend_quota)
