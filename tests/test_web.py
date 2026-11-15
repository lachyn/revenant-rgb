"""Web UI server: API, security checks and translations, with a fake keyboard."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from conftest import rv


@pytest.fixture
def web(home, keyboard):
    srv = rv.make_web_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_port}"

    def call(path, body=None, headers=None):
        h = {"X-Revenant": "1", "Content-Type": "application/json"} if body is not None else {}
        h.update(headers or {})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
        except urllib.error.HTTPError as ex:
            return ex.code, json.loads(ex.read())
    yield call
    srv.shutdown()
    srv.server_close()


def test_static_files(web):
    status, html = web("/")
    assert status == 200 and b"app.js" in html
    assert web("/app.js")[0] == 200 and web("/style.css")[0] == 200
    assert web("/../revenant.py")[0] == 404


def test_state(web):
    status, st = web("/api/state")
    assert status == 200
    assert st["active"] == "default" and "monokai" in st["profiles"]
    assert st["device"]["state"] == "ok"
    assert st["lang"] == "en" and len(st["rows"]) == 6


def test_rejects_foreign_requests(web):
    assert web("/api/state", headers={"Host": "evil.example"})[0] == 403
    assert web("/api/apply", body={}, headers={"X-Revenant": ""})[0] == 403


def test_save_sends_to_keyboard(web, keyboard):
    _, st = web("/api/state")
    assert st["dirty"] is False
    prof = st["profile"]
    prof["lighting"].update(mode="keys", keys={"w": "ff0000"})
    status, r = web("/api/save", {"profile": prof, "parts": ["lighting"], "done": "ok!"})
    assert status == 200 and r["msg"] == "ok!"
    assert rv.load_current()["lighting"]["keys"] == {"w": "ff0000"}      # the current settings changed ...
    assert rv.load_profile("default")["lighting"]["keys"] == {}            # ... the saved profile did not
    assert r["state"]["dirty"] is True
    assert any(c[0] == "set_keys" for kb in keyboard.instances for c in kb.calls)


def test_profile_save_and_discard(web, keyboard):
    _, st = web("/api/state")
    prof = st["profile"]
    prof["lighting"]["color"] = "123456"
    web("/api/save", {"profile": prof, "parts": ["lighting"]})
    status, r = web("/api/discard", {})
    assert status == 200 and r["state"]["dirty"] is False
    assert rv.load_current()["lighting"]["color"] == rv.load_profile("default")["lighting"]["color"] != "123456"
    web("/api/save", {"profile": prof, "parts": ["lighting"]})
    status, r = web("/api/profile-save", {})
    assert status == 200 and r["state"]["dirty"] is False
    assert rv.load_profile("default")["lighting"]["color"] == "123456"


def test_save_as_makes_new_profile_active(web):
    _, st = web("/api/state")
    prof = st["profile"]
    prof["lighting"]["color"] = "abcdef"
    web("/api/save", {"profile": prof, "parts": []})
    status, r = web("/api/copy", {"name": "mine"})
    assert status == 200 and r["state"]["active"] == "mine" and r["state"]["dirty"] is False
    assert rv.load_profile("mine")["lighting"]["color"] == "abcdef"
    assert rv.load_profile("default")["lighting"]["color"] != "abcdef"


def test_save_rejects_invalid(web):
    _, st = web("/api/state")
    prof = st["profile"]
    prof["lighting"]["color"] = "nope"
    status, r = web("/api/save", {"profile": prof, "parts": ["lighting"]})
    assert status == 400 and "colour" in r["error"]


def test_profile_actions(web):
    assert web("/api/new", {"name": "mine"})[0] == 200
    assert web("/api/new", {"name": "mine"})[0] == 400
    assert web("/api/new", {"name": "../escape"})[0] == 400
    status, r = web("/api/use", {"name": "mine"})
    assert status == 200 and r["state"]["active"] == "mine"
    assert web("/api/delete", {"name": "mine"})[0] == 400          # active
    assert web("/api/delete", {"name": "ocean"})[0] == 200
    assert "ocean" not in web("/api/state")[1]["profiles"]


def test_language_switch(web):
    status, r = web("/api/lang", {"lang": "cs"})
    assert status == 200 and r["msg"] == "Jazyk: Čeština"
    assert r["state"]["lang"] == "cs" and r["state"]["strings"]["Saved"] == "Uloženo"
    assert web("/api/lang", {"lang": "xx"})[0] == 400


def test_device_poll(web):
    status, d = web("/api/device")
    assert status == 200 and d == {"state": "ok", "error": "", "setup": None}
