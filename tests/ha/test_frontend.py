"""Frontend : l'intégration sert ses cartes et les injecte une seule fois."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.frontend import UrlManager
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.parental_control.const import DOMAIN
from custom_components.parental_control.frontend import async_register_frontend

_MANIFEST = Path(__file__).parents[2] / "custom_components" / DOMAIN / "manifest.json"
_VERSION = json.loads(_MANIFEST.read_text("utf-8"))["version"]
_URL = f"/parental_control_static/parental-cards.js?v={_VERSION}"


@pytest.fixture(autouse=True)
def frontend(hass: HomeAssistant) -> None:
    # Le composant `frontend` complet exige le paquet `home-assistant-frontend` : on pose son registre.
    hass.data["frontend_extra_module_url"] = UrlManager(lambda *_: None, [])


@pytest.fixture
def http(hass: HomeAssistant) -> MagicMock:
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    return hass.http


async def test_registers_static_path_and_module_once(hass: HomeAssistant, http) -> None:
    await async_register_frontend(hass)
    await async_register_frontend(hass)  # rechargement de l'entrée

    http.async_register_static_paths.assert_awaited_once()
    (config,) = http.async_register_static_paths.await_args.args[0]
    assert config.url_path == "/parental_control_static"
    assert config.cache_headers is False  # modules importés sans `?v=` : pas de cache périmé
    assert Path(config.path).joinpath("parental-cards.js").is_file()
    assert Path(config.path).joinpath("lib.js").is_file()
    assert sorted(hass.data["frontend_extra_module_url"].urls) == [_URL]


async def test_without_http_still_injects_module(hass: HomeAssistant) -> None:
    await async_register_frontend(hass)
    assert sorted(hass.data["frontend_extra_module_url"].urls) == [_URL]


async def test_entry_setup_registers_module_once(hass: HomeAssistant, http) -> None:
    for _ in range(2):  # setup puis rechargement
        entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"code_hash": ""})
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entry.entry_id)
    assert sorted(hass.data["frontend_extra_module_url"].urls) == [_URL]
    http.async_register_static_paths.assert_awaited_once()


async def test_without_frontend_injects_on_later_call(hass: HomeAssistant, http) -> None:
    del hass.data["frontend_extra_module_url"]
    await async_register_frontend(hass)
    assert "frontend_extra_module_url" not in hass.data

    # Le frontend se charge ensuite : le rechargement de l'entrée rattrape l'injection.
    hass.data["frontend_extra_module_url"] = UrlManager(lambda *_: None, [])
    await async_register_frontend(hass)
    assert sorted(hass.data["frontend_extra_module_url"].urls) == [_URL]
    http.async_register_static_paths.assert_awaited_once()


async def test_static_path_failure_is_retried(hass: HomeAssistant, http) -> None:
    http.async_register_static_paths.side_effect = [RuntimeError("boom"), None]
    await async_register_frontend(hass)  # l'échec n'interrompt pas le setup
    await async_register_frontend(hass)
    assert http.async_register_static_paths.await_count == 2
    assert sorted(hass.data["frontend_extra_module_url"].urls) == [_URL]
