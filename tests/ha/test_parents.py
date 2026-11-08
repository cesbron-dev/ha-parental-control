"""Qui est parent : administrateur, ou propriétaire mémorisé d'un téléphone de demandes."""

from __future__ import annotations

import logging
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parental_control.const import DOMAIN, STORE_VERSION
from custom_components.parental_control.core.config_io import ConfigError, parse_config
from custom_components.parental_control.parents import (
    bind_owners,
    current_phone_owners,
    is_parent,
    migrate_phone_owners,
    phone_status,
    trusted_phone_owners,
)
from tests.fixtures import EX

MANOU = "notify.mobile_app_iphone_de_manou"
OLIVIER = "notify.mobile_app_iphone_de_olivier"
OTHER = "notify.persistent_notification"


@pytest.fixture
async def users(hass):
    # Le premier utilisateur créé devient propriétaire : on le crée d'abord.
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    admin = await hass.auth.async_create_user("Olivier", group_ids=["system-admin"])
    manou = await hass.auth.async_create_user("Manou", group_ids=["system-users"])
    kid = await hass.auth.async_create_user("Tablette", group_ids=["system-users"])
    assert admin.is_admin and not manou.is_admin and not kid.is_admin
    return {"admin": admin, "manou": manou, "kid": kid}


def add_phone(hass, device_name: str, user_id: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="mobile_app",
        data={
            "device_name": device_name,
            "user_id": user_id,
            "app_id": "io.robbie.HomeAssistant",
            "webhook_id": f"{device_name}-{user_id}",
        },
    )
    entry.add_to_hass(hass)
    return entry


def cfg(targets: list[str], owners: dict[str, str] | None = None):
    return parse_config({**EX, "request_notify": targets, "request_notify_owners": owners or {}})


