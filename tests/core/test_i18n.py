"""Textes du serveur : catalogue `en`/`fr`, choix de la langue, codes d'erreur de config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.parental_control.core.config_io import ConfigError, parse_config
from custom_components.parental_control.core.i18n import MESSAGES, base_language, msg

COMPONENT = Path(__file__).parents[2] / "custom_components" / "parental_control"


def _keys(node: object, prefix: str = "") -> set[str]:
    if not isinstance(node, dict):
        return {prefix}
    out: set[str] = set()
    for key, value in node.items():
        out |= _keys(value, f"{prefix}.{key}" if prefix else key)
    return out


def _load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def test_base_language():
    assert base_language("fr-CA") == "fr"
    assert base_language("en-GB") == "en"
    assert base_language("de") == "en"
    assert base_language(None) == "en"
    assert base_language("FR") == "fr"
    assert base_language("fr_BE") == "fr"


def test_same_keys():
    assert set(MESSAGES) == {"en", "fr"}
    assert set(MESSAGES["en"]) == set(MESSAGES["fr"])


def test_fallbacks():
    assert msg("fr", "no.such.key") == "no.such.key"
    assert msg("de", "notify.title") == MESSAGES["en"]["notify.title"]
    assert msg("fr", "notify.title") == "Contrôle parental"


def test_params():
    assert msg("en", "warn.kid", name="Hugo", minutes=5) == "Hugo: screens end in 5 min"
    assert msg("fr", "warn.kid", name="Hugo", minutes=5) == "Hugo : fin des écrans dans 5 min"


def test_config_error_code():
    with pytest.raises(ConfigError) as e:
        parse_config({"version": 3, "kids": [{"id": "a", "name": "A", "profiles": {}}],
                      "resources": []})
    assert e.value.code and e.value.path.startswith("kids[0]")
    assert str(e.value) == f"{e.value.path}: " + msg("en", f"config.{e.value.code}",
                                                     **e.value.params)


def test_translation_files_same_keys():
    en, fr = _load("translations/en.json"), _load("translations/fr.json")
    assert _keys(en) == _keys(fr)
    assert _keys(_load("strings.json")) == _keys(en)


def test_config_error_translations_match_catalogue():
    """Chaque code d'erreur de config a sa clé `config_<code>` dans `exceptions`, en `en` et
    en `fr`, au texte du catalogue précédé du chemin."""
    codes = {k.removeprefix("config.") for k in MESSAGES["en"] if k.startswith("config.")}
    assert codes
    for lang, name in (("en", "translations/en.json"), ("fr", "translations/fr.json"),
                       ("en", "strings.json")):
        exceptions = _load(name)["exceptions"]
        keys = {k.removeprefix("config_") for k in exceptions if k.startswith("config_")}
        assert keys == codes, name
        for code in codes:
            sep = " : " if lang == "fr" else ": "
            assert exceptions[f"config_{code}"]["message"] == (
                "{path}" + sep + MESSAGES[lang][f"config.{code}"]
            ), (name, code)


def test_reason_texts():
    """Chaque code de raison de l'évaluateur a son texte, en anglais et en français."""
    assert msg("en", "reason.allowed_until", until="16:00") == "Screens allowed until 16:00"
    assert msg("fr", "reason.allowed_until", until="16:00") == "Écrans autorisés jusqu'à 16:00"
    assert msg("en", "reason.blocked") == "Blocked"
    assert msg("fr", "reason.blocked") == "Bloqué"


def test_english_durations():
    from custom_components.parental_control.core.i18n import duration_text

    assert [duration_text("en", m) for m in (45, 120, 90, 65)] == [
        "45 min", "2 h", "1 h 30 min", "1 h 5 min"]
    assert [duration_text("fr", m) for m in (45, 120, 90, 65)] == [
        "45 min", "2 h", "1 h 30", "1 h 05"]


def test_global_device_name_translated():
    for name, expected in (("strings.json", "Parental control"),
                           ("translations/en.json", "Parental control"),
                           ("translations/fr.json", "Contrôle parental")):
        assert _load(name)["device"]["global"]["name"] == expected
