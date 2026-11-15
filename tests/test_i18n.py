"""Translations and language selection."""
import subprocess
import sys

import pytest

from conftest import ROOT, rv


def test_catalog_complete():
    """every source string has a translation with the same {placeholders} (tools/i18n_check.py)"""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "i18n_check.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    assert "0 missing" in r.stdout


def test_tr(home):
    assert rv.tr("Saved") == "Saved"
    rv.set_language("cs")
    assert rv.tr("Saved") == "Uloženo"
    assert rv.tr("unknown key '{name}'", name="x") == "neznámá klávesa 'x'"
    assert rv.tr("text that is not in the catalog") == "text that is not in the catalog"


@pytest.mark.parametrize("system, expected", [
    ("cs_CZ.UTF-8", "cs"), ("Czech_Czechia", "cs"), ("sk_SK", "cs"), ("cs-CZ", "cs"),
    ("en_US.UTF-8", "en"), ("de_DE", "en"), ("", "en"),
])
def test_resolve_language_from_system(home, monkeypatch, system, expected):
    monkeypatch.setattr(rv, "system_language", lambda: system)
    assert rv.resolve_language() == expected


def test_language_setting_and_override(home, monkeypatch):
    monkeypatch.setattr(rv, "system_language", lambda: "en_US")
    rv.save_settings(lang="cs")
    assert rv.resolve_language() == "cs"
    monkeypatch.setenv("REVENANT_LANG", "en")
    assert rv.resolve_language() == "en"
    assert rv.resolve_language("cs") == "cs"