async def test_current_phone_owners(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    owners = current_phone_owners(hass, [MANOU, OLIVIER, OTHER])
    assert owners == {MANOU: [users["manou"].id], OLIVIER: []}


async def test_trusted_owner_matches(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    add_phone(hass, "iPhone de Olivier", users["admin"].id)
    config = cfg([MANOU, OLIVIER], {MANOU: users["manou"].id, OLIVIER: users["admin"].id})
    assert trusted_phone_owners(hass, config) == {users["manou"].id, users["admin"].id}
    assert trusted_phone_owners(hass, None) == set()


async def test_device_recreated_by_other_user_not_trusted(hass, users) -> None:
    """Le téléphone de Manou a disparu ; la tablette enregistre un appareil sous ce nom."""
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    config = cfg([MANOU], {MANOU: users["manou"].id})
    assert trusted_phone_owners(hass, config) == set()
    assert not await is_parent(hass, config, users["kid"].id)
    assert not await is_parent(hass, config, users["manou"].id)


async def test_ambiguous_device_not_trusted(
    hass, users, caplog: pytest.LogCaptureFixture
) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    config = cfg([MANOU], {MANOU: users["manou"].id})
    with caplog.at_level(logging.WARNING):
        assert trusted_phone_owners(hass, config) == set()
    assert "mobile_app_iphone_de_manou" in caplog.text and "plusieurs" in caplog.text


async def test_ambiguous_warning_logged_once(
    hass, users, caplog: pytest.LogCaptureFixture
) -> None:
    """`is_parent` est appelé à chaque action : l'avertissement ne doit pas inonder le journal."""
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    add_phone(hass, "iPhone de Olivier", users["admin"].id)
    add_phone(hass, "iPhone de Olivier", users["kid"].id)
    config = cfg([MANOU, OLIVIER], {MANOU: users["manou"].id, OLIVIER: users["admin"].id})
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert trusted_phone_owners(hass, config) == set()
            assert not await is_parent(hass, config, users["manou"].id)
    warnings = [r.getMessage() for r in caplog.records if "plusieurs" in r.getMessage()]
    assert len(warnings) == 2
    assert any(MANOU in w for w in warnings) and any(OLIVIER in w for w in warnings)


async def test_unbound_phone_not_trusted(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    config = cfg([MANOU])
    assert trusted_phone_owners(hass, config) == set()
    assert not await is_parent(hass, config, users["manou"].id)


async def test_non_mobile_app_target_ignored(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    config = cfg([OTHER, MANOU], {OTHER: users["kid"].id, MANOU: users["manou"].id})
    assert trusted_phone_owners(hass, config) == {users["manou"].id}
    assert OTHER not in await phone_status(hass, config)


async def test_is_parent_admin_without_phone(hass, users) -> None:
    assert await is_parent(hass, cfg([]), users["admin"].id)
    assert await is_parent(hass, None, users["admin"].id)


async def test_is_parent_none_user(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    assert not await is_parent(hass, cfg([MANOU], {MANOU: users["manou"].id}), None)


async def test_is_parent_non_admin_with_phone(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    config = cfg([MANOU], {MANOU: users["manou"].id})
    assert await is_parent(hass, config, users["manou"].id)
    assert not await is_parent(hass, config, users["kid"].id)
    assert not await is_parent(hass, config, "inconnu")


async def test_is_parent_removed_phone(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    assert await is_parent(hass, cfg([MANOU], {MANOU: users["manou"].id}), users["manou"].id)
    assert not await is_parent(hass, cfg([]), users["manou"].id)


async def test_phone_status_each_state(hass, users) -> None:
    ok = "notify.mobile_app_ok"
    unbound = "notify.mobile_app_unbound"
    missing = "notify.mobile_app_missing"
    changed = "notify.mobile_app_changed"
    ambiguous = "notify.mobile_app_ambiguous"
    manou = users["manou"].id
    add_phone(hass, "OK", manou)
    add_phone(hass, "Unbound", manou)
    add_phone(hass, "Changed", users["kid"].id)
    add_phone(hass, "Ambiguous", manou)
    add_phone(hass, "Ambiguous", users["kid"].id)
    config = cfg(
        [ok, unbound, missing, changed, ambiguous, OTHER],
        {ok: manou, missing: manou, changed: manou, ambiguous: manou},
    )
    # `current_name` : nom du propriétaire actuel unique de l'appareil (qui deviendrait parent
    # en réassociant), `None` sans appareil ou avec plusieurs.
    assert await phone_status(hass, config) == {
        ok: {"owner": manou, "owner_name": "Manou", "current_name": "Manou", "status": "ok"},
        unbound: {
            "owner": None, "owner_name": None, "current_name": "Manou", "status": "unbound"
        },
        missing: {
            "owner": manou, "owner_name": "Manou", "current_name": None, "status": "missing"
        },
        changed: {
            "owner": manou, "owner_name": "Manou", "current_name": "Tablette", "status": "changed"
        },
        ambiguous: {
            "owner": manou, "owner_name": "Manou", "current_name": None, "status": "ambiguous"
        },
    }


async def test_phone_status_unknown_owner_has_no_name(hass, users) -> None:
    """Propriétaire mémorisé supprimé de HA : identifiant gardé, pas de nom."""
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    status = await phone_status(hass, cfg([MANOU], {MANOU: "supprime"}))
    assert status == {
        MANOU: {
            "owner": "supprime", "owner_name": None, "current_name": "Manou", "status": "changed"
        }
    }


async def test_phone_status_current_owner_unknown_has_no_name(hass, users) -> None:
    """Appareil d'un utilisateur inexistant (ou sans `user_id`) : pas de nom actuel."""
    add_phone(hass, "iPhone de Manou", "inconnu")
    add_phone(hass, "iPhone de Olivier", "")
    status = await phone_status(hass, cfg([MANOU, OLIVIER]))
    assert status[MANOU]["current_name"] is None
    assert status[OLIVIER]["current_name"] is None


async def test_bind_owners_keeps_old_owner(hass, users) -> None:
    """Le téléphone de Manou a été recréé par la tablette : l'ancien propriétaire reste."""
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    add_phone(hass, "iPhone de Olivier", users["admin"].id)
    old = cfg([MANOU], {MANOU: users["manou"].id})
    bound = bind_owners(hass, cfg([MANOU, OLIVIER]), old)
    assert bound.request_notify_owners == {MANOU: users["manou"].id, OLIVIER: users["admin"].id}


async def test_bind_owners_ignores_client_owner(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    add_phone(hass, "iPhone de Olivier", users["admin"].id)
    old = cfg([MANOU], {MANOU: users["manou"].id})
    new = cfg([MANOU, OLIVIER], {MANOU: users["kid"].id, OLIVIER: users["kid"].id})
    bound = bind_owners(hass, new, old)
    assert bound.request_notify_owners == {MANOU: users["manou"].id, OLIVIER: users["admin"].id}
    assert bind_owners(hass, new, None).request_notify_owners == {
        MANOU: users["manou"].id, OLIVIER: users["admin"].id
    }


async def test_bind_owners_rebind(hass, users) -> None:
    """App réinstallée par Manou sous un nouveau compte : réassociation explicite."""
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    old = cfg([MANOU], {MANOU: users["manou"].id})
    bound = bind_owners(hass, cfg([MANOU]), old, rebind=[MANOU])
    assert bound.request_notify_owners == {MANOU: users["kid"].id}


async def test_bind_owners_unbound_kept_phone_stays_unbound(hass, users) -> None:
    """Un téléphone déjà listé sans propriétaire ne s'associe pas en silence."""
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    old = cfg([MANOU])
    assert bind_owners(hass, cfg([MANOU]), old).request_notify_owners == {}
    bound = bind_owners(hass, cfg([MANOU]), old, rebind=[MANOU])
    assert bound.request_notify_owners == {MANOU: users["kid"].id}


@pytest.mark.parametrize("devices", [0, 2])
async def test_bind_owners_missing_device_raises(hass, users, devices) -> None:
    for _ in range(devices):
        add_phone(hass, "iPhone de Manou", users["manou"].id)
    with pytest.raises(ConfigError) as err:
        bind_owners(hass, cfg([MANOU]), None)
    assert MANOU in str(err.value)
    add_phone(hass, "iPhone de Olivier", users["admin"].id)
    old = cfg([OLIVIER], {OLIVIER: users["admin"].id})
    with pytest.raises(ConfigError):
        bind_owners(hass, cfg([OLIVIER, MANOU]), old, rebind=[OLIVIER])


async def test_bind_owners_non_mobile_target(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    new = cfg([OTHER, MANOU], {OTHER: users["kid"].id})
    bound = bind_owners(hass, new, None)
    assert bound.request_notify_owners == {MANOU: users["manou"].id}
    assert bound.request_notify == (OTHER, MANOU)


class FakeEngine:
    """Moteur minimal : `config`, `store` et `set_config` suffisent à la migration.

    `pending` : la configuration stockée était à l'ancien format (sans propriétaires).
    """

    def __init__(self, config, pending: bool = True) -> None:
        self.config = config
        self.store = SimpleNamespace(owners_migration_pending=pending)
        self.saved = 0

    async def set_config(self, config) -> None:
        self.saved += 1
        self.config = config


async def test_migration_binds_unique_owner(
    hass, users, caplog: pytest.LogCaptureFixture
) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    engine = FakeEngine(cfg([MANOU]))
    with caplog.at_level(logging.INFO):
        await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {MANOU: users["manou"].id}
    assert engine.saved == 1
    assert f"Téléphone {MANOU} associé à l'utilisateur Manou" in caplog.text


async def test_migration_logs_user_id_when_user_unknown(
    hass, users, caplog: pytest.LogCaptureFixture
) -> None:
    add_phone(hass, "iPhone de Manou", "inconnu")
    engine = FakeEngine(cfg([MANOU]))
    with caplog.at_level(logging.INFO):
        await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {MANOU: "inconnu"}
    assert f"Téléphone {MANOU} associé à l'utilisateur inconnu" in caplog.text


async def test_migration_skips_ambiguous_and_missing(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    add_phone(hass, "Autre", "")
    engine = FakeEngine(cfg([MANOU, OLIVIER, OTHER, "notify.mobile_app_autre"]))
    await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {}
    # Rien d'associé, mais la configuration est réécrite : la migration ne rejouera pas.
    assert engine.saved == 1


async def test_migration_keeps_existing_owner(hass, users) -> None:
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    add_phone(hass, "iPhone de Olivier", users["admin"].id)
    engine = FakeEngine(cfg([MANOU, OLIVIER], {MANOU: users["manou"].id}))
    await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {
        MANOU: users["manou"].id,
        OLIVIER: users["admin"].id,
    }


async def test_migration_only_for_old_format(hass, users) -> None:
    """Configuration déjà au nouveau format : jamais de migration, même pour un téléphone
    non associé dont l'appareil a un propriétaire unique."""
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    engine = FakeEngine(cfg([MANOU]), pending=False)
    await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {}
    assert engine.saved == 0
    await migrate_phone_owners(hass, FakeEngine(None))


async def test_setup_migrates_once_then_unbound_phone_stays_unbound(
    hass, users, make_env
) -> None:
    """Migration au premier démarrage ; l'appareil d'un téléphone resté non associé est
    ensuite recréé par l'enfant : au démarrage suivant, il reste non associé."""
    add_phone(hass, "iPhone de Olivier", users["admin"].id)
    env = await make_env(
        datetime(2026, 11, 3, 16, 30, tzinfo=ZoneInfo("America/Toronto")),
        {**EX, "request_notify": [OLIVIER, MANOU]},
        raw=True,
    )
    assert env.engine.config.request_notify_owners == {OLIVIER: users["admin"].id}
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    assert await hass.config_entries.async_reload(env.entry.entry_id)
    await hass.async_block_till_done()
    engine = env.entry.runtime_data
    assert engine.config.request_notify_owners == {OLIVIER: users["admin"].id}
    assert users["kid"].id not in trusted_phone_owners(hass, engine.config)


async def test_setup_old_format_without_phone_persists_key(hass, users, make_env) -> None:
    """Ancien format sans téléphone associable : la clé est enregistrée (vide), et un
    appareil créé ensuite n'est pas associé au démarrage suivant."""
    env = await make_env(
        datetime(2026, 11, 3, 16, 30, tzinfo=ZoneInfo("America/Toronto")),
        {**EX, "request_notify": [MANOU]},
        raw=True,
    )
    assert env.engine.config.request_notify_owners == {}
    stored = await Store(hass, STORE_VERSION, f"{DOMAIN}.config").async_load()
    assert stored["request_notify_owners"] == {}
    add_phone(hass, "iPhone de Manou", users["kid"].id)
    assert await hass.config_entries.async_reload(env.entry.entry_id)
    await hass.async_block_till_done()
    assert env.entry.runtime_data.config.request_notify_owners == {}


async def test_setup_entry_runs_migration(hass, users, make_env) -> None:
    add_phone(hass, "iPhone de Manou", users["manou"].id)
    env = await make_env(
        datetime(2026, 11, 3, 16, 30, tzinfo=ZoneInfo("America/Toronto")),
        {**EX, "request_notify": [MANOU]},
        raw=True,
    )
    assert env.engine.config.request_notify_owners == {MANOU: users["manou"].id}
