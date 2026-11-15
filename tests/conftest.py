"""Shared fixtures. Tests never touch a real keyboard: `keyboard` replaces it with a recorder, and every test that
writes files runs in a temporary config folder (`home`)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import revenant as rv  # noqa: E402


class FakeDevice:
    def close(self):
        pass


class FakeKeyboard:
    """stands in for rv.Revenant: records every call (set_keys, set_effect, write_macros, ...) and reports success"""
    instances = []

    def __init__(self, verbose=False):
        self.dev = FakeDevice()
        self.calls = []
        FakeKeyboard.instances.append(self)

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return True
        return call


@pytest.fixture
def home(tmp_path, monkeypatch):
    """isolated config folder, English UI"""
    monkeypatch.setattr(rv, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(rv, "PROFILE_DIR", tmp_path / "profiles")
    monkeypatch.setattr(rv, "ACTIVE_FILE", tmp_path / "active")
    monkeypatch.setattr(rv, "CURRENT_FILE", tmp_path / "current.json")
    monkeypatch.setattr(rv, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.delenv("REVENANT_LANG", raising=False)
    rv.set_language("en")
    yield tmp_path
    rv.set_language("en")


@pytest.fixture
def keyboard(monkeypatch):
    FakeKeyboard.instances.clear()
    monkeypatch.setattr(rv, "Revenant", FakeKeyboard)
    monkeypatch.setattr(rv, "keyboard_present", lambda: True)
    return FakeKeyboard
