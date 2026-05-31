"""Validation du manifest plugin_info/info.json (D5).

Garantit que le manifest reste conforme aux attentes du canal stable Jeedom
et aux préférences du projet (monolingue fr_FR, licence AGPL, version SemVer).
"""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFO_PATH = os.path.join(ROOT, "plugin_info", "info.json")

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@pytest.fixture(scope="module")
def info():
    with open(INFO_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_info_json_is_valid_json(info):
    assert isinstance(info, dict)


def test_required_fields_present(info):
    for field in ("id", "name", "pluginVersion", "description", "licence", "author", "require"):
        assert field in info, f"Champ requis manquant : {field}"


def test_id_is_projote(info):
    assert info["id"] == "ProJote"


def test_version_is_semver(info):
    assert SEMVER_RE.match(info["pluginVersion"]), (
        f"pluginVersion '{info['pluginVersion']}' n'est pas au format X.Y.Z"
    )


def test_licence_agpl(info):
    assert "AGPL" in info["licence"].upper()


def test_monolingual_fr_fr(info):
    # Préférence projet : monolingue fr_FR, aucune référence en_US.
    assert "fr_FR" in info["description"]
    assert "en_US" not in info["description"], "Aucune description en_US attendue"
    if "language" in info:
        assert "en_US" not in info["language"], "Aucune langue en_US attendue"


def test_require_is_supported(info):
    # Jeedom 4.4 minimum.
    assert info["require"] in ("4.4", "4.5", "4.6", "5.0")
