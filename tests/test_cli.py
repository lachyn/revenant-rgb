"""Command line, run as a real process. Only commands that never open the keyboard are used here, or `-p` with
an inactive profile, so a keyboard plugged into the test machine is never written to."""
import os
import subprocess
import sys

import pytest

from conftest import ROOT


@pytest.fixture
def run(tmp_path):
    env = dict(os.environ, REVENANT_HOME=str(tmp_path), REVENANT_NO_BOOTSTRAP="1", REVENANT_LANG="en",
               PYTHONIOENCODING="utf-8")

    def run(*args):
        return subprocess.run([sys.executable, str(ROOT / "revenant.py"), *args], capture_output=True, text=True,
                              encoding="utf-8", env=env, timeout=60)
    return run


def test_version(run):
    r = run("--version")
    assert r.returncode == 0 and r.stdout.startswith("revenant ")


def test_status_and_presets(run):
    r = run("status")
    assert r.returncode == 0
    assert "active profile: default" in r.stdout
    assert "monokai" in run("profile", "list").stdout


def test_czech(run):
    assert "aktivní profil: default" in run("--lang", "cs", "status").stdout
    assert "použití:" in run("--lang", "cs", "web", "--help").stdout


def test_edit_inactive_profile(run):
    assert run("profile", "new", "other").returncode == 0
    r = run("-p", "other", "macro", "set", "hi", "text:Hi!", "enter")
    assert r.returncode == 0 and "keyboard unchanged" in r.stdout
    r = run("-p", "other", "remap", "f1=macro:hi", "caps=disable")
    assert r.returncode == 0
    assert "caps = disable" in run("-p", "other", "remap").stdout
    r = run("-p", "other", "macro", "delete", "hi")
    assert r.returncode != 0 and "assigned to keys f1" in r.stderr


def test_errors(run):
    r = run("-p", "default", "remap", "caps=nonsense")
    assert r.returncode != 0 and "unknown function" in r.stderr
    r = run("profile", "delete", "default")
    assert r.returncode != 0 and "can't be deleted" in r.stderr


def test_lang_command(run):
    assert "setting: cs" in run("lang", "cs").stdout.replace("nastavení: cs", "setting: cs")
    assert "language: English (setting: en)" in run("lang", "en").stdout
