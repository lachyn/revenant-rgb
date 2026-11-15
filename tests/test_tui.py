"""TUI smoke tests (headless, via Textual's test pilot)."""
import asyncio

import pytest

from conftest import rv

textual_app = pytest.importorskip("textual.app")


def run_headless(monkeypatch, script):
    """run rv.run_tui() with App.run replaced by a headless pilot running `script(app, pilot)`"""
    results = []

    def fake_run(app, *args, **kwargs):
        async def go():
            async with app.run_test(size=(150, 45)) as pilot:
                await pilot.pause(0.5)
                results.append(await script(app, pilot))
        asyncio.run(go())
        return app.return_value

    monkeypatch.setattr(textual_app.App, "run", fake_run)
    rv.run_tui()
    return results


def test_tui_shows_profile_and_selects_keys(home, keyboard, monkeypatch):
    async def script(app, pilot):
        app.query_one("#grp-wasd").press()           # may be below the fold on a small test screen
        await pilot.pause()
        tabs = [str(t.label) for t in app.query("Tab")]
        status = str(app.query_one("#status").render())
        selected = sorted(app.selected)
        await pilot.press("ctrl+q")
        return tabs, status, selected

    [(tabs, status, selected)] = run_headless(monkeypatch, script)
    assert tabs[:4] == ["Lighting", "Key functions", "Macros", "Game mode"]     # + nested: Custom colours | Effect
    assert "Custom colours" in tabs and "Effect" in tabs
    assert selected == ["a", "d", "s", "w"]
    assert "Keys selected: 4" in status


def test_tui_language_switch(home, keyboard, monkeypatch):
    async def script(app, pilot):
        first = str(app.query("Tab").first().label)
        if rv.LANG == "en":
            await pilot.press("ctrl+l")                         # opens the language picker
            await pilot.pause()
            assert type(app.screen).__name__ == "LanguageScreen"
            app.screen.dismiss("cs")
        else:
            await pilot.press("ctrl+q")
        await pilot.pause()
        return first

    assert run_headless(monkeypatch, script) == ["Lighting", "Podsvícení"]
    assert rv.load_settings()["lang"] == "cs"


def test_tui_confirms_before_loading_over_unsaved_changes(home, keyboard, monkeypatch):
    async def script(app, pilot):
        app.toggle_key("w"); app.paint_selected("ff0000")      # unsaved change
        await pilot.pause(0.3)
        ol = app.query_one("#pf_list")
        ol.highlighted = app._pf_names.index("nord")
        app._pf_load()
        await pilot.pause()
        asked = type(app.screen).__name__
        app.screen.dismiss(False)                               # Cancel
        await pilot.pause()
        kept = app.pname
        await pilot.press("ctrl+q")
        return asked, kept

    assert run_headless(monkeypatch, script) == [("ConfirmScreen", "default")]


def test_tui_offers_setup_when_access_denied(home, monkeypatch):
    def denied(*args, **kwargs):
        raise rv.RevenantAccessError("open failed")
    monkeypatch.setattr(rv, "Revenant", denied)
    monkeypatch.setattr(rv, "setup_kind", lambda: "udev")

    async def script(app, pilot):
        await pilot.pause(0.5)
        screen = type(app.screen).__name__
        await pilot.click("#setup_no")
        await pilot.pause()
        await pilot.press("ctrl+q")
        return screen

    assert run_headless(monkeypatch, script) == ["SetupScreen"]


def test_tui_selection_shows_key_colour(home, keyboard, monkeypatch):
    rv.install_presets()
    rv.set_active("monokai")

    async def script(app, pilot):
        app.toggle_key("q")                      # a custom (non-palette) colour
        await pilot.pause()
        single = app.current
        app.toggle_key("f1")                     # the last clicked key shows its colour
        await pilot.pause()
        second = app.current
        app.toggle_key("f1")                     # deselecting: the remaining selection (q) shows its colour
        await pilot.pause()
        after = app.current
        await pilot.press("ctrl+q")
        return single, second, after

    keys = rv.load_profile("monokai")["lighting"]["keys"]
    assert run_headless(monkeypatch, script) == [(keys["q"], keys["f1"], keys["q"])]
    assert not any(c[0] == "set_keys" for kb in keyboard.instances for c in kb.calls)   # nothing sent


def test_tui_unsaved_changes_and_save(home, keyboard, monkeypatch):
    async def script(app, pilot):
        clean = app.sub_title
        app.toggle_key("w")
        await pilot.pause()
        app.paint_selected("ff0000")                 # change -> current settings, not the profile
        await pilot.pause(0.3)
        dirty = app.sub_title
        await pilot.press("ctrl+s")                  # save to the active profile
        await pilot.pause(0.3)
        saved = app.sub_title
        await pilot.press("ctrl+q")
        return clean, dirty, saved

    [(clean, dirty, saved)] = run_headless(monkeypatch, script)
    assert "•" not in clean and "unsaved" in dirty and "•" not in saved
    assert rv.load_profile("default")["lighting"]["keys"]["w"] == "ff0000"
