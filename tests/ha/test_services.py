"""Services HA : schémas, code parent, verrouillage après échecs, import admin."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
import voluptuous as vol
from homeassistant.auth.models import User
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parental_control import security
from custom_components.parental_control.const import DOMAIN
from custom_components.parental_control.core.config_io import parse_config
from custom_components.parental_control.engine import ParentalEngine
from custom_components.parental_control.security import hash_code
from custom_components.parental_control.store import ParentalStore
from tests.fixtures import EX
from tests.ha.test_engine import SATURDAY, TUESDAY, TV, Services, at

CODE = "0123"
SERVICES = [
    "devoirs_termines",
    "ajouter_bonus",
    "exception",
    "annuler_exception",
    "demarrer_minuteur",
    "arreter_minuteur",
    "pause",
    "importer_configuration",
]


@dataclass
class Env:
    hass: HomeAssistant
    entry: MockConfigEntry
    engine: ParentalEngine
    admin: User
    kid: User
    services: Services

    @property
    def admin_ctx(self) -> Context:
        return Context(user_id=self.admin.id)

    @property
    def kid_ctx(self) -> Context:
        return Context(user_id=self.kid.id)

    async def call(self, service: str, data: dict, context: Context | None = None,
                   return_response: bool = False):
        return await self.hass.services.async_call(
            DOMAIN, service, data, blocking=True, context=context,
            return_response=return_response,
        )


@pytest.fixture
async def make_env(hass: HomeAssistant, freezer):
    await hass.config.async_set_time_zone("America/Toronto")
    services = Services(hass)
    # Le premier utilisateur créé devient propriétaire : on le crée d'abord.
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    admin = await hass.auth.async_create_user("Parent", group_ids=["system-admin"])
    kid = await hass.auth.async_create_user("Tablette", group_ids=["system-users"])
    assert admin.is_admin and not kid.is_admin

    async def _make(moment) -> Env:
        freezer.move_to(moment)
        await ParentalStore(hass).save_config(parse_config(EX))
        entry = MockConfigEntry(
            domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": hash_code(CODE)}
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return Env(hass, entry, entry.runtime_data, admin, kid, services)

    return _make


async def _raises_key(coro, key: str) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await coro
    assert err.value.translation_key == key


# --- enregistrement ------------------------------------------------------------


async def test_services_registered_and_removed(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    for service in SERVICES:
        assert env.hass.services.has_service(DOMAIN, service)
    assert await env.hass.config_entries.async_unload(env.entry.entry_id)
    for service in SERVICES:
        assert not env.hass.services.has_service(DOMAIN, service)


# --- code parent ---------------------------------------------------------------


async def test_homework_requires_code_for_non_admin(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    await _raises_key(
        env.call("devoirs_termines", {"kid_id": "gabin"}, env.kid_ctx), "code_required"
    )
    await _raises_key(
        env.call("devoirs_termines", {"kid_id": "gabin", "code": "9999"}, env.kid_ctx),
        "code_invalid",
    )
    assert not env.engine.decisions.homework_done_on("gabin", TUESDAY)
    await env.call("devoirs_termines", {"kid_id": "gabin", "code": CODE}, env.kid_ctx)
    assert env.engine.decisions.homework_done_on("gabin", TUESDAY)


async def test_homework_admin_without_code(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    await env.call("devoirs_termines", {"kid_id": "gabin"}, env.admin_ctx)
    assert env.engine.decisions.homework_done_on("gabin", TUESDAY)


async def test_automation_without_code(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    await env.call("devoirs_termines", {"kid_id": "gabin"}, Context())
    assert env.engine.decisions.homework_done_on("gabin", TUESDAY)


async def test_close_exception_never_requires_code(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    await env.call("exception", {"open": False, "resource_id": "tv"}, env.kid_ctx)
    assert [e.open for e in env.engine.decisions.exceptions] == [False]
    await _raises_key(
        env.call("exception", {"open": True, "resource_id": "tv"}, env.kid_ctx),
        "code_required",
    )
    assert len(env.engine.decisions.exceptions) == 1


async def test_unpause_requires_code_pause_does_not(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    await env.call("pause", {"active": True}, env.kid_ctx)
    assert env.engine.decisions.paused
    await _raises_key(env.call("pause", {"active": False}, env.kid_ctx), "code_required")
    assert env.engine.decisions.paused
    await env.call("pause", {"active": False, "code": CODE}, env.kid_ctx)
    assert not env.engine.decisions.paused


async def test_exception_returns_id_and_can_be_cancelled(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    response = await env.call(
        "exception", {"open": True, "resource_id": "tv", "minutes": 30, "code": CODE},
        env.kid_ctx, return_response=True,
    )
    exc_id = response["id"]
    assert [e.id for e in env.engine.decisions.exceptions] == [exc_id]
    # Annuler une ouverture referme : pas de code.
    await env.call("annuler_exception", {"exception_id": exc_id}, env.kid_ctx)
    assert env.engine.decisions.exceptions == []
    # Sans réponse demandée, le service s'exécute quand même.
    await env.call("exception", {"open": False, "resource_id": "tv"}, env.kid_ctx)
    assert len(env.engine.decisions.exceptions) == 1


async def test_cancel_close_exception_requires_code(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    response = await env.call(
        "exception", {"open": False, "resource_id": "tv"}, env.kid_ctx,
        return_response=True,
    )
    exc_id = response["id"]
    await _raises_key(
        env.call("annuler_exception", {"exception_id": exc_id}, env.kid_ctx),
        "code_required",
    )
    assert len(env.engine.decisions.exceptions) == 1
    await env.call("annuler_exception", {"exception_id": exc_id, "code": CODE}, env.kid_ctx)
    assert env.engine.decisions.exceptions == []
    # Id inconnu : ni erreur ni code.
    await env.call("annuler_exception", {"exception_id": "inconnu"}, env.kid_ctx)


async def test_bonus_and_timers(make_env) -> None:
    env = await make_env(at(SATURDAY, 10, 0))
    await _raises_key(
        env.call("ajouter_bonus", {"kid_id": "gabin", "minutes": 15}, env.kid_ctx),
        "code_required",
    )
    await env.call("ajouter_bonus", {"kid_id": "gabin", "minutes": 15, "code": CODE},
                   env.kid_ctx)
    assert [b.minutes for b in env.engine.decisions.bonuses] == [15]

    await _raises_key(
        env.call("demarrer_minuteur", {"kid_id": "gabin", "minutes": 20}, env.kid_ctx),
        "code_required",
    )
    await env.call("demarrer_minuteur", {"kid_id": "gabin", "minutes": 20, "code": CODE},
                   env.kid_ctx)
    assert len(env.engine.decisions.timers) == 1
    # Arrêter un minuteur ne débloque rien : pas de code.
    await env.call("arreter_minuteur", {"kid_id": "gabin"}, env.kid_ctx)
    assert env.engine.decisions.active_timer("gabin", dt_util.now()) is None


# --- schémas -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("ajouter_bonus", {"minutes": 15}),
        ("ajouter_bonus", {"minutes": 15, "kid_id": "gabin", "resource_id": "tv"}),
        ("ajouter_bonus", {"minutes": 0, "kid_id": "gabin"}),
        ("ajouter_bonus", {"minutes": 241, "kid_id": "gabin"}),
        ("demarrer_minuteur", {"kid_id": "gabin", "minutes": 0}),
        ("demarrer_minuteur", {"kid_id": "gabin"}),
        ("exception", {"resource_id": "tv"}),
        ("pause", {}),
        ("importer_configuration", {}),
    ],
)
async def test_schema_errors(make_env, service, data) -> None:
    env = await make_env(at(SATURDAY, 10, 0))
    with pytest.raises(vol.Invalid):
        await env.call(service, data, env.admin_ctx)


async def test_code_keeps_leading_zero(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    await env.call("devoirs_termines", {"kid_id": "gabin", "code": "0123"}, env.kid_ctx)
    assert env.engine.decisions.homework_done_on("gabin", TUESDAY)


async def test_unknown_kid_rejected(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    await _raises_key(
        env.call("devoirs_termines", {"kid_id": "inconnu"}, env.admin_ctx), "unknown_kid"
    )
    await _raises_key(
        env.call("ajouter_bonus", {"resource_id": "inconnue", "minutes": 5}, env.admin_ctx),
        "unknown_resource",
    )


# --- import de configuration ---------------------------------------------------


async def test_import_configuration_admin_only(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    new = dict(EX, kids=[dict(EX["kids"][0], name="Gabin B.")])
    with pytest.raises(Unauthorized):
        await env.call("importer_configuration", {"config": new, "code": CODE}, env.kid_ctx)
    assert env.engine.config.kid("gabin").name == "Gabin"
    with pytest.raises(Unauthorized):
        await env.call("importer_configuration", {"config": new},
                       Context(user_id="inconnu"))
    await env.call("importer_configuration", {"config": new}, env.admin_ctx)
    assert env.engine.config.kid("gabin").name == "Gabin B."
    newer = dict(EX, kids=[dict(EX["kids"][0], name="Gabin C.")])
    await env.call("importer_configuration", {"config": newer}, Context())
    assert env.engine.config.kid("gabin").name == "Gabin C."


async def test_import_invalid_config_raises_validation_error(make_env) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    with pytest.raises(ServiceValidationError) as err:
        await env.call("importer_configuration", {"config": dict(EX, version=99)},
                       env.admin_ctx)
    assert err.value.translation_key == "invalid_config"
    assert "version" in err.value.translation_placeholders["error"]
    assert env.engine.config == parse_config(EX)


# --- verrouillage après codes faux ---------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(security, "_monotonic", clock)
    return clock


async def test_code_lockout_after_5_failures(make_env, clock, monkeypatch) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    homework = {"kid_id": "gabin"}
    for _ in range(5):
        await _raises_key(
            env.call("devoirs_termines", dict(homework, code="9999"), env.kid_ctx),
            "code_invalid",
        )

    verified: list[str] = []
    real_verify = security.verify_code

    def spy(code: str, stored: str) -> bool:
        verified.append(code)
        return real_verify(code, stored)

    monkeypatch.setattr(security, "verify_code", spy)

    # Verrouillé : même le bon code est refusé, sans calcul pbkdf2.
    await _raises_key(
        env.call("devoirs_termines", dict(homework, code=CODE), env.kid_ctx), "code_locked"
    )
    assert verified == []
    assert not env.engine.decisions.homework_done_on("gabin", TUESDAY)
    with pytest.raises(ServiceValidationError) as err:
        await env.call("devoirs_termines", dict(homework, code=CODE), env.kid_ctx)
    assert str(err.value) == "Too many wrong parent codes. Try again in 60 s"
    # Un admin n'est pas concerné, et le verrou est propre à l'utilisateur.
    await env.call("pause", {"active": False}, env.admin_ctx)

    clock.now += 59
    await _raises_key(
        env.call("devoirs_termines", dict(homework, code=CODE), env.kid_ctx), "code_locked"
    )
    # Après 60 s : un nouvel échec double le verrou (120 s).
    clock.now += 2
    await _raises_key(
        env.call("devoirs_termines", dict(homework, code="9999"), env.kid_ctx),
        "code_invalid",
    )
    clock.now += 119
    await _raises_key(
        env.call("devoirs_termines", dict(homework, code=CODE), env.kid_ctx), "code_locked"
    )
    clock.now += 2
    assert verified == ["9999"]

    # Le doublement est plafonné à 15 minutes.
    for expected in (240, 480, 900, 900):
        await _raises_key(
            env.call("devoirs_termines", dict(homework, code="9999"), env.kid_ctx),
            "code_invalid",
        )
        clock.now += expected - 1
        await _raises_key(
            env.call("devoirs_termines", dict(homework, code=CODE), env.kid_ctx),
            "code_locked",
        )
        clock.now += 2

    await env.call("devoirs_termines", dict(homework, code=CODE), env.kid_ctx)
    assert env.engine.decisions.homework_done_on("gabin", TUESDAY)


async def test_code_lockout_resets_on_success(make_env, clock) -> None:
    env = await make_env(at(TUESDAY, 16, 30))
    homework = {"kid_id": "gabin"}
    for _ in range(4):
        await _raises_key(
            env.call("devoirs_termines", dict(homework, code="9999"), env.kid_ctx),
            "code_invalid",
        )
    await env.call("devoirs_termines", dict(homework, code=CODE), env.kid_ctx)
    # Compteur remis à zéro : 4 nouveaux échecs ne verrouillent pas.
    for _ in range(4):
        await _raises_key(
            env.call("devoirs_termines", dict(homework, code="9999"), env.kid_ctx),
            "code_invalid",
        )
    await env.call("pause", {"active": False, "code": CODE}, env.kid_ctx)
    # Après un verrou échu, un bon code remet aussi le compteur à zéro.
    for _ in range(5):
        await _raises_key(
            env.call("devoirs_termines", dict(homework, code="9999"), env.kid_ctx),
            "code_invalid",
        )
    clock.now += 61
    await env.call("devoirs_termines", dict(homework, code=CODE), env.kid_ctx)
    await _raises_key(
        env.call("devoirs_termines", dict(homework, code="9999"), env.kid_ctx),
        "code_invalid",
    )
