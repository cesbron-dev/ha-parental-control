"""Qui est parent : administrateur, ou propriétaire mémorisé d'un téléphone de demandes."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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

JULIE = "notify.mobile_app_iphone_de_julie"
MARC = "notify.mobile_app_iphone_de_marc"
OTHER = "notify.persistent_notification"


@pytest.fixture
async def users(hass):
    # Le premier utilisateur créé devient propriétaire : on le crée d'abord.
    await hass.auth.async_create_user("Propriétaire", group_ids=["system-admin"])
    admin = await hass.auth.async_create_user("Marc", group_ids=["system-admin"])
    julie = await hass.auth.async_create_user("Julie", group_ids=["system-users"])
    kid = await hass.auth.async_create_user("Tablette", group_ids=["system-users"])
    assert admin.is_admin and not julie.is_admin and not kid.is_admin
    return {"admin": admin, "julie": julie, "kid": kid}


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
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    owners = current_phone_owners(hass, [JULIE, MARC, OTHER])
    assert owners == {JULIE: [users["julie"].id], MARC: []}


async def test_trusted_owner_matches(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    add_phone(hass, "iPhone de Marc", users["admin"].id)
    config = cfg([JULIE, MARC], {JULIE: users["julie"].id, MARC: users["admin"].id})
    assert trusted_phone_owners(hass, config) == {users["julie"].id, users["admin"].id}
    assert trusted_phone_owners(hass, None) == set()


async def test_device_recreated_by_other_user_not_trusted(hass, users) -> None:
    """Le téléphone de Julie a disparu ; la tablette enregistre un appareil sous ce nom."""
    add_phone(hass, "iPhone de Julie", users["kid"].id)
    config = cfg([JULIE], {JULIE: users["julie"].id})
    assert trusted_phone_owners(hass, config) == set()
    assert not await is_parent(hass, config, users["kid"].id)
    assert not await is_parent(hass, config, users["julie"].id)


async def test_ambiguous_device_not_trusted(
    hass, users, caplog: pytest.LogCaptureFixture
) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    add_phone(hass, "iPhone de Julie", users["kid"].id)
    config = cfg([JULIE], {JULIE: users["julie"].id})
    with caplog.at_level(logging.WARNING):
        assert trusted_phone_owners(hass, config) == set()
    assert "mobile_app_iphone_de_julie" in caplog.text and "plusieurs" in caplog.text


async def test_unbound_phone_not_trusted(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    config = cfg([JULIE])
    assert trusted_phone_owners(hass, config) == set()
    assert not await is_parent(hass, config, users["julie"].id)


async def test_non_mobile_app_target_ignored(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    config = cfg([OTHER, JULIE], {OTHER: users["kid"].id, JULIE: users["julie"].id})
    assert trusted_phone_owners(hass, config) == {users["julie"].id}
    assert OTHER not in phone_status(hass, config)


async def test_is_parent_admin_without_phone(hass, users) -> None:
    assert await is_parent(hass, cfg([]), users["admin"].id)
    assert await is_parent(hass, None, users["admin"].id)


async def test_is_parent_none_user(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    assert not await is_parent(hass, cfg([JULIE], {JULIE: users["julie"].id}), None)


async def test_is_parent_non_admin_with_phone(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    config = cfg([JULIE], {JULIE: users["julie"].id})
    assert await is_parent(hass, config, users["julie"].id)
    assert not await is_parent(hass, config, users["kid"].id)
    assert not await is_parent(hass, config, "inconnu")


async def test_is_parent_removed_phone(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    assert await is_parent(hass, cfg([JULIE], {JULIE: users["julie"].id}), users["julie"].id)
    assert not await is_parent(hass, cfg([]), users["julie"].id)


async def test_phone_status_each_state(hass, users) -> None:
    ok = "notify.mobile_app_ok"
    unbound = "notify.mobile_app_unbound"
    missing = "notify.mobile_app_missing"
    changed = "notify.mobile_app_changed"
    ambiguous = "notify.mobile_app_ambiguous"
    julie = users["julie"].id
    add_phone(hass, "OK", julie)
    add_phone(hass, "Unbound", julie)
    add_phone(hass, "Changed", users["kid"].id)
    add_phone(hass, "Ambiguous", julie)
    add_phone(hass, "Ambiguous", users["kid"].id)
    config = cfg(
        [ok, unbound, missing, changed, ambiguous, OTHER],
        {ok: julie, missing: julie, changed: julie, ambiguous: julie},
    )
    assert phone_status(hass, config) == {
        ok: {"owner": julie, "status": "ok"},
        unbound: {"owner": None, "status": "unbound"},
        missing: {"owner": julie, "status": "missing"},
        changed: {"owner": julie, "status": "changed"},
        ambiguous: {"owner": julie, "status": "ambiguous"},
    }


async def test_bind_owners_keeps_old_owner(hass, users) -> None:
    """Le téléphone de Julie a été recréé par la tablette : l'ancien propriétaire reste."""
    add_phone(hass, "iPhone de Julie", users["kid"].id)
    add_phone(hass, "iPhone de Marc", users["admin"].id)
    old = cfg([JULIE], {JULIE: users["julie"].id})
    bound = bind_owners(hass, cfg([JULIE, MARC]), old)
    assert bound.request_notify_owners == {JULIE: users["julie"].id, MARC: users["admin"].id}


