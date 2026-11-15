"""Profiles, the bundled sample profiles and sending a profile to the keyboard."""
import json

import pytest

from conftest import ROOT, rv

PRESETS = sorted((ROOT / "revenant_profiles").glob("*.json"))


def test_presets_exist():
    names = {p.stem for p in PRESETS}
    assert {"default", "monokai", "monokai-vivid", "nord", "ocean", "synthwave", "fps"} <= names


@pytest.mark.parametrize("path", PRESETS, ids=lambda p: p.stem)
def test_preset_is_valid(path):
    prof = rv.normalize_profile(json.loads(path.read_text(encoding="utf-8")))
    rv._check_lighting(prof["lighting"])
    rv.validate_profile(prof)
    assert not prof["macros"], "sample profiles must not ship macros (they could contain personal text)"


def test_first_run_installs_presets(home):
    assert rv.get_active() == "default"
    assert rv.list_profiles() == sorted(p.stem for p in PRESETS)


def test_install_presets_keeps_existing(home):
    rv.PROFILE_DIR.mkdir(parents=True)
    mine = rv._template()
    mine["lighting"]["color"] = "123456"
    rv.save_profile("monokai", mine)
    added = rv.install_presets()
    assert "monokai" not in added and "nord" in added
    assert rv.load_profile("monokai")["lighting"]["color"] == "123456"


def test_normalize_upgrades_old_format():
    prof = rv.normalize_profile({"lighting": {"keys": {"w": "ff0000"}, "brightness": 5}})
    assert prof["lighting"]["mode"] == "keys"
    assert prof["lighting"]["key_brightness"] == 5
    assert prof["gamemode"] == rv.PROFILE_TEMPLATE["gamemode"]


def test_validate_profile():
    prof = rv._template()
    prof["macros"] = {"hi": ["text:Hi", "enter"]}
    prof["remap"] = {"f1": "macro:hi", "caps": "disable"}
    macros, actions = rv.validate_profile(prof)
    assert len(macros) == 1 and actions[rv.KEYS["f1"]][0] == 0x06
    prof["remap"]["f2"] = "macro:missing"
    with pytest.raises(ValueError):
        rv.validate_profile(prof)


def test_sync_sends_every_part(keyboard):
    prof = rv._template()
    prof["lighting"].update(mode="keys", keys={"w": "ff0000"}, base="101010")
    prof["remap"] = {"caps": "disable"}
    kb = keyboard()
    assert rv.sync(kb, prof)
    assert [c[0] for c in kb.calls] == ["set_keys", "write_macros", "write_keymap", "set_gamemode"]
    colors, base, brightness = kb.calls[0][1]
    assert colors == {"w": (255, 0, 0)} and base == (16, 16, 16) and brightness == 16


def test_sync_validates_before_writing(keyboard):
    prof = rv._template()
    prof["remap"] = {"f1": "macro:missing"}
    kb = keyboard()
    with pytest.raises(ValueError):
        rv.sync(kb, prof)
    assert kb.calls == []


def test_describe_profile_translated(home):
    prof = rv.normalize_profile(json.loads((ROOT / "revenant_profiles" / "fps.json").read_text()))
    assert "lighting: custom key colours" in rv.describe_profile(prof)
    assert "game mode: on, blocks Win" in rv.describe_profile(prof)
    rv.set_language("cs")
    assert "podsvícení: vlastní barvy kláves" in rv.describe_profile(prof)


def test_current_settings_model(home):
    """edits go to the current settings; profiles change only when saved explicitly"""
    assert rv.get_active() == "default" and not rv.is_dirty()
    cur = rv.load_current()
    cur["lighting"]["color"] = "112233"
    rv.save_current(cur)
    assert rv.is_dirty()
    assert rv.load_profile("default")["lighting"]["color"] != "112233"

    rv.discard_changes()
    assert not rv.is_dirty() and rv.load_current()["lighting"]["color"] != "112233"

    cur = rv.load_current()
    cur["lighting"]["color"] = "445566"
    rv.save_current(cur)
    assert rv.save_current_as() == "default"
    assert not rv.is_dirty() and rv.load_profile("default")["lighting"]["color"] == "445566"


def test_use_profile_replaces_current_settings(home):
    rv.get_active()
    cur = rv.load_current()
    cur["lighting"]["color"] = "778899"
    rv.save_current(cur)
    prof = rv.use_profile("nord")
    assert rv.get_active() == "nord" and rv.load_current() == prof and not rv.is_dirty()
    assert rv.load_profile("default")["lighting"]["color"] != "778899"      # never saved


def test_save_as_new_profile(home):
    rv.get_active()
    cur = rv.load_current()
    cur["lighting"]["color"] = "a1b2c3"
    rv.save_current(cur)
    assert rv.save_current_as("mine") == "mine"
    assert rv.get_active() == "mine" and not rv.is_dirty()
    with pytest.raises(ValueError):
        rv.save_current_as("../escape")


def test_current_settings_start_from_active_profile(home):
    """upgrade from older versions: no current.json yet -> copy of the active profile"""
    rv.get_active()
    rv.set_active("ocean")
    rv.CURRENT_FILE.unlink(missing_ok=True)
    assert rv.load_current() == rv.load_profile("ocean") and rv.CURRENT_FILE.exists()