async def test_bind_owners_ignores_client_owner(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    add_phone(hass, "iPhone de Marc", users["admin"].id)
    old = cfg([JULIE], {JULIE: users["julie"].id})
    new = cfg([JULIE, MARC], {JULIE: users["kid"].id, MARC: users["kid"].id})
    bound = bind_owners(hass, new, old)
    assert bound.request_notify_owners == {JULIE: users["julie"].id, MARC: users["admin"].id}
    assert bind_owners(hass, new, None).request_notify_owners == {
        JULIE: users["julie"].id, MARC: users["admin"].id
    }


async def test_bind_owners_rebind(hass, users) -> None:
    """App réinstallée par Julie sous un nouveau compte : réassociation explicite."""
    add_phone(hass, "iPhone de Julie", users["kid"].id)
    old = cfg([JULIE], {JULIE: users["julie"].id})
    bound = bind_owners(hass, cfg([JULIE]), old, rebind=[JULIE])
    assert bound.request_notify_owners == {JULIE: users["kid"].id}


async def test_bind_owners_unbound_kept_phone_stays_unbound(hass, users) -> None:
    """Un téléphone déjà listé sans propriétaire ne s'associe pas en silence."""
    add_phone(hass, "iPhone de Julie", users["kid"].id)
    old = cfg([JULIE])
    assert bind_owners(hass, cfg([JULIE]), old).request_notify_owners == {}
    bound = bind_owners(hass, cfg([JULIE]), old, rebind=[JULIE])
    assert bound.request_notify_owners == {JULIE: users["kid"].id}


@pytest.mark.parametrize("devices", [0, 2])
async def test_bind_owners_missing_device_raises(hass, users, devices) -> None:
    for _ in range(devices):
        add_phone(hass, "iPhone de Julie", users["julie"].id)
    with pytest.raises(ConfigError) as err:
        bind_owners(hass, cfg([JULIE]), None)
    assert JULIE in str(err.value)
    add_phone(hass, "iPhone de Marc", users["admin"].id)
    old = cfg([MARC], {MARC: users["admin"].id})
    with pytest.raises(ConfigError):
        bind_owners(hass, cfg([MARC, JULIE]), old, rebind=[MARC])


async def test_bind_owners_non_mobile_target(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    new = cfg([OTHER, JULIE], {OTHER: users["kid"].id})
    bound = bind_owners(hass, new, None)
    assert bound.request_notify_owners == {JULIE: users["julie"].id}
    assert bound.request_notify == (OTHER, JULIE)


class FakeEngine:
    """Moteur minimal : `config` et `set_config` suffisent à la migration."""

    def __init__(self, config) -> None:
        self.config = config
        self.saved = 0

    async def set_config(self, config) -> None:
        self.saved += 1
        self.config = config


async def test_migration_binds_unique_owner(
    hass, users, caplog: pytest.LogCaptureFixture
) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    engine = FakeEngine(cfg([JULIE]))
    with caplog.at_level(logging.INFO):
        await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {JULIE: users["julie"].id}
    assert engine.saved == 1
    assert f"Téléphone {JULIE} associé à l'utilisateur Julie" in caplog.text


async def test_migration_logs_user_id_when_user_unknown(
    hass, users, caplog: pytest.LogCaptureFixture
) -> None:
    add_phone(hass, "iPhone de Julie", "inconnu")
    engine = FakeEngine(cfg([JULIE]))
    with caplog.at_level(logging.INFO):
        await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {JULIE: "inconnu"}
    assert f"Téléphone {JULIE} associé à l'utilisateur inconnu" in caplog.text


async def test_migration_skips_ambiguous_and_missing(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    add_phone(hass, "iPhone de Julie", users["kid"].id)
    add_phone(hass, "Autre", "")
    engine = FakeEngine(cfg([JULIE, MARC, OTHER, "notify.mobile_app_autre"]))
    await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {}
    assert engine.saved == 0


async def test_migration_keeps_existing_owner(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["kid"].id)
    add_phone(hass, "iPhone de Marc", users["admin"].id)
    engine = FakeEngine(cfg([JULIE, MARC], {JULIE: users["julie"].id}))
    await migrate_phone_owners(hass, engine)
    assert engine.config.request_notify_owners == {
        JULIE: users["julie"].id,
        MARC: users["admin"].id,
    }


async def test_migration_noop_does_not_save(hass, users) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    engine = FakeEngine(cfg([JULIE], {JULIE: users["julie"].id}))
    await migrate_phone_owners(hass, engine)
    assert engine.saved == 0
    await migrate_phone_owners(hass, FakeEngine(None))


async def test_setup_entry_runs_migration(hass, users, make_env) -> None:
    add_phone(hass, "iPhone de Julie", users["julie"].id)
    env = await make_env(
        datetime(2026, 11, 3, 16, 30, tzinfo=ZoneInfo("America/Toronto")),
        {**EX, "request_notify": [JULIE]},
    )
    assert env.engine.config.request_notify_owners == {JULIE: users["julie"].id}
