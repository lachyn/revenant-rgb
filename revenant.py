#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["hidapi>=0.14", "textual>=0.80", "psutil>=5.9"]
# ///
"""
revenant - cross-platform RGB driver for the CZC.Gaming Revenant keyboard
(SONiX chip, USB 0C45:8006). Works on Windows, Linux and macOS via hidapi.

  python revenant.py            TUI
  python revenant.py <prikaz>   command line (python revenant.py --help)

Missing libraries are installed automatically into a private venv on first run
(or run it with `uv run revenant.py`, which reads the dependency block above).

Protocol reverse-engineered from the official CZC software (V1.00.238n):
all traffic is 64-byte HID feature reports (report ID 0) on interface 1.

  04 ab              begin session; followed by one 64-byte random block
  04 02              query -> reply carries a 16-bit sum of the last block(s)
  04 13 .. .. [n]    begin write of n data packets (n at byte 8)
  <n data packets>   lighting table (see build_table)
  04 f0              commit

Effect record (16 bytes):
  [id] [R] [G] [B] 00 00 00 00 [rainbow 0/1] [brightness 0-16] [speed 0-16] [dir] 00 00 aa 55
"""
__version__ = "0.1.1"

import argparse, copy, importlib.util, json, os, subprocess, sys, threading, time
from pathlib import Path

REQUIREMENTS = {"hid": "hidapi>=0.14", "textual": "textual>=0.80", "psutil": "psutil>=5.9"}

# ---------------------------------------------------------------- settings + i18n
# Source strings are English and wrapped in tr(); translations live in revenant_i18n/<lang>.json as
# {"English text": "translation"}. Missing translations fall back to English. Check: python tools/i18n_check.py
CONFIG_DIR = Path(os.environ.get("REVENANT_HOME", Path.home() / ".config" / "revenant"))
SETTINGS_FILE = CONFIG_DIR / "settings.json"
LANGUAGES = {"en": "English", "cs": "Čeština"}
I18N_DIR = Path(__file__).resolve().with_name("revenant_i18n")
LANG = "en"
_catalog = {}


def load_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(**values):
    data = load_settings()
    data.update(values)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def system_language():
    """the user's UI language as reported by the OS (e.g. 'cs_CZ.UTF-8', 'Czech_Czechia', 'en-US')"""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(var, "")
        if v and v not in ("C", "POSIX") and not v.startswith("C."):
            return v
    try:
        if os.name == "nt":
            import ctypes, locale
            return locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
        if sys.platform == "darwin":
            return subprocess.run(["defaults", "read", "-g", "AppleLocale"], capture_output=True,
                                  text=True, timeout=2).stdout.strip()
        import locale
        return locale.getlocale()[0] or ""
    except Exception:
        return ""


def resolve_language(value=None):
    """'cs' / 'en' from an explicit value, REVENANT_LANG, settings.json or the system ('auto')"""
    v = (value or os.environ.get("REVENANT_LANG") or load_settings().get("lang") or "auto").lower()
    if v == "auto":
        v = system_language().lower()
    return "cs" if v.startswith(("cs", "cz", "sk", "czech", "slovak")) else "en"


def set_language(lang):
    global LANG, _catalog
    LANG = lang if lang in LANGUAGES else "en"
    _catalog = {}
    if LANG != "en":
        try:
            _catalog = json.loads((I18N_DIR / f"{LANG}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass


def N_(text):
    """mark a string for translation without translating it yet (it is passed to tr() later)"""
    return text


def tr(text, **values):
    """translate an English source string, then fill {placeholders}"""
    s = _catalog.get(text, text)
    return s.format(**values) if values else s


set_language(resolve_language())


def _venv_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "revenant" / "venv"


def ensure_dependencies():
    """If a library is missing, install all of them into a private venv and re-run this script there.
    Disable with REVENANT_NO_BOOTSTRAP=1."""
    missing = [pkg for mod, pkg in REQUIREMENTS.items() if importlib.util.find_spec(mod) is None]
    if not missing or os.environ.get("REVENANT_NO_BOOTSTRAP"):
        return
    manual = tr("Install them manually:  pip install {pkgs}\nor run with uv:        uv run revenant.py",
                pkgs=" ".join(REQUIREMENTS.values()))
    vdir = _venv_dir()
    py = vdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    stage = os.environ.get("_REVENANT_BOOTSTRAP", "")
    try:
        if Path(sys.prefix).resolve() != vdir.resolve():
            if stage:
                raise RuntimeError(tr("could not start {path}", path=py))
            if not py.exists():
                print(tr("First run: creating environment {path} ...", path=vdir), file=sys.stderr)
                import venv
                venv.EnvBuilder(with_pip=True).create(vdir)
            stage = "venv"                       # switch to the private venv (installs there if needed)
        elif stage != "installed":
            print(tr("Installing {pkgs} (first run only) ...", pkgs=", ".join(missing)), file=sys.stderr)
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                                   *REQUIREMENTS.values()])
            stage, py = "installed", Path(sys.executable)
        else:
            raise RuntimeError(tr("missing {pkgs}", pkgs=", ".join(missing)))
    except Exception as ex:
        hint = "\nDebian/Ubuntu: sudo apt install python3-venv" if sys.platform.startswith("linux") else ""
        sys.exit(tr("Automatic installation of the libraries failed: {error}", error=ex) + f"{hint}\n{manual}")
    env = dict(os.environ, _REVENANT_BOOTSTRAP=stage)
    cmd = [str(py), os.path.abspath(__file__), *sys.argv[1:]]
    if os.name == "nt":                 # no real exec() on Windows
        if Path(sys.executable).name.lower() == "pythonw.exe":     # keep running without a console window
            cmd[0] = str(py.with_name("pythonw.exe"))
        sys.exit(subprocess.call(cmd, env=env))
    os.execve(str(py), cmd, env)


if __name__ == "__main__":
    ensure_dependencies()

try:
    if sys.platform.startswith("linux"):
        # The PyPI wheel's default 'hid' module uses libusb on Linux: it needs raw USB permissions and detaches
        # the kernel driver (the keyboard stops typing). 'hidraw' from the same package uses /dev/hidraw*.
        try:
            import hidraw as hid
        except ImportError:
            import hid
    else:
        import hid
except ImportError:
    hid = None

if hid is not None and sys.platform == "darwin":
    # hidapi opens devices exclusively (seize) on macOS by default, which the system refuses for keyboards
    # ("open failed" on the control interface even with Input Monitoring allowed). Non-exclusive also keeps
    # the keyboard typing and lets the TUI, web UI and CLI share it. The wheel exports the C call, not a wrapper.
    try:
        import ctypes
        ctypes.CDLL(hid.__file__).hid_darwin_set_open_exclusive(0)
    except (OSError, AttributeError):
        pass


class RevenantError(RuntimeError):
    """keyboard not found / cannot be opened"""


class RevenantNotFound(RevenantError):
    """no keyboard connected by cable"""


class RevenantAccessError(RevenantError):
    """keyboard is connected but cannot be opened (permissions, another program)"""

VID, PID = 0x0C45, 0x8006

EFFECTS = {
    "static": 0x01, "press-on": 0x02, "press-off": 0x03, "sparkle": 0x04,
    "rain": 0x05, "colors": 0x06, "breathing": 0x07, "spectrum": 0x08,
    "center-wave": 0x09, "vertical-wave": 0x0A, "horizontal-wave": 0x0B,
    "rotating": 0x0C, "explosion": 0x0D, "start": 0x0E, "ripple": 0x0F,
    "snake": 0x10, "pulse": 0x11, "disco": 0x12, "lines": 0x13, "custom": 0x80,
}

# Per-key LED matrix: index = row * 18 + col  (layout from the official software, verified on Esc and A)
_LAYOUT = {
    0: "esc f1 f2 f3 f4 f5 f6 f7 f8 f9 f10 f11 f12",
    1: "` 1 2 3 4 5 6 7 8 9 0 - = numlock num/ num*",
    2: "tab q w e r t y u i o p [ ] num7 num8 num9",
    3: "caps a s d f g h j k l ; ' \\ num4 num5 num6",
    4: "lshift z x c v b n m , . / rshift enter num1 num2 num3",
    5: "lctrl win lalt space ralt fn menu rctrl left down up right backspace num0 num. numenter",
}
KEYS = {}
for _row, _names in _LAYOUT.items():
    for _col, _n in enumerate(_names.split(), start=1):
        KEYS[_n] = _row * 18 + _col
for _col, _n in {4: "prtsc", 5: "scrolllock", 7: "pause", 8: "insert", 9: "home", 10: "pgup",
                 11: "delete", 12: "end", 13: "pgdn", 14: "num-", 15: "num+"}.items():
    KEYS[_n] = 6 * 18 + _col
KEY_ALIASES = {"escape": "esc", "shift": "lshift", "ctrl": "lctrl", "alt": "lalt", "del": "delete",
               "ins": "insert", "bksp": "backspace", "return": "enter", "capslock": "caps",
               "pageup": "pgup", "pagedown": "pgdn", "print": "prtsc", "grave": "`"}
KEY_GROUPS = {
    "all": list(KEYS),
    "wasd": ["w", "a", "s", "d"],
    "arrows": ["up", "down", "left", "right"],
    "fkeys": [f"f{i}" for i in range(1, 13)],
    "numbers": list("1234567890"),
    "letters": list("qwertyuiopasdfghjklzxcvbnm"),
    "numpad": [k for k in KEYS if k.startswith("num")],
    "nav": ["insert", "home", "pgup", "delete", "end", "pgdn"],
    "mods": ["lshift", "rshift", "lctrl", "rctrl", "lalt", "ralt", "win", "fn", "menu"],
}


def resolve_keys(name):
    n = name.lower()
    n = KEY_ALIASES.get(n, n)
    if n in KEY_GROUPS:
        return [KEYS[k] for k in KEY_GROUPS[n]]
    if n in KEYS:
        return [KEYS[n]]
    raise KeyError(name)


# Default record values as sent by the official software
DEFAULT_COLOR = (0x00, 0x00, 0xFF)
RAINBOW_DEFAULT = {0x01: 0, 0x06: 0, 0x07: 0, 0x08: 0, 0x80: 0}


def record(eid, rgb=DEFAULT_COLOR, rainbow=None, brightness=16, speed=12, direction=0):
    if rainbow is None:
        rainbow = RAINBOW_DEFAULT.get(eid, 1)
    if eid == 0x80:
        speed, rgb = 0, (0, 0, 0)
    r, g, b = rgb
    return bytes([eid, r, g, b, 0, 0, 0, 0, int(rainbow), brightness, speed, direction, 0, 0, 0xAA, 0x55])


def build_table(active, keymap=None):
    """active: 16-byte record of the effect to show. keymap: optional {index: (r,g,b)} for 'custom'."""
    recs = []
    for eid in list(range(0x01, 0x14)) + [0x80]:
        recs.append(active if eid == active[0] else record(eid))
    table = b"".join(recs)                                   # 320 B = 5 packets
    pkts = [table[i:i + 64] for i in range(0, 320, 64)]
    pkts += [bytes(64)] * 3                                  # reserved
    keys = bytearray(b"\x80\x00\x00\x00" * 144)              # per-key table, 9 packets
    for idx, (r, g, b) in (keymap or {}).items():
        keys[idx * 4: idx * 4 + 4] = bytes([0x80, r, g, b])
    pkts += [bytes(keys[i:i + 64]) for i in range(0, len(keys), 64)]
    pkts.append(active + bytes(48))                          # active effect
    assert len(pkts) == 18
    return pkts


# ---------------------------------------------------------------- key functions
# HID keyboard usage codes
HID = {c: 0x04 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")}
HID.update({c: 0x1E + i for i, c in enumerate("1234567890")})
HID.update({"enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C, "-": 0x2D,
            "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33, "'": 0x34, "`": 0x35, ",": 0x36,
            ".": 0x37, "/": 0x38, "caps": 0x39, "prtsc": 0x46, "scrolllock": 0x47, "pause": 0x48,
            "insert": 0x49, "home": 0x4A, "pgup": 0x4B, "delete": 0x4C, "end": 0x4D, "pgdn": 0x4E,
            "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52, "numlock": 0x53, "num/": 0x54,
            "num*": 0x55, "num-": 0x56, "num+": 0x57, "numenter": 0x58, "num0": 0x62, "num.": 0x63,
            "menu": 0x65, "lctrl": 0xE0, "lshift": 0xE1, "lalt": 0xE2, "win": 0xE3, "rctrl": 0xE4,
            "rshift": 0xE5, "ralt": 0xE6, "rwin": 0xE7})
HID.update({f"f{i}": 0x3A + i - 1 for i in range(1, 13)})
HID.update({f"f{i}": 0x68 + i - 13 for i in range(13, 25)})
HID.update({f"num{i}": 0x59 + i - 1 for i in range(1, 10)})
HID_ALIASES = dict(KEY_ALIASES, ctrl="lctrl", shift="lshift", alt="lalt", gui="win", cmd="win", super="win")

# HID consumer usage codes (verified: voldown)
MEDIA = {"volup": 0xE9, "voldown": 0xEA, "mute": 0xE2, "play": 0xCD, "next": 0xB5, "prev": 0xB6,
         "stop": 0xB7, "mail": 0x18A, "calc": 0x192, "mycomputer": 0x194, "browser": 0x223}
MOUSE_BUTTONS = {"left": 1, "right": 2, "middle": 4, "back": 8, "forward": 16}
MACRO_MODES = {"once": 0, "repeat": 1, "toggle": 2}


def hid_code(name):
    n = name.lower()
    n = HID_ALIASES.get(n, n)
    if n not in HID:
        raise ValueError(tr("unknown key '{name}'", name=name))
    return HID[n]


def encode_action(spec, macro_index=None):
    """text -> 4-byte key function.
    default | disable | key:X | combo:ctrl+shift+esc | media:volup | mouse:left|right|middle|back|forward|wheelup|wheeldown
    | macro:NAME[:once|:repeat:N|:toggle]"""
    s = spec.strip()
    kind, _, arg = s.partition(":")
    kind = kind.lower()
    if kind == "default":
        return bytes(4)
    if kind in ("disable", "disabled", "off"):
        return bytes([0x05, 0x03, 0, 0])
    if kind == "key":
        return bytes([0x02, 0, hid_code(arg), 0])
    if kind == "combo":
        ks = [hid_code(k) for k in arg.split("+") if k]
        if not 1 <= len(ks) <= 3:
            raise ValueError(tr("combo: 1 to 3 keys, e.g. combo:ctrl+shift+esc"))
        return bytes([0x07] + ks + [0] * (3 - len(ks)))
    if kind == "media":
        if arg.lower() not in MEDIA:
            raise ValueError("media: " + ", ".join(MEDIA))
        c = MEDIA[arg.lower()]
        return bytes([0x03, c & 0xFF, c >> 8, 0])
    if kind == "mouse":
        a = arg.lower()
        if a in MOUSE_BUTTONS:
            return bytes([0x01, 0x01, MOUSE_BUTTONS[a], 0])
        if a in ("wheelup", "wheeldown"):
            return bytes([0x01, 0x03, 0x01 if a == "wheelup" else 0xFF, 0])
        raise ValueError("mouse: " + ", ".join(list(MOUSE_BUTTONS) + ["wheelup", "wheeldown"]))
    if kind == "macro":
        parts = arg.split(":")
        name, mode = parts[0], (parts[1].lower() if len(parts) > 1 else "once")
        count = int(parts[2]) if len(parts) > 2 else (1 if mode == "repeat" else 0)
        if macro_index is None or name not in macro_index:
            raise ValueError(tr("macro '{name}' does not exist", name=name))
        if mode not in MACRO_MODES or not 0 <= count <= 255:
            raise ValueError(tr("macro:NAME[:once|:repeat:N|:toggle]"))
        return bytes([0x06, macro_index[name], MACRO_MODES[mode], count])
    if len(s) and (s.lower() in HID or s.lower() in HID_ALIASES):   # bare key name = key:X
        return encode_action("key:" + s)
    raise ValueError(tr("unknown function '{spec}'", spec=spec))


def build_keymap(actions):
    """10 packets: 160 x 4 B, entry index = LED matrix index, 'aa 55' at the very end"""
    t = bytearray(640)
    for idx, act in actions.items():
        t[idx * 4: idx * 4 + 4] = act
    t[638:640] = b"\xaa\x55"
    return [bytes(t[i:i + 64]) for i in range(0, 640, 64)]


# ---------------------------------------------------------------- macros
# event = u32 LE: type<<24 | code<<16 | value ; types: 0x30 key, 0x10 mouse, 0x50 delay(ms), |0x80 = press
_SHIFTED = {'!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
            '_': '-', '+': '=', '{': '[', '}': ']', '|': '\\', ':': ';', '"': "'", '~': '`', '<': ',', '>': '.', '?': '/'}


def _ev(kind, code=0, down=False, ms=0):
    if kind == "delay":
        return (0x50 << 24) | min(ms, 0xFFFFFF)
    t = (0x30 if kind == "key" else 0x10) | (0x80 if down else 0)
    return (t << 24) | (code << 16)


def compile_macro(steps, gap=10):
    """steps (strings): 'a' (tap), 'down:a', 'up:a', '50ms' / 'delay:50', 'text:Hello!',
    'combo:ctrl+c', 'mouse:left' (click), 'mdown:left', 'mup:left'"""
    ev = []

    def tap(code, shift=False):
        if shift: ev.extend([_ev("key", 0xE1, True), _ev("delay", ms=gap)])
        ev.extend([_ev("key", code, True), _ev("delay", ms=gap), _ev("key", code, False), _ev("delay", ms=gap)])
        if shift: ev.extend([_ev("key", 0xE1, False), _ev("delay", ms=gap)])

    for st in steps:
        s = st.strip()
        if not s:
            continue
        kind, _, arg = s.partition(":")
        k = kind.lower()
        if s.lower().endswith("ms") and s[:-2].strip().isdigit():
            ev.append(_ev("delay", ms=int(s[:-2])))
        elif k == "delay":
            ev.append(_ev("delay", ms=int(arg)))
        elif k == "text":
            for ch in arg:
                if ch == " ": tap(HID["space"])
                elif ch.isalpha(): tap(hid_code(ch.lower()), ch.isupper())
                elif ch in _SHIFTED: tap(hid_code(_SHIFTED[ch]), True)
                else: tap(hid_code(ch))
        elif k in ("down", "up"):
            ev.extend([_ev("key", hid_code(arg), k == "down"), _ev("delay", ms=gap)])
        elif k == "combo":
            ks = [hid_code(x) for x in arg.split("+")]
            for c in ks: ev.extend([_ev("key", c, True), _ev("delay", ms=gap)])
            for c in reversed(ks): ev.extend([_ev("key", c, False), _ev("delay", ms=gap)])
        elif k in ("mouse", "mdown", "mup"):
            b = MOUSE_BUTTONS[arg.lower()]
            if k in ("mouse", "mdown"): ev.extend([_ev("mouse", b, True), _ev("delay", ms=gap)])
            if k in ("mouse", "mup"): ev.extend([_ev("mouse", b, False), _ev("delay", ms=gap)])
        else:
            tap(hid_code(s))
    return ev


def build_macros(macros):
    """header: 100 slots x u32 LE offset; then per macro: u16 count + 6 B pad + events; aa 55 at the end"""
    if len(macros) > 100:
        raise ValueError(tr("at most 100 macros"))
    data = bytearray(400)
    for i, evs in enumerate(macros):
        data[i * 4: i * 4 + 4] = len(data).to_bytes(4, "little")
        data += len(evs).to_bytes(2, "little") + bytes(6)
        for e in evs:
            data += e.to_bytes(4, "little")
    n = -(-len(data) // 64) + 1
    data += bytes(n * 64 - len(data))
    data[-2:] = b"\xaa\x55"
    return [bytes(data[i:i + 64]) for i in range(0, len(data), 64)]


# ---------------------------------------------------------------- profiles
PROFILE_DIR = CONFIG_DIR / "profiles"

ACTIVE_FILE = CONFIG_DIR / "active"          # name of the profile the current settings came from
CURRENT_FILE = CONFIG_DIR / "current.json"   # the current settings = what is on the keyboard (saved to a profile explicitly)

PROFILE_TEMPLATE = {
    # mode "effect": effect/color/rainbow/brightness/speed/direction ; mode "keys": per-key colors
    "lighting": {"mode": "effect", "effect": "static", "color": "00aaff", "rainbow": False, "brightness": 16,
                 "speed": 10, "direction": "right", "keys": {}, "base": "000000", "key_brightness": 16},
    "remap": {},
    "macros": {},
    "gamemode": {"enabled": False, "alt_tab": False, "alt_f4": False, "win": False},
}


def _template():
    return json.loads(json.dumps(PROFILE_TEMPLATE))


def normalize_profile(prof):
    """fill missing fields, upgrade old flat lighting format"""
    t = _template()
    out = {**t, **prof}
    L = {**t["lighting"], **prof.get("lighting", {})}
    if "mode" not in prof.get("lighting", {}):
        L["mode"] = "keys" if prof.get("lighting", {}).get("keys") and "effect" not in prof["lighting"] else "effect"
    if "brightness" in prof.get("lighting", {}) and L["mode"] == "keys" and "key_brightness" not in prof["lighting"]:
        L["key_brightness"] = prof["lighting"]["brightness"]
    out["lighting"] = L
    out["gamemode"] = {**t["gamemode"], **prof.get("gamemode", {})}
    return out


def list_profiles():
    return sorted(p.stem for p in PROFILE_DIR.glob("*.json")) if PROFILE_DIR.exists() else []


def load_profile(name):
    p = PROFILE_DIR / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(tr("profile '{name}' does not exist ({path})", name=name, path=p))
    return normalize_profile(json.loads(p.read_text(encoding="utf-8")))


def save_profile(name, prof):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    (PROFILE_DIR / f"{name}.json").write_text(json.dumps(prof, indent=2, ensure_ascii=False), encoding="utf-8")


PRESET_DIR = Path(__file__).resolve().with_name("revenant_profiles")


def install_presets(overwrite=False):
    """copy the bundled sample profiles into the profile folder (existing ones are kept); returns the copied names"""
    if not PRESET_DIR.is_dir():
        return []
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in sorted(PRESET_DIR.glob("*.json")):
        dst = PROFILE_DIR / src.name
        if overwrite or not dst.exists():
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            copied.append(src.stem)
    return copied


def get_active():
    """name of the active profile; on first use installs the sample profiles and activates 'default'"""
    if not list_profiles():
        install_presets()
    name = ACTIVE_FILE.read_text(encoding="utf-8").strip() if ACTIVE_FILE.exists() else ""
    if not name or not (PROFILE_DIR / f"{name}.json").exists():
        name = name or "default"
        if not (PROFILE_DIR / f"{name}.json").exists():
            save_profile(name, _template())
        set_active(name)
    return name


def set_active(name):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(name, encoding="utf-8")


# The current settings are edited by the CLI, TUI and web UI and sent to the keyboard right away; profiles are
# named snapshots that change only when saved explicitly (profile save / Save / Save as).

def load_current():
    """the current settings; on first use (or after an upgrade) a copy of the active profile"""
    active = get_active()
    try:
        return normalize_profile(json.loads(CURRENT_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        prof = load_profile(active)
        save_current(prof)
        return prof


def save_current(prof):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_FILE.write_text(json.dumps(prof, indent=2, ensure_ascii=False), encoding="utf-8")


def is_dirty(current=None):
    """do the current settings differ from the saved active profile?"""
    current = load_current() if current is None else current
    try:
        return normalize_profile(current) != load_profile(get_active())
    except FileNotFoundError:
        return True


def use_profile(name):
    """make a profile the current settings (unsaved changes are dropped); returns it – send it to the keyboard"""
    prof = load_profile(name)
    validate_profile(prof)
    set_active(name)
    save_current(prof)
    return prof


def save_current_as(name=None):
    """store the current settings in a profile (default: the active one) and make that profile active"""
    name = _profile_name(name or get_active())
    prof = load_current()
    validate_profile(prof)
    save_profile(name, prof)
    set_active(name)
    return name


def discard_changes():
    """back to the saved active profile; returns it – send it to the keyboard"""
    return use_profile(get_active())


def validate_profile(prof):
    """raise ValueError on any problem; returns (macro_list, keymap_actions)"""
    names = list(prof.get("macros", {}))
    index = {n: i for i, n in enumerate(names)}
    macros = [compile_macro(prof["macros"][n]) for n in names]
    actions = {}
    for key, spec in prof.get("remap", {}).items():
        idx = resolve_keys(key)
        if len(idx) != 1:
            raise ValueError(tr("remap: '{key}' is not a single key", key=key))
        actions[idx[0]] = encode_action(spec, index)
    return macros, actions


def apply_lighting(kb, L):
    L = normalize_profile({"lighting": L})["lighting"]
    if L["mode"] == "keys":
        base = parse_color(L.get("base", "000000"))
        colors = {k: parse_color(v) for k, v in L["keys"].items()}
        return kb.set_keys(colors, base, int(L.get("key_brightness", 16)))
    return kb.set_effect(L["effect"], parse_color(L["color"]), rainbow=1 if L.get("rainbow") else 0,
                         brightness=int(L["brightness"]), speed=int(L["speed"]),
                         direction=parse_direction(str(L["direction"])))


def sync(kb, prof, parts=("lighting", "keys", "gamemode"), log=lambda *_: None):
    """send parts of a profile: 'lighting', 'keys' (macros + key functions), 'gamemode'"""
    ok = True
    if "keys" in parts:
        macros, actions = validate_profile(prof)        # validate before touching the keyboard
    if "lighting" in parts:
        ok &= apply_lighting(kb, prof["lighting"]); log("  " + tr("lighting"))
    if "keys" in parts:
        ok &= kb.write_macros(macros); log("  " + tr("macros: {value}", value=len(macros)))
        ok &= kb.write_keymap(actions); log("  " + tr("key functions: {value}", value=len(actions)))
    if "gamemode" in parts:
        g = prof["gamemode"]
        ok &= kb.set_gamemode(g["enabled"], g["alt_tab"], g["alt_f4"], g["win"])
        log("  " + tr("game mode: {state}", state=tr("on") if g["enabled"] else tr("off")))
    return ok


def apply_profile(kb, prof, log=print):
    return sync(kb, normalize_profile(prof), log=log)


def describe_profile(prof):
    L, g = prof["lighting"], prof["gamemode"]
    if L["mode"] == "keys":
        light = tr("custom key colours ({n} keys, base #{base}, brightness {b})",
                   n=len(L["keys"]), base=L["base"], b=L["key_brightness"])
    else:
        col = tr("rainbow") if L["rainbow"] else "#" + L["color"]
        light = tr("{effect} {color}, brightness {b}, speed {s}, direction {d}", effect=effect_label(L["effect"]),
                   color=col, b=L["brightness"], s=L["speed"], d=direction_label(str(L["direction"])))
    lines = [tr("lighting: {value}", value=light)]
    lines.append(tr("key functions: {value}",
                    value=", ".join(f"{k}={v}" for k, v in prof["remap"].items()) or tr("default")))
    lines.append(tr("macros: {value}", value=", ".join(prof["macros"]) or tr("none")))
    gm = [n for n, k in (("Alt+Tab", "alt_tab"), ("Alt+F4", "alt_f4"), ("Win", "win")) if g[k]]
    if g["enabled"] and gm:
        state = tr("on, blocks {keys}", keys=", ".join(gm))
    else:
        state = tr("on") if g["enabled"] else tr("off")
    lines.append(tr("game mode: {state}", state=state))
    return "\n".join(lines)


class Revenant:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.dev = self._open()

    def _open(self):
        if hid is None:
            raise RevenantError(tr("The hidapi library is missing:  pip install hidapi"))
        cands = hid.enumerate(VID, PID)
        if not cands:
            raise RevenantNotFound(tr("CZC.Gaming Revenant keyboard not found (it must be connected with the USB cable, "
                                     "switch on the bottom = Off)."))
        # feature reports live on interface 0 (the keyboard interface)
        cands.sort(key=lambda d: (d.get("interface_number", 0) != 0, d.get("usage", 0) != 6))
        last = None
        for d in cands:
            try:
                dev = hid.device()
                dev.open_path(d["path"])
                if dev.send_feature_report(self._cmd(0x02)) < 0:
                    raise IOError(dev.error())
                time.sleep(0.01)
                dev.get_feature_report(0, 65)
                if self.verbose:
                    print("open", d["path"], hex(d.get("usage_page", 0)))
                return dev
            except (OSError, IOError) as e:
                last = e
                try: dev.close()
                except Exception: pass
        if sys.platform.startswith("linux"):
            hint = tr("Missing permissions – run once:  revenant setup")
        elif sys.platform == "darwin":
            hint = tr("Allow 'Input Monitoring' for your terminal (revenant setup shows where).")
        else:
            hint = tr("Close the original CZC program and try again.")
        raise RevenantAccessError(tr("Could not open the keyboard's control interface: {error}", error=last) + "\n" + hint)

    @staticmethod
    def _cmd(op, n=0):
        p = bytearray(65)
        p[1], p[2] = 0x04, op
        p[9] = n
        return bytes(p)

    def _send(self, payload64):
        assert len(payload64) == 64
        self.dev.send_feature_report(b"\x00" + payload64)
        time.sleep(0.005)

    def _cmd_ack(self, op, n=0):
        """send command, poll until the keyboard reports it done (byte 4 == 1)"""
        self.dev.send_feature_report(self._cmd(op, n))
        for _ in range(50):
            time.sleep(0.01)
            g = bytes(self.dev.get_feature_report(0, 65))
            if len(g) > 4 and g[4] == 1:
                return g
        raise IOError(tr("the keyboard did not acknowledge command {op}", op=f"{op:#04x}"))

    def _write(self, op, pkts, commit=False):
        """generic block write: handshake, 04 <op> n, n x 64 B, checksum query [, 04 f0]"""
        self._cmd_ack(0xAB)
        self._send(os.urandom(64))
        self._cmd_ack(0x02)
        self._cmd_ack(op, len(pkts))
        for p in pkts:
            self._send(p)
        ack = self._cmd_ack(0x02)
        expected = sum(sum(p) for p in pkts) & 0xFFFF
        # reply: [rid] 04 02 00 01 [sum lo] [sum hi]
        got = ack[5] | (ack[6] << 8) if len(ack) > 6 else None
        if self.verbose:
            print(f"op {op:#04x}: checksum keyboard={got:#06x} expected={expected:#06x}")
        if commit:
            self.dev.send_feature_report(self._cmd(0xF0))
        return got == expected

    def write_table(self, pkts):
        """lighting table (op 0x13, 18 packets, committed with 04 f0)"""
        return self._write(0x13, pkts, commit=True)

    def write_keymap(self, actions):
        """actions: {matrix index: 4-byte action}; every other key gets its default function"""
        return self._write(0x11, build_keymap(actions))

    def write_macros(self, macros):
        """macros: list of event lists (index = macro number used by 'macro:' actions)"""
        return self._write(0x15, build_macros(macros))

    def set_gamemode(self, enabled, alt_tab=False, alt_f4=False, win=False):
        p = bytearray(64)
        p[0:5] = bytes([0x0A, int(enabled), int(alt_tab), int(alt_f4), int(win)])
        p[62:64] = b"\xaa\x55"
        return self._write(0x17, [bytes(p)])

    def set_keys(self, colors, base=(0, 0, 0), brightness=16):
        """colors: {key name or group: (r,g,b)}; later entries override earlier ones."""
        keymap = {i: base for i in KEYS.values()} if base != (0, 0, 0) else {}
        for name, rgb in colors.items():
            for i in resolve_keys(name):
                keymap[i] = rgb
        act = record(EFFECTS["custom"], brightness=brightness)
        return self.write_table(build_table(act, keymap))

    def set_effect(self, name, color=DEFAULT_COLOR, rainbow=None, brightness=16, speed=12, direction=0, keymap=None):
        eid = EFFECTS[name]
        act = record(eid, color, rainbow, brightness, speed, direction)
        return self.write_table(build_table(act, keymap))


def parse_color(s):
    s = s.lstrip("#")
    names = {"red": "ff0000", "green": "00ff00", "blue": "0000ff", "white": "ffffff",
             "yellow": "ffff00", "cyan": "00ffff", "magenta": "ff00ff", "orange": "ff6000",
             "purple": "a000ff", "pink": "ff3080", "off": "000000",
             "cervena": "ff0000", "zelena": "00ff00", "modra": "0000ff", "bila": "ffffff",
             "zluta": "ffff00", "fialova": "a000ff", "oranzova": "ff6000", "ruzova": "ff3080"}
    s = names.get(s.lower(), s)
    if len(s) != 6:
        raise argparse.ArgumentTypeError(tr("colour as RRGGBB or a name (red, blue, ...)"))
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


DIRECTIONS = {"right": 0, "left": 1, "up": 2, "down": 3,
              "doprava": 0, "doleva": 1, "nahoru": 2, "dolu": 3}


def parse_direction(s):
    if s.isdigit() and 0 <= int(s) <= 3:
        return int(s)
    if s.lower() in DIRECTIONS:
        return DIRECTIONS[s.lower()]
    raise argparse.ArgumentTypeError(tr("direction: right, left, up, down or 0-3"))



def hexcol(rgb):
    return "%02x%02x%02x" % rgb


UDEV_RULE_PATH = "/etc/udev/rules.d/70-czc-revenant.rules"
UDEV_RULE = ('# CZC.Gaming Revenant (revenant-rgb): access for the logged-in user\n'
             'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0c45", ATTRS{idProduct}=="8006", MODE="0660", TAG+="uaccess"\n')


def keyboard_present():
    """is the keyboard plugged in (no I/O to the device)"""
    return bool(hid and hid.enumerate(VID, PID))


def setup_kind():
    """which one-time setup can fix an access error here: 'udev' (Linux), 'macos' or None (Windows)"""
    if sys.platform.startswith("linux"):
        return "udev"
    return "macos" if sys.platform == "darwin" else None


def udev_rule_installed():
    p = Path(UDEV_RULE_PATH)
    return p.exists() and p.read_text() == UDEV_RULE


def install_udev_rule(method=None):
    """install the udev rule with admin rights. method: 'sudo' (asks in this terminal), 'pkexec' (GUI dialog)
    or None = sudo when there is a terminal, else pkexec. Raises RevenantError."""
    import shutil
    script = (f"cat > {UDEV_RULE_PATH} && udevadm control --reload-rules"
              " && udevadm trigger --subsystem-match=hidraw --action=change")
    if os.geteuid() == 0:
        elevate = []
    else:
        method = method or ("sudo" if sys.stdin.isatty() and shutil.which("sudo") else "pkexec")
        if not shutil.which(method):
            raise RevenantError(tr("{tool} is not available – run in a terminal:  revenant setup", tool=method))
        elevate = [method]
    r = subprocess.run(elevate + ["sh", "-c", script], input=UDEV_RULE, text=True)
    if r.returncode:
        raise RevenantError(tr("Installing the udev rule failed or was cancelled."))
    time.sleep(1.0)                               # let udev re-apply permissions


def open_macos_privacy():
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"])


def probe():
    """try to open the keyboard (sends only a status query, writes nothing); returns None or the exception"""
    try:
        Revenant().dev.close()
        return None
    except RevenantError as ex:
        return ex


def cmd_setup(a):
    """one-time OS setup so the keyboard can be used without admin rights"""
    if sys.platform.startswith("linux"):
        if udev_rule_installed() and not a.force:
            print(tr("udev rule is already installed ({path})", path=UDEV_RULE_PATH))
        else:
            print(tr("Installing the udev rule {path} (asks for the administrator password) ...", path=UDEV_RULE_PATH))
            install_udev_rule()
    elif sys.platform == "darwin":
        print(tr("macOS needs no installation. On first use the system may ask you to allow\n"
                 "'Input Monitoring' for Terminal / the app you run revenant from:\n"
                 "  System Settings -> Privacy & Security -> Input Monitoring"))
        if a.open:
            open_macos_privacy()
    else:
        print(tr("Windows needs no installation (only the original CZC program must not be running)."))

    err = probe()
    if err is None:
        print(tr("ok – the keyboard is connected and accessible"))
    else:
        print(err)
        if sys.platform.startswith("linux") and isinstance(err, RevenantAccessError):
            print(tr("If the rule is installed, unplug and re-plug the keyboard cable."))
        sys.exit(1)


def running_processes():
    try:
        import psutil
        return {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])}
    except ImportError:
        sys.exit(tr("auto needs psutil:  pip install psutil"))


def cmd_auto(a):
    """auto.json: {"default": "desk", "rules": [{"process": "cs2.exe", "profile": "fps"}, ...]}"""
    cfg_path = CONFIG_DIR / "auto.json"
    if not cfg_path.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps({"default": "", "rules": [{"process": "cs2.exe", "profile": "fps"}]},
                                       indent=2), encoding="utf-8")
        print(tr("created a sample {path} – edit it and run again", path=cfg_path)); return
    kb, current = None, None
    print(tr("auto: watching programs (Ctrl+C to stop)"))
    while True:
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            procs = running_processes()
            want = next((r["profile"] for r in cfg.get("rules", []) if r["process"].lower() in procs),
                        cfg.get("default") or None)
            if want and want != current:
                print(time.strftime("%H:%M:%S"), "->", want)
                kb = kb or Revenant(a.verbose)
                apply_profile(kb, use_profile(want), log=lambda *_: None)
                current = want
        except KeyboardInterrupt:
            return
        except (Exception, SystemExit) as ex:   # keyboard unplugged, bad profile, ... keep running
            print(tr("error: {error}", error=ex)); kb = None; current = None
        try:
            time.sleep(a.interval)
        except KeyboardInterrupt:
            return


def func_help():
    return tr("""Key functions (remap KEY=FUNCTION):
  default                 default function
  disable                 disable the key
  key:X                   another key (key:esc, key:f13 ... or just X)
  combo:ctrl+shift+esc    combination of up to 3 keys
  media:NAME              {media}
  mouse:NAME              left, right, middle, back, forward, wheelup, wheeldown
  macro:NAME              macro (once); macro:NAME:repeat:5 ; macro:NAME:toggle

Macro steps (macro set NAME STEP STEP ...):
  a, enter, f5 ...        press and release a key
  text:Hello world!       type text (capitals and !?@ via Shift)
  combo:ctrl+c            combination
  down:a / up:a           press only / release only
  50ms                    pause
  mouse:left              mouse click; mdown:left / mup:left""", media=", ".join(MEDIA))


# argparse's own texts go through its module-level gettext function, which we point at tr()
ARGPARSE_STRINGS = [N_("usage: "), N_("options"), N_("positional arguments"), N_("show this help message and exit"),
                    N_("show program's version number and exit")]


def build_parser():
    argparse._ = tr
    ap = argparse.ArgumentParser(
        prog="revenant", formatter_class=argparse.RawDescriptionHelpFormatter,
        description=tr("CZC.Gaming Revenant driver. Changes go to the keyboard right away; "
                       "save them to a profile with: revenant profile save"),
        epilog=tr("examples:") + "\n"
               "  revenant static red\n  revenant effect breathing -c blue -s 6\n"
               "  revenant keys wasd=red arrows=green --base 101010\n"
               "  revenant remap caps=disable f12=media:volup\n"
               "  revenant macro set hello text:Hello! enter\n  revenant remap f1=macro:hello\n"
               "  revenant gamemode on --win\n  revenant profile use games\n  revenant status\n"
               "  revenant web\n"
               "  revenant            " + tr("(no command) text user interface"))
    ap.add_argument("-v", "--verbose", action="store_true", help=tr("verbose output"))
    ap.add_argument("-V", "--version", action="version", version=f"revenant {__version__}")
    ap.add_argument("-p", "--profile", help=tr("edit a saved profile file instead of the current settings (keyboard unchanged)"))
    ap.add_argument("--lang", choices=["auto", *LANGUAGES], help=tr("language for this run (default: settings / system)"))
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("tui", help=tr("text user interface (same as running without a command)"))

    s = sub.add_parser("static", help=tr("one colour"))
    s.add_argument("color", type=parse_color)
    s.add_argument("-b", "--brightness", type=int, default=16, help="0-16")

    e = sub.add_parser("effect", help=tr("effect (revenant list = list)"))
    e.add_argument("name", choices=[k for k in EFFECTS if k != "custom"])
    e.add_argument("-c", "--color", type=parse_color, default=None, help=tr("colour (otherwise rainbow)"))
    e.add_argument("-b", "--brightness", type=int, default=16, help="0-16")
    e.add_argument("-s", "--speed", type=int, default=12, help="0-16")
    e.add_argument("-d", "--direction", type=parse_direction, default=0, help="right, left, up, down")

    k = sub.add_parser("keys", help=tr("key colours: keys wasd=red esc=00ff00 (adds to the current ones)"))
    k.add_argument("assign", nargs="*", help=tr("KEY=COLOR or GROUP=COLOR (groups: {groups})", groups=", ".join(KEY_GROUPS)))
    k.add_argument("--base", type=parse_color, default=None, help=tr("colour of the other keys"))
    k.add_argument("-b", "--brightness", type=int, default=None, help="0-16")
    k.add_argument("--clear", action="store_true", help=tr("turn all keys off first"))

    sub.add_parser("off", help=tr("turn the lighting off"))

    r = sub.add_parser("remap", help=tr("key functions: remap caps=disable (lists them without arguments)"))
    r.add_argument("assign", nargs="*", help=tr("KEY=FUNCTION (see: revenant funcs)"))
    r.add_argument("--clear", action="store_true", help=tr("reset all keys to default"))

    m = sub.add_parser("macro", help=tr("macros: list | show NAME | set NAME STEPS... | delete NAME"))
    m.add_argument("action", choices=["list", "show", "set", "delete"])
    m.add_argument("name", nargs="?")
    m.add_argument("steps", nargs="*", help=tr("macro steps (see: revenant funcs)"))

    g = sub.add_parser("gamemode", help=tr("game mode: gamemode on --win --alt-tab --alt-f4 | gamemode off"))
    g.add_argument("state", choices=["on", "off"])
    g.add_argument("--alt-tab", action="store_true", help=tr("block Alt+Tab"))
    g.add_argument("--alt-f4", action="store_true", help=tr("block Alt+F4"))
    g.add_argument("--win", action="store_true", help=tr("block the Windows key"))

    p = sub.add_parser("profile", help=tr("profiles: list | show | use | save | discard | new | copy | delete | path | presets"))
    p.add_argument("action", choices=["list", "show", "use", "save", "discard", "new", "copy", "delete", "path", "presets"])
    p.add_argument("name", nargs="?")
    p.add_argument("target", nargs="?", help=tr("for 'copy': name of the copy"))

    sub.add_parser("apply", help=tr("send the whole active profile to the keyboard again"))
    sub.add_parser("status", help=tr("show the active profile"))
    au = sub.add_parser("auto", help=tr("switch profiles by running programs (auto.json)"))
    au.add_argument("--interval", type=float, default=2.0)
    st = sub.add_parser("setup", help=tr("one-time system setup (Linux: udev rule) and keyboard check"))
    st.add_argument("--force", action="store_true", help=tr("Linux: reinstall the rule even if it exists"))
    st.add_argument("--open", action="store_true", help=tr("macOS: open the Input Monitoring settings"))
    w = sub.add_parser("web", help=tr("web user interface in the browser (this computer only)"))
    w.add_argument("--port", type=int, default=None, help=tr("port (default {port}, a free one if taken)", port=WEB_PORT))
    w.add_argument("--no-browser", action="store_true", help=tr("don't open the browser"))
    lg = sub.add_parser("lang", help=tr("show or set the language: lang [auto|{langs}]", langs="|".join(LANGUAGES)))
    lg.add_argument("value", nargs="?", choices=["auto", *LANGUAGES])
    sub.add_parser("list", help=tr("list of effects"))
    sub.add_parser("keylist", help=tr("key and group names"))
    sub.add_parser("funcs", help=tr("help for key functions and macro steps"))
    return ap


def cmd_lang(a):
    if a.value:
        save_settings(lang=a.value)
        set_language(resolve_language(a.value))
    current = load_settings().get("lang", "auto")
    print(tr("language: {lang} (setting: {setting})", lang=LANGUAGES[LANG], setting=current))


def main():
    a = build_parser().parse_args()

    # ---- commands without profile/keyboard
    if a.cmd in (None, "tui"):
        return run_tui()
    if a.cmd == "lang":
        return cmd_lang(a)
    if a.cmd == "list":
        print("\n".join(f"{k:16} {effect_label(k)}" for k in EFFECTS if k != "custom")); return
    if a.cmd == "keylist":
        for row in range(7):
            print("  ".join(n for n, i in KEYS.items() if i // 18 == row))
        print("\n" + tr("groups: {groups}", groups=", ".join(KEY_GROUPS))); return
    if a.cmd == "funcs":
        print(func_help()); return
    if a.cmd == "auto":
        return cmd_auto(a)
    if a.cmd == "setup":
        return cmd_setup(a)
    if a.cmd == "web":
        return run_web(a.port, not a.no_browser, a.verbose)

    active = get_active()
    if a.cmd == "profile":
        return cmd_profile(a, active)
    target = a.profile                 # -p NAME: edit that profile file directly, the keyboard is not touched
    try:
        prof = load_profile(target) if target else load_current()
    except FileNotFoundError as ex:
        sys.exit(str(ex))

    def finish(parts, changed=True):
        if changed:
            try:
                validate_profile(prof)
            except (ValueError, KeyError) as ex:
                sys.exit(tr("error: {error}", error=ex))
            save_profile(target, prof) if target else save_current(prof)
        if target:
            print(tr("saved to profile '{name}' (keyboard unchanged)", name=target)); return
        ok = sync(Revenant(a.verbose), prof, parts)
        print("ok" if ok else tr("sent (checksum mismatch)"))
        if is_dirty(prof):
            print(tr("unsaved changes to profile '{name}' – keep them: revenant profile save", name=active))

    L = prof["lighting"]
    for v in ("brightness", "speed"):
        if getattr(a, v, None) is not None and not 0 <= getattr(a, v) <= 16:
            sys.exit(tr("{name} must be 0-16", name=v))

    if a.cmd == "status":
        if target:
            print(tr("profile '{name}'", name=target))
        else:
            print(tr("active profile: {name}", name=active) + (" " + tr("(unsaved changes)") if is_dirty(prof) else ""))
        print(describe_profile(prof)); return
    if a.cmd == "apply":
        print(tr("sending profile '{name}':", name=target or active))
        ok = sync(Revenant(a.verbose), prof, log=print)
        print("ok" if ok else tr("sent (some checksum did not match)")); return

    if a.cmd == "static":
        L.update(mode="effect", effect="static", color=hexcol(a.color), rainbow=False, brightness=a.brightness)
        return finish(["lighting"])
    if a.cmd == "off":
        L.update(mode="effect", effect="static", color="000000", rainbow=False, brightness=0)
        return finish(["lighting"])
    if a.cmd == "effect":
        L.update(mode="effect", effect=a.name, rainbow=a.color is None, brightness=a.brightness, speed=a.speed,
                 direction=[k for k, v in DIRECTIONS.items() if v == a.direction][0])
        if a.color is not None:
            L["color"] = hexcol(a.color)
        return finish(["lighting"])
    if a.cmd == "keys":
        if a.clear:
            L["keys"] = {}
        for item in a.assign:
            key, sep, col = item.rpartition("=")
            if not sep or not key:
                sys.exit(tr("'{item}': use KEY=COLOR", item=item))
            try:
                names = [n for n, i in KEYS.items() if i in resolve_keys(key)]
                c = hexcol(parse_color(col))
            except (KeyError, ValueError, argparse.ArgumentTypeError):
                sys.exit(tr("'{item}': unknown key or colour (see: revenant keylist)", item=item))
            for n in names:
                L["keys"][n] = c
        if a.base is not None:
            L["base"] = hexcol(a.base)
        if a.brightness is not None:
            L["key_brightness"] = a.brightness
        L["keys"] = {k: v for k, v in L["keys"].items() if v != L["base"]}
        L["mode"] = "keys"
        return finish(["lighting"])
    if a.cmd == "remap":
        if not a.assign and not a.clear:
            print("\n".join(f"{k} = {v}" for k, v in prof["remap"].items()) or tr("all keys have their default function"))
            return
        if a.clear:
            prof["remap"] = {}
        for item in a.assign:
            key, sep, spec = item.partition("=")
            try:
                idx = resolve_keys(key)
            except KeyError:
                sys.exit(tr("error: {error}", error=tr("unknown key '{name}'", name=key)))
            if not sep or len(idx) != 1:
                sys.exit(tr("error: {error}", error=tr("'{item}': use KEY=FUNCTION", item=item)))
            canon = next(n for n, i in KEYS.items() if i == idx[0])
            if spec.strip().lower() == "default":
                prof["remap"].pop(canon, None)
            else:
                prof["remap"][canon] = spec.strip()
        return finish(["keys"])
    if a.cmd == "macro":
        if a.action == "list":
            print("\n".join(f"{n}: {' | '.join(s)}" for n, s in prof["macros"].items()) or tr("no macros")); return
        if not a.name:
            sys.exit(tr("enter a macro name"))
        if a.action == "show":
            if a.name not in prof["macros"]:
                sys.exit(tr("macro '{name}' does not exist", name=a.name))
            print("\n".join(prof["macros"][a.name])); return
        if a.action == "delete":
            if a.name not in prof["macros"]:
                sys.exit(tr("macro '{name}' does not exist", name=a.name))
            used = [k for k, v in prof["remap"].items() if v.split(":")[:2] == ["macro", a.name]]
            if used:
                sys.exit(tr("the macro is assigned to keys {keys} – change them first (remap KEY=default)",
                            keys=", ".join(used)))
            del prof["macros"][a.name]
            return finish(["keys"])
        if not a.steps:
            sys.exit(tr("enter the macro steps, e.g.: macro set hello text:Hello! enter"))
        try:
            compile_macro(a.steps)
        except (ValueError, KeyError) as ex:
            sys.exit(tr("error in macro: {error}", error=ex))
        prof["macros"][a.name] = a.steps
        return finish(["keys"])
    if a.cmd == "gamemode":
        prof["gamemode"] = {"enabled": a.state == "on", "alt_tab": a.alt_tab, "alt_f4": a.alt_f4, "win": a.win}
        return finish(["gamemode"])


def cmd_profile(a, active):
    if a.action == "list":
        dirty = is_dirty()
        for n in list_profiles():
            print(("* " if n == active else "  ") + n + (" " + tr("(unsaved changes)") if n == active and dirty else ""))
        return
    if a.action == "save":
        try:
            name = save_current_as(a.name)
        except ValueError as ex:
            sys.exit(tr("error: {error}", error=ex))
        print(tr("current settings saved to profile '{name}'", name=name)); return
    if a.action == "discard":
        print(tr("discarding changes, back to profile '{name}':", name=active))
        ok = apply_profile(Revenant(a.verbose), discard_changes())
        print("ok" if ok else tr("sent (some checksum did not match)")); return
    if a.action == "path":
        print(PROFILE_DIR); return
    if a.action == "presets":
        copied = install_presets()
        print(tr("sample profiles added: {names}", names=", ".join(copied)) if copied
              else tr("all sample profiles are already there ({path})", path=PROFILE_DIR))
        return
    name = a.name or (active if a.action == "show" else None)
    if not name:
        sys.exit(tr("enter a profile name"))
    path = PROFILE_DIR / f"{name}.json"
    if a.action == "new":
        if path.exists():
            sys.exit(tr("the profile already exists: {path}", path=path))
        save_profile(name, _template()); print(tr("created profile '{name}' ({path})", name=name, path=path)); return
    if a.action == "delete":
        if name == active:
            sys.exit(tr("the active profile can't be deleted – switch to another one first (profile use NAME)"))
        path.unlink(missing_ok=True); print(tr("deleted")); return
    try:
        prof = load_profile(name)
        validate_profile(prof)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as ex:
        sys.exit(tr("error in profile: {error}", error=ex))
    if a.action == "show":
        print(tr("profile '{name}'", name=name) + (" " + tr("(active)") if name == active else ""))
        print(describe_profile(prof)); print(tr("file: {path}", path=path)); return
    if a.action == "copy":
        if not a.target:
            sys.exit(tr("profile copy SOURCE NEW"))
        save_profile(a.target, prof); print(tr("copied to '{name}'", name=a.target)); return
    if a.action == "use":
        print(tr("activating profile '{name}':", name=name))
        ok = apply_profile(Revenant(a.verbose), use_profile(name))
        print("ok" if ok else tr("sent (some checksum did not match)"))


# ================================================================ TUI (Textual)
# physical layout: (key, width in units); None = gap
U = 5
ROWS = [
    [("esc", 1), (None, 1), ("f1", 1), ("f2", 1), ("f3", 1), ("f4", 1), (None, .5), ("f5", 1), ("f6", 1), ("f7", 1),
     ("f8", 1), (None, .5), ("f9", 1), ("f10", 1), ("f11", 1), ("f12", 1), (None, .5), ("prtsc", 1), ("scrolllock", 1), ("pause", 1)],
    [("`", 1), ("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 1), ("6", 1), ("7", 1), ("8", 1), ("9", 1), ("0", 1), ("-", 1), ("=", 1),
     ("backspace", 2), (None, .5), ("insert", 1), ("home", 1), ("pgup", 1), (None, .5), ("numlock", 1), ("num/", 1), ("num*", 1), ("num-", 1)],
    [("tab", 1.5), ("q", 1), ("w", 1), ("e", 1), ("r", 1), ("t", 1), ("y", 1), ("u", 1), ("i", 1), ("o", 1), ("p", 1), ("[", 1), ("]", 1),
     ("\\", 1.5), (None, .5), ("delete", 1), ("end", 1), ("pgdn", 1), (None, .5), ("num7", 1), ("num8", 1), ("num9", 1), ("num+", 1)],
    [("caps", 1.75), ("a", 1), ("s", 1), ("d", 1), ("f", 1), ("g", 1), ("h", 1), ("j", 1), ("k", 1), ("l", 1), (";", 1), ("'", 1),
     ("enter", 2.25), (None, 3.5), (None, .5), ("num4", 1), ("num5", 1), ("num6", 1)],
    [("lshift", 2.25), ("z", 1), ("x", 1), ("c", 1), ("v", 1), ("b", 1), ("n", 1), ("m", 1), (",", 1), (".", 1), ("/", 1),
     ("rshift", 2.75), (None, 1.5), ("up", 1), (None, 1), (None, .5), ("num1", 1), ("num2", 1), ("num3", 1), ("numenter", 1)],
    [("lctrl", 1.25), ("win", 1.25), ("lalt", 1.25), ("space", 6.25), ("ralt", 1.25), ("fn", 1.25), ("menu", 1.25), ("rctrl", 1.25),
     (None, .5), ("left", 1), ("down", 1), ("right", 1), (None, .5), ("num0", 2), ("num.", 1)],
]
LABELS = {"esc": "Esc", "prtsc": "PrS", "scrolllock": "ScL", "pause": "Pau", "backspace": "Bksp", "insert": "Ins",
          "home": "Hom", "pgup": "PgU", "numlock": "Num", "num/": "/", "num*": "*", "num-": "-", "tab": "Tab",
          "delete": "Del", "end": "End", "pgdn": "PgD", "num7": "7", "num8": "8", "num9": "9", "num+": "+",
          "caps": "Caps", "enter": "Enter", "num4": "4", "num5": "5", "num6": "6", "lshift": "Shift",
          "rshift": "Shift", "up": "↑", "num1": "1", "num2": "2", "num3": "3", "numenter": "Ent", "lctrl": "Ctrl",
          "win": "Win", "lalt": "Alt", "space": "", "ralt": "Alt", "fn": "Fn", "menu": "Menu", "rctrl": "Ctrl",
          "left": "←", "down": "↓", "right": "→", "num0": "0", "num.": "."}

PALETTE = ["ff0000", "ff6000", "ffcc00", "80ff00", "00ff00", "00ffaa", "00ffff", "0080ff",
           "0000ff", "8000ff", "ff00ff", "ff3080", "ffffff", "808080", "000000"]

EFFECT_LABELS = {
    "static": N_("Static"), "press-on": N_("Light up on press"), "press-off": N_("Go dark on press"),
    "sparkle": N_("Sparkle"), "rain": N_("Rain"), "colors": N_("Colours"), "breathing": N_("Breathing"),
    "spectrum": N_("Spectrum"), "center-wave": N_("Centre wave"), "vertical-wave": N_("Vertical wave"),
    "horizontal-wave": N_("Horizontal wave"), "rotating": N_("Rotating"), "explosion": N_("Explosion"),
    "start": N_("Start"), "ripple": N_("Ripple"), "snake": N_("Snake"), "pulse": N_("Pulse"),
    "disco": N_("Disco"), "lines": N_("Lines"),
}
DIRS = ["right", "left", "up", "down"]
DIRECTION_LABELS = {"right": N_("right"), "left": N_("left"), "up": N_("up"), "down": N_("down")}
FUNC_TYPE_LABELS = [("default", N_("Default")), ("disable", N_("Disabled")), ("key", N_("Other key")),
                    ("combo", N_("Combination")), ("media", N_("Media")), ("mouse", N_("Mouse")), ("macro", N_("Macro"))]


def effect_label(name):
    return tr(EFFECT_LABELS.get(name, name))


def direction_label(name):
    return tr(DIRECTION_LABELS.get(name, name))


def effect_choices():
    return [(effect_label(k), k) for k in EFFECT_LABELS]


def func_types():
    return [(tr(label), value) for value, label in FUNC_TYPE_LABELS]


def func_hints():
    return {"default": "", "disable": "", "key": tr("e.g. esc, f13, a"), "combo": tr("e.g. ctrl+shift+esc"),
            "media": ", ".join(MEDIA), "mouse": "left, right, middle, back, forward, wheelup, wheeldown",
            "macro": tr("macro name")}


def macro_modes():
    return [(tr("Play once"), "once"), (tr("Repeat N times"), "repeat"), (tr("Toggle on/off by pressing"), "toggle")]


def macro_help():
    return tr("""[b]Macro steps[/b] – one per line:
  [cyan]a[/] / [cyan]enter[/] / [cyan]f5[/]     press and release a key
  [cyan]text:Hello![/]         type text
  [cyan]combo:ctrl+c[/]        key combination
  [cyan]down:shift[/] / [cyan]up:shift[/]  press only / release only
  [cyan]100ms[/]               pause
  [cyan]mouse:left[/]          mouse click""")


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def contrast(h):
    r, g, b = hex2rgb(h)
    return "black" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "white"


def run_tui():
    # This is an RGB tool - colors are the point: ignore NO_COLOR and ask for 24-bit color.
    os.environ.pop("NO_COLOR", None)
    os.environ["COLORTERM"] = "truecolor"
    try:
        from textual import events, on, work
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.color import Color
        from textual.containers import Horizontal, HorizontalScroll, Vertical, VerticalScroll
        from textual.widgets import (Button, Checkbox, DataTable, Footer, Header, Input, Label, OptionList,
                                     RadioButton, RadioSet, Select, Static, Switch, TabbedContent, TabPane,
                                     TextArea)
        from textual.screen import ModalScreen
    except ImportError:
        sys.exit(tr("The TUI needs the textual library:  pip install textual"))

    def keyboard_rows(cls):
        for row in ROWS:
            with Horizontal(classes="krow"):
                for key, w in row:
                    if key is None:
                        g = Static(classes="gap"); g.styles.width = round(w * U); yield g
                    else:
                        yield cls(key, w)

    class KeyCap(Static):
        def __init__(self, key, width):
            super().__init__(LABELS.get(key, key.upper()), classes="key")
            self.key = key
            self.styles.width = max(3, round(width * U))

        def paint(self, hexcol, selected):
            self.styles.background = Color.parse("#" + hexcol)
            self.styles.color = contrast(hexcol)
            self.set_class(selected, "selected")

        def on_click(self, event: events.Click) -> None:
            self.app.toggle_key(self.key)

    class RemapCap(KeyCap):
        """a key on the Key functions keyboard: click = edit that key's function"""
        def paint_remap(self, mapped, selected):
            self.styles.background = Color.parse("#3a4255" if mapped else "#232733")
            self.styles.color = "#22d3ee" if mapped else "#9aa4b2"
            self.update(LABELS.get(self.key, self.key.upper()) + ("•" if mapped else ""))
            self.set_class(selected, "selected")

        def on_click(self, event: events.Click) -> None:
            self.app.pick_remap_key(self.key)


    class Swatch(Static):
        def __init__(self, hexcol):
            super().__init__("", classes="swatch")
            self.hexcol = hexcol
            self.styles.background = Color.parse("#" + hexcol)
            self.tooltip = "#" + hexcol

        def on_click(self) -> None:
            self.app.set_current_color(self.hexcol)

    class CustomSwatch(Static):
        """the last colour outside the palette (picked from a key, typed as #RRGGBB or taken with the eyedropper)"""
        def __init__(self):
            super().__init__(tr("Custom"), id="custom")
            self.hexcol = None

        def show(self, hexcol):
            self.hexcol = hexcol
            self.styles.background = Color.parse("#" + hexcol)
            self.styles.color = contrast(hexcol)
            self.tooltip = "#" + hexcol

        def on_click(self) -> None:
            if self.hexcol:
                self.app.set_current_color(self.hexcol)


    class Stepper(Horizontal):
        """value 0-16 with  - [bar] +"""
        def __init__(self, label, value, id):
            super().__init__(id=id, classes="stepper")
            self.label, self.value = label, value

        def compose(self) -> ComposeResult:
            yield Label(self.label, classes="steplabel")
            yield Button("−", classes="step dec", name="dec")
            yield Static(self._bar(), classes="bar")
            yield Button("+", classes="step inc", name="inc")

        def _bar(self):
            return "█" * self.value + "░" * (16 - self.value) + f" {self.value:2d}"

        def set(self, v):
            self.value = max(0, min(16, int(v)))
            if self.is_mounted:
                self.query_one(".bar", Static).update(self._bar())

        @on(Button.Pressed, ".step")
        def _step(self, ev: Button.Pressed) -> None:
            self.set(self.value + (1 if ev.button.name == "inc" else -1))


    class SetupScreen(ModalScreen):
        """offer the one-time OS setup when the keyboard is connected but not accessible"""
        DEFAULT_CSS = """
        SetupScreen { align: center middle; background: #00000080; }
        #setup_box { width: 76; height: auto; padding: 1 2; border: round #fbbf24; background: #151a25; }
        #setup_box .t { text-style: bold; color: #fbbf24; }
        #setup_box Static { margin: 1 0 0 0; }
        #setup_box Horizontal { height: auto; margin: 1 0 0 0; }
        #setup_box Button { margin: 0 2 0 0; }
        """
        BINDINGS = [("escape", "later", tr("Later"))]

        def __init__(self, error, kind):
            super().__init__()
            self.error, self.kind = error, kind

        def compose(self) -> ComposeResult:
            if self.kind == "udev":
                hint = tr("On Linux a udev rule has to be installed once. The TUI hides for a moment "
                          "and sudo asks for the administrator password in the terminal.")
                label = tr("Set up access")
            else:
                hint = tr("macOS requires the Input Monitoring permission for the app you run revenant from. "
                          "Restart it after allowing.")
                label = tr("Open settings")
            with Vertical(id="setup_box"):
                yield Label(tr("The keyboard is connected, but the program has no access to it"), classes="t")
                yield Static(hint)
                yield Static(f"[dim]{self.error}[/]")
                with Horizontal():
                    yield Button(label, variant="primary", id="setup_yes")
                    yield Button(tr("Later"), id="setup_no")

        @on(Button.Pressed, "#setup_yes")
        def _yes(self) -> None:
            self.dismiss(True)

        @on(Button.Pressed, "#setup_no")
        def action_later(self) -> None:
            self.dismiss(False)

    class ConfirmScreen(ModalScreen):
        """in-app confirmation; Cancel has the focus, so Enter never destroys anything by accident"""
        DEFAULT_CSS = """
        ConfirmScreen { align: center middle; background: #00000080; }
        #confirm_box { width: 64; height: auto; padding: 1 2; border: round #3f4656; background: #151a25; }
        #confirm_box.danger { border: round #f87171; }
        #confirm_box .t { text-style: bold; }
        #confirm_box .x { margin: 1 0 0 0; color: #9aa4b2; }
        #confirm_box Horizontal { height: auto; margin: 1 0 0 0; align-horizontal: right; }
        #confirm_box Button { margin: 0 0 0 2; }
        """
        BINDINGS = [("escape", "cancel", tr("Cancel"))]

        def __init__(self, title, text, ok, danger=False):
            super().__init__()
            self.title_, self.text, self.ok, self.danger = title, text, ok, danger

        def compose(self) -> ComposeResult:
            with Vertical(id="confirm_box", classes="danger" if self.danger else ""):
                yield Label(self.title_, classes="t")
                if self.text:
                    yield Static(self.text, classes="x")
                with Horizontal():
                    yield Button(tr("Cancel"), id="confirm_no")
                    yield Button(self.ok, id="confirm_yes", variant="error" if self.danger else "primary")

        def on_mount(self) -> None:
            self.query_one("#confirm_no", Button).focus()

        @on(Button.Pressed, "#confirm_yes")
        def _yes(self) -> None:
            self.dismiss(True)

        @on(Button.Pressed, "#confirm_no")
        def action_cancel(self) -> None:
            self.dismiss(False)

    class LanguageScreen(ModalScreen):
        DEFAULT_CSS = """
        LanguageScreen { align: center middle; background: #00000080; }
        #lang_box { width: 44; height: auto; padding: 1 2; border: round #3f4656; background: #151a25; }
        #lang_box OptionList { height: auto; margin: 1 0 0 0; }
        """
        BINDINGS = [("escape", "cancel", tr("Cancel"))]

        def compose(self) -> ComposeResult:
            setting = load_settings().get("lang", "auto")
            self.values = ["auto", *LANGUAGES]
            labels = [tr("System ({lang})", lang=LANGUAGES[resolve_language("auto")]), *LANGUAGES.values()]
            with Vertical(id="lang_box"):
                yield Label(tr("Language"), classes="t")
                ol = OptionList(*[("● " if v == setting else "  ") + lab for v, lab in zip(self.values, labels)])
                ol.highlighted = self.values.index(setting) if setting in self.values else 0
                yield ol

        @on(OptionList.OptionSelected)
        def _picked(self, ev: OptionList.OptionSelected) -> None:
            self.dismiss(self.values[ev.option_index])

        def action_cancel(self) -> None:
            self.dismiss(None)

    class RevenantApp(App):
        TITLE = "CZC.Gaming Revenant"
        CSS = """
        Screen { background: #0d0f14; }
        #main { height: 1fr; }
        #side { width: 40; padding: 0 1; border-right: solid #262d3d; }
        #side Horizontal { height: auto; }
        #side Horizontal Button { width: 1fr; min-width: 0; margin: 0 1 1 0; }
        #side .h { margin: 1 0 0 0; }
        #pf_active { text-style: bold; color: #e6e9ef; margin: 0 0 0 0; }
        #pf_state { margin: 0 0 1 0; }
        #side Button { width: 100%; margin: 0 0 1 0; }
        #pf_list { height: 1fr; min-height: 6; border: round #333a48; }
        #pf_info { color: #9aa4b2; height: auto; max-height: 5; margin: 0 0 1 0; }
        #pf_name { margin: 0 0 1 0; }
        #tabs { width: 1fr; }
        .kbdscroll { height: auto; }
        .kbd { height: auto; width: auto; padding: 1 1 0 1; }
        .krow { height: 3; width: auto; }
        .key { height: 3; content-align: center middle; border: tall #00000000; text-style: bold; }
        .key:hover { border: round #888888; }
        .key.selected { border: round #ffd54f; text-style: bold underline; }
        .gap { height: 3; }
        #toolbar { height: auto; padding: 0 1; }
        .swatch { width: 4; height: 3; margin: 0 1 0 0; }
        #custom { width: 11; height: 3; margin: 0 2 0 0; content-align: center middle; background: #1a1d26;
                  color: #9aa4b2; }
        .swatch:hover, #custom:hover { outline: tall #888888; }
        .swatch.active, #custom.active { outline: tall #ffffff; }
        #current { width: 10; height: 3; margin: 0 2 0 0; content-align: center middle; text-style: bold; }
        #hex { width: 14; }
        .row { height: auto; margin: 1 0 0 0; }
        .row Button { margin: 0 1 0 0; min-width: 10; }
        #status { height: 1; padding: 0 2; background: #1a1d26; color: #9aa4b2; }
        .stepper { height: 3; width: auto; }
        .steplabel { width: 12; padding: 1 0; }
        .step { min-width: 5; width: 5; }
        .bar { width: 24; padding: 1 1; color: #4fc3f7; }
        Label.h { margin: 1 0 0 0; text-style: bold; color: #4fc3f7; }
        .note { color: #9aa4b2; margin: 1 0 0 0; }
        .inline Label { padding: 1 1 0 0; }
        .pane { padding: 0 2; }
        #fxcolor { width: 14; }
        #rm_key { width: 22; } #rm_type { width: 22; } #rm_arg { width: 34; } #rm_mode { width: 30; } #rm_count { width: 9; }
        #rm_table { height: 10; margin: 1 0 0 0; }
        #mc_list { width: 28; height: 18; border: round #333a48; }
        #mc_edit { width: 1fr; height: 18; }
        #mc_name { width: 28; }
        #mc_help { margin: 1 0 0 2; color: #9aa4b2; }
        #gm_box Checkbox { margin: 0 0 0 2; }
        """
        BINDINGS = [("ctrl+s", "save_profile", tr("Save")), ("ctrl+a", "select_all", tr("Select all")),
                    ("escape", "clear_sel", tr("Clear selection")), ("f5", "send_all", tr("Re-send to keyboard")),
                    ("ctrl+r", "reload", tr("Reload")), ("f2", "setup", tr("Set up access")),
                    ("ctrl+l", "language", tr("Language")), ("ctrl+q", "quit", tr("Quit")),
                    # Ctrl+C quits too (Textual only shows a hint); priority so text inputs don't take it as copy
                    Binding("ctrl+c", "quit", tr("Quit"), show=False, priority=True)]

        def __init__(self):
            super().__init__()
            self._dev_state, self._connecting, self._setup_offered = "", False, False
            self.selected = set()
            self.current = "ff0000"
            self._picking = False
            self._mc_current = None
            self._pf_names = []
            self.remap_key = "caps"
            self._lock = threading.Lock()
            self.kb = None
            self.load_active()

        # ---------------------------------------------------------------- profile state
        def load_active(self):
            self.pname = get_active()
            self.prof = load_current()

        def save(self):
            save_current(self.prof)
            self.refresh_title()

        def refresh_title(self):
            dirty = is_dirty(self.prof)
            self.sub_title = tr("profile: {name}", name=self.pname) + (" • " + tr("unsaved") if dirty else "")
            if self.is_mounted:
                self.refresh_side(dirty)

        @property
        def L(self):
            return self.prof["lighting"]

        def key_color(self, k):
            return self.L["keys"].get(k, self.L["base"])

        # ---------------------------------------------------------------- layout
        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="main"):
                # ---- left: profiles (what is saved)
                with Vertical(id="side"):
                    yield Label(tr("Active profile"), classes="h")
                    yield Static("", id="pf_active")
                    yield Static("", id="pf_state")
                    with Horizontal():
                        yield Button(tr("Save"), id="pf_save")
                        yield Button(tr("Discard changes"), id="pf_discard")
                    yield Button(tr("Re-send to keyboard"), id="send_all")
                    yield Label(tr("Profiles"), classes="h")
                    yield OptionList(id="pf_list")
                    yield Static("", id="pf_info")
                    yield Button(tr("Delete selected"), id="pf_del", variant="error")
                    yield Input(placeholder=tr("name of a new profile"), id="pf_name")
                    with Horizontal():
                        yield Button(tr("Save as new"), id="pf_copy")
                        yield Button(tr("New empty"), id="pf_new")
                # ---- right: editor of the current settings (what is on the keyboard)
                with TabbedContent(id="tabs"):
                    with TabPane(tr("Lighting"), id="lightpane"):
                        with TabbedContent(id="lightmode"):
                            with TabPane(tr("Custom colours"), id="keyspane"):
                                with VerticalScroll():
                                    with HorizontalScroll(classes="kbdscroll"):
                                        with Vertical(classes="kbd", id="kbd"):
                                            yield from keyboard_rows(KeyCap)
                                    with Vertical(id="toolbar"):
                                        with Horizontal(classes="row"):
                                            yield Static("", id="current")
                                            for c in PALETTE:
                                                yield Swatch(c)
                                            yield CustomSwatch()
                                            yield Input(placeholder="#RRGGBB", id="hex", max_length=7)
                                        with Horizontal(classes="row"):
                                            for g in ["all", "letters", "numbers", "fkeys", "wasd", "arrows", "numpad", "nav", "mods"]:
                                                yield Button(g, name=g, id=f"grp-{g}", classes="grp")
                                        with Horizontal(classes="row"):
                                            yield Button(tr("Paint selection"), id="paint", variant="primary")
                                            yield Button(tr("Eyedropper"), id="pick")
                                            yield Button(tr("Turn selection off"), id="blank")
                                            yield Stepper(tr("Brightness"), self.L["key_brightness"], id="kbright")
                                            yield Button(tr("Turn all off"), id="clearall", variant="error")
                            with TabPane(tr("Effect"), id="fxpane"):
                                with VerticalScroll(classes="pane"):
                                    yield Label(tr("Effect"), classes="h")
                                    yield Select(effect_choices(), value=self.L["effect"], id="fxsel", allow_blank=False)
                                    yield Label(tr("Colour"), classes="h")
                                    with Horizontal(classes="row inline"):
                                        yield Label(tr("Rainbow"))
                                        yield Switch(value=bool(self.L["rainbow"]), id="fxrainbow")
                                        yield Label("   #")
                                        yield Input(value=self.L["color"], id="fxcolor", max_length=7)
                                    yield Label(tr("Parameters"), classes="h")
                                    yield Stepper(tr("Brightness"), self.L["brightness"], id="fxbright")
                                    yield Stepper(tr("Speed"), self.L["speed"], id="fxspeed")
                                    yield Label(tr("Direction"), classes="h")
                                    with RadioSet(id="fxdir"):
                                        for arrow, d in zip("→←↑↓", DIRS):
                                            yield RadioButton(f"{arrow} {direction_label(d)}", value=(d == self.L["direction"]))
                                    yield Button(tr("Run effect"), id="fxapply", variant="primary")
                    with TabPane(tr("Key functions"), id="rmpane"):
                        with VerticalScroll(classes="pane"):
                            yield Static(tr("Click a key on the keyboard, then choose what it should do. "
                                            "Keys with their own function have a dot."), classes="note")
                            with HorizontalScroll(classes="kbdscroll"):
                                with Vertical(classes="kbd", id="kbd_remap"):
                                    yield from keyboard_rows(RemapCap)
                            with Horizontal(classes="row"):
                                yield Select([(k, k) for k in sorted(KEYS, key=KEYS.get)], value="caps",
                                             id="rm_key", allow_blank=False)
                                yield Select(func_types(), value="disable", id="rm_type", allow_blank=False)
                                yield Input(placeholder="", id="rm_arg")
                            with Horizontal(classes="row", id="rm_macrorow"):
                                yield Select(macro_modes(), value="once", id="rm_mode", allow_blank=False)
                                yield Input(value="5", id="rm_count", max_length=3)
                            with Horizontal(classes="row"):
                                yield Button(tr("Assign"), id="rm_set", variant="primary")
                                yield Button(tr("Reset key"), id="rm_del")
                                yield Button(tr("All to default"), id="rm_clear", variant="error")
                            yield DataTable(id="rm_table", cursor_type="row", zebra_stripes=True)
                    with TabPane(tr("Macros"), id="mcpane"):
                        with VerticalScroll(classes="pane"):
                            with Horizontal(classes="row"):
                                yield Input(placeholder=tr("name of the new macro"), id="mc_name")
                                yield Button(tr("New macro"), id="mc_new")
                                yield Button(tr("Save macro"), id="mc_save", variant="primary")
                                yield Button(tr("Delete macro"), id="mc_del", variant="error")
                            with Horizontal(classes="row"):
                                yield OptionList(id="mc_list")
                                yield TextArea(id="mc_edit")
                            yield Static(macro_help(), id="mc_help")
                    with TabPane(tr("Game mode"), id="gmpane"):
                        with Vertical(classes="pane", id="gm_box"):
                            yield Label(tr("Game mode"), classes="h")
                            with Horizontal(classes="row inline"):
                                yield Label(tr("Enabled"))
                                yield Switch(value=self.prof["gamemode"]["enabled"], id="gm_on")
                            yield Label(tr("When enabled, block:"), classes="h")
                            yield Checkbox("Alt + Tab", self.prof["gamemode"]["alt_tab"], id="gm_alt_tab")
                            yield Checkbox("Alt + F4", self.prof["gamemode"]["alt_f4"], id="gm_alt_f4")
                            yield Checkbox(tr("Windows key"), self.prof["gamemode"]["win"], id="gm_win")
            yield Static("", id="status")
            yield Footer()

        def on_mount(self) -> None:
            t = self.query_one("#rm_table", DataTable)
            t.add_columns(tr("Key"), tr("Function"))
            self.refresh_all()
            self.set_current_color(self.current)
            self.connect()
            self.set_interval(4, self._watch_device)

        def refresh_all(self):
            self.refresh_title()
            self.refresh_keys()
            self.query_one("#lightmode", TabbedContent).active = "fxpane" if self.L["mode"] == "effect" else "keyspane"
            L = self.L
            self.query_one("#kbright", Stepper).set(L["key_brightness"])
            self.query_one("#fxsel", Select).value = L["effect"]
            self.query_one("#fxrainbow", Switch).value = bool(L["rainbow"])
            self.query_one("#fxcolor", Input).value = L["color"]
            self.query_one("#fxbright", Stepper).set(L["brightness"])
            self.query_one("#fxspeed", Stepper).set(L["speed"])
            g = self.prof["gamemode"]
            with self.prevent(Switch.Changed, Checkbox.Changed):
                self.query_one("#gm_on", Switch).value = g["enabled"]
                for k in ("alt_tab", "alt_f4", "win"):
                    self.query_one(f"#gm_{k}", Checkbox).value = g[k]
            self.refresh_remap()
            self.refresh_macros()
            self.refresh_profiles()
            self.update_type_hint()

        # ---------------------------------------------------------------- device
        @work(thread=True, exclusive=True, group="dev")
        def connect(self) -> None:
            self._connecting = True
            try:
                kb = Revenant()
                with self._lock:
                    self.kb = kb
                self._dev_state = "ok"
                self.call_from_thread(self.status, "✔ " + tr("Keyboard connected – profile '{name}'", name=self.pname))
            except RevenantNotFound:
                if self._dev_state != "missing":
                    self.call_from_thread(self.status, "✘ " + tr("Keyboard not found – connect it with the USB cable "
                                                                 "(it connects by itself; changes are saved to the profile meanwhile)"))
                self._dev_state = "missing"
            except RevenantError as e:
                first = self._dev_state != "denied"
                self._dev_state = "denied"
                msg = str(e).replace("\n", " – ")
                hint = "  [F2 = " + tr("set up access") + "]" if setup_kind() else ""
                self.call_from_thread(self.status, f"✘ {msg}{hint}")
                if first and setup_kind() and not self._setup_offered:
                    self._setup_offered = True
                    self.call_from_thread(self.offer_setup, str(e))
            finally:
                self._connecting = False

        def _watch_device(self) -> None:
            """every few seconds: notice unplugging and reconnect when the keyboard appears (no writes)"""
            if self.kb is not None and not keyboard_present():
                with self._lock:
                    try:
                        self.kb.dev.close()
                    except Exception:
                        pass
                    self.kb = None
                self._dev_state = "missing"
                self.status("✘ " + tr("Keyboard disconnected – it reconnects by itself when plugged in"))
            elif self.kb is None and not self._connecting and not isinstance(self.screen, SetupScreen):
                self.connect()

        def offer_setup(self, error) -> None:
            kind = setup_kind()
            if not kind:
                self.status("✘ " + tr("Close the original CZC program and try again.")); return

            def done(yes):
                if not yes:
                    self.status(tr("Access can be set up later with F2 or the command: revenant setup"))
                elif kind == "udev":
                    self.call_after_refresh(self.run_udev_setup)
                else:
                    open_macos_privacy()
                    self.status(tr("Allow the app in Settings → Input Monitoring, then start revenant again"))
            self.push_screen(SetupScreen(error, kind), done)

        def run_udev_setup(self) -> None:
            import shutil
            try:
                try:
                    with self.suspend():                   # give the terminal to sudo for the password
                        print("\nrevenant: " + tr("installing the udev rule – enter the administrator password") + "\n", flush=True)
                        install_udev_rule("sudo" if shutil.which("sudo") else "pkexec")
                except RevenantError:
                    raise
                except Exception:                          # suspend not supported: graphical password dialog
                    install_udev_rule("pkexec")
                self.status("✔ " + tr("Access set up – connecting the keyboard…"))
            except RevenantError as e:
                self.status(f"✘ {e}")
            self._dev_state = ""
            self.connect()

        def action_setup(self) -> None:
            if self.kb is not None:
                self.status("✔ " + tr("The keyboard is connected and accessible – nothing to set up")); return
            err = probe()
            if err is None:
                self.connect()
            elif isinstance(err, RevenantNotFound):
                self.status("✘ " + tr("Keyboard not found – connect it with the USB cable"))
            else:
                self.offer_setup(str(err))

        def send(self, parts, msg=None):
            self.save()
            self._send(tuple(parts), copy.deepcopy(self.prof), msg or "✔ " + tr("Sent"))

        @work(thread=True, group="send")
        def _send(self, parts, prof, msg) -> None:
            if not self.kb:
                self.call_from_thread(self.status, "✘ " + tr("The keyboard is not connected (saved to the profile only)")); return
            try:
                with self._lock:
                    ok = sync(self.kb, prof, parts)
                self.call_from_thread(self.status, msg if ok else "⚠ " + tr("Sent, but the checksum does not match"))
            except (ValueError, KeyError) as e:
                self.call_from_thread(self.status, f"✘ {e}")
            except Exception as e:
                self.kb = None
                self.call_from_thread(self.status, "✘ " + tr("Error: {error} – trying to reconnect", error=e))
                self.call_from_thread(self.connect)

        def status(self, msg):
            self.query_one("#status", Static).update(msg)

        # ---------------------------------------------------------------- key colors
        def refresh_keys(self):
            for cap in self.query("#kbd KeyCap"):
                cap.paint(self.key_color(cap.key), cap.key in self.selected)

        def confirm(self, title, text, ok, then, danger=True):
            """ask in an in-app dialog; run then() only on OK"""
            self.push_screen(ConfirmScreen(title, text, ok, danger), lambda yes: then() if yes else None)

        def toggle_key(self, key):
            if self._picking:
                self._picking = False
                self.set_current_color(self.key_color(key), apply=False)
                self.status(tr("Eyedropper: #{color}", color=self.key_color(key))); return
            self.selected ^= {key}
            self.selection_changed(key if key in self.selected else None)

        def selection_changed(self, clicked=None):
            """show the colour of the clicked key (or of a whole selection sharing one colour) as the current
            colour, marked in the palette / Custom – nothing is sent"""
            self.refresh_keys()
            self.status(tr("Keys selected: {n}", n=len(self.selected)))
            colors = {self.key_color(k) for k in self.selected}
            if clicked:
                self.set_current_color(self.key_color(clicked), apply=False)
            elif len(colors) == 1:
                self.set_current_color(colors.pop(), apply=False)

        def set_current_color(self, hexcol, apply=True):
            """apply = also paint the selected keys with it"""
            self.current = hexcol.lower()
            cur = self.query_one("#current", Static)
            cur.styles.background = Color.parse("#" + self.current)
            cur.styles.color = contrast(self.current)
            cur.update("#" + self.current)
            for sw in self.query(Swatch):
                sw.set_class(sw.hexcol == self.current, "active")
            custom = self.query_one(CustomSwatch)
            if self.current not in PALETTE:
                custom.show(self.current)
            custom.set_class(self.current not in PALETTE, "active")
            if apply and self.selected:
                self.paint_selected(self.current)

        def paint_selected(self, col):
            if not self.selected:
                self.status(tr("Select keys first (click them or a group)")); return
            for k in self.selected:
                self.L["keys"][k] = col
            self.push_keys()

        def push_keys(self):
            self.L["keys"] = {k: v for k, v in self.L["keys"].items() if v != self.L["base"]}
            self.L["mode"] = "keys"
            self.L["key_brightness"] = self.query_one("#kbright", Stepper).value
            self.refresh_keys()
            self.send(["lighting"])

        @on(Button.Pressed, ".grp")
        def _group(self, ev: Button.Pressed) -> None:
            keys = set(KEY_GROUPS[ev.button.name])
            self.selected = set() if keys <= self.selected else (self.selected | keys)
            self.selection_changed()

        @on(Button.Pressed, "#paint")
        def _paint(self) -> None:
            self.paint_selected(self.current)

        @on(Button.Pressed, "#pick")
        def _pick(self) -> None:
            self._picking = True
            self.status(tr("Eyedropper: click the key whose colour you want to take"))

        @on(Button.Pressed, "#blank")
        def _blank(self) -> None:
            self.paint_selected("000000")

        @on(Button.Pressed, "#clearall")
        def _clearall(self) -> None:
            def go():
                self.L["keys"], self.L["base"] = {}, "000000"
                self.push_keys()
            self.confirm(tr("Turn all keys off?"), tr("You can go back with Discard changes until you save."),
                         tr("Turn all off"), go)

        @on(Button.Pressed, "#kbright .step")
        def _kb_bright(self) -> None:
            self.call_after_refresh(self.push_keys)

        @on(Input.Submitted, "#hex")
        def _hex(self, ev: Input.Submitted) -> None:
            v = ev.value.strip().lstrip("#")
            try:
                hex2rgb(v); assert len(v) == 6
            except Exception:
                self.status(tr("Invalid colour – enter RRGGBB")); return
            self.set_current_color(v)
            ev.input.value = ""

        # ---------------------------------------------------------------- effects
        @on(Button.Pressed, "#fxapply")
        def _fx(self) -> None:
            col = self.query_one("#fxcolor", Input).value.strip().lstrip("#")
            try:
                hex2rgb(col); assert len(col) == 6
            except Exception:
                self.status(tr("Invalid effect colour")); return
            idx = self.query_one("#fxdir", RadioSet).pressed_index
            self.L.update(mode="effect", effect=self.query_one("#fxsel", Select).value,
                          rainbow=self.query_one("#fxrainbow", Switch).value, color=col.lower(),
                          brightness=self.query_one("#fxbright", Stepper).value,
                          speed=self.query_one("#fxspeed", Stepper).value, direction=DIRS[max(0, idx)])
            self.send(["lighting"], "✔ " + tr("Effect {name} started", name=effect_label(self.L["effect"])))

        # ---------------------------------------------------------------- remap
        def refresh_remap(self):
            t = self.query_one("#rm_table", DataTable)
            t.clear()
            for k, v in sorted(self.prof["remap"].items(), key=lambda kv: KEYS[kv[0]]):
                t.add_row(k, v, key=k)
            for cap in self.query(RemapCap):
                cap.paint_remap(cap.key in self.prof["remap"], cap.key == self.remap_key)

        def pick_remap_key(self, key):
            """load a key's current function into the form"""
            self.remap_key = key
            spec = self.prof["remap"].get(key, "default")
            self.query_one("#rm_key", Select).value = key
            kind, _, arg = spec.partition(":")
            arg_input = self.query_one("#rm_arg", Input)
            if kind == "macro":
                parts = arg.split(":")
                self.query_one("#rm_type", Select).value = "macro"
                arg_input.value = parts[0]
                self.query_one("#rm_mode", Select).value = parts[1] if len(parts) > 1 else "once"
                if len(parts) > 2:
                    self.query_one("#rm_count", Input).value = parts[2]
            elif kind in ("disable", "default", "combo", "media", "mouse", "key"):
                self.query_one("#rm_type", Select).value = kind
                arg_input.value = arg
            else:                                   # bare key name
                self.query_one("#rm_type", Select).value = "key"
                arg_input.value = spec
            self.refresh_remap()

        def update_type_hint(self):
            typ = self.query_one("#rm_type", Select).value
            arg = self.query_one("#rm_arg", Input)
            arg.placeholder = func_hints().get(typ, "")
            arg.disabled = typ in ("default", "disable")
            if typ == "macro" and not arg.value and self.prof["macros"]:
                arg.value = next(iter(self.prof["macros"]))
            is_macro = typ == "macro"
            self.query_one("#rm_mode", Select).disabled = not is_macro
            self.query_one("#rm_count", Input).disabled = not (is_macro and self.query_one("#rm_mode", Select).value == "repeat")

        @on(Select.Changed, "#rm_type")
        @on(Select.Changed, "#rm_mode")
        def _rm_type(self) -> None:
            self.update_type_hint()

        @on(DataTable.RowSelected, "#rm_table")
        def _rm_row(self, ev: DataTable.RowSelected) -> None:
            self.pick_remap_key(ev.row_key.value)

        @on(Select.Changed, "#rm_key")
        def _rm_key(self, ev: Select.Changed) -> None:
            if ev.value != self.remap_key and isinstance(ev.value, str):
                self.pick_remap_key(ev.value)

        @on(Button.Pressed, "#rm_set")
        def _rm_set(self) -> None:
            key = self.query_one("#rm_key", Select).value
            typ = self.query_one("#rm_type", Select).value
            arg = self.query_one("#rm_arg", Input).value.strip()
            if typ in ("default", "disable"):
                spec = typ
            elif typ == "macro":
                mode = self.query_one("#rm_mode", Select).value
                spec = f"macro:{arg}:{mode}"
                if mode == "repeat":
                    spec += ":" + (self.query_one("#rm_count", Input).value.strip() or "1")
            else:
                spec = f"{typ}:{arg}"
            try:
                encode_action(spec, {n: i for i, n in enumerate(self.prof["macros"])})
            except (ValueError, KeyError) as e:
                self.status(f"✘ {e}"); return
            if spec == "default":
                self.prof["remap"].pop(key, None)
            else:
                self.prof["remap"][key] = spec
            self.refresh_remap()
            self.send(["keys"], f"✔ {key} = {spec}")

        @on(Button.Pressed, "#rm_del")
        def _rm_del(self) -> None:
            key = self.remap_key
            self.prof["remap"].pop(key, None)
            self.refresh_remap()
            self.send(["keys"], "✔ " + tr("{key} has its default function", key=key))

        @on(Button.Pressed, "#rm_clear")
        def _rm_clear(self) -> None:
            if not self.prof["remap"]:
                return
            def go():
                self.prof["remap"] = {}
                self.refresh_remap()
                self.send(["keys"], "✔ " + tr("All keys have their default function"))
            self.confirm(tr("Reset all keys to their default function?"), "", tr("All to default"), go)

        # ---------------------------------------------------------------- macros
        def refresh_macros(self, select=None):
            ol = self.query_one("#mc_list", OptionList)
            ol.clear_options()
            names = list(self.prof["macros"])
            ol.add_options(names)
            if names:
                i = names.index(select) if select in names else 0
                ol.highlighted = i
                self.show_macro(names[i])
            else:
                self.query_one("#mc_edit", TextArea).text = ""
                self._mc_current = None

        def show_macro(self, name):
            self._mc_current = name
            self.query_one("#mc_edit", TextArea).text = "\n".join(self.prof["macros"][name])

        @on(OptionList.OptionHighlighted, "#mc_list")
        def _mc_pick(self, ev: OptionList.OptionHighlighted) -> None:
            name = str(ev.option.prompt)
            if name in self.prof["macros"]:
                self.show_macro(name)

        @on(Button.Pressed, "#mc_new")
        def _mc_new(self) -> None:
            name = self.query_one("#mc_name", Input).value.strip()
            if not name or ":" in name or " " in name:
                self.status(tr("Enter a macro name (no spaces or colons)")); return
            if name in self.prof["macros"]:
                self.status(tr("The macro already exists")); return
            self.prof["macros"][name] = ["text:" + tr("Hello!")]
            self.query_one("#mc_name", Input).value = ""
            self.refresh_macros(select=name)
            self.send(["keys"], "✔ " + tr("Macro '{name}' created – edit the steps and save", name=name))

        @on(Button.Pressed, "#mc_save")
        def _mc_save(self) -> None:
            name = self._mc_current
            if not name:
                self.status(tr("Create or select a macro first")); return
            steps = [l.strip() for l in self.query_one("#mc_edit", TextArea).text.splitlines() if l.strip()]
            try:
                compile_macro(steps)
            except (ValueError, KeyError) as e:
                self.status("✘ " + tr("Error in macro: {error}", error=e)); return
            self.prof["macros"][name] = steps
            self.send(["keys"], "✔ " + tr("Macro '{name}' saved ({n} steps)", name=name, n=len(steps)))

        @on(Button.Pressed, "#mc_del")
        def _mc_del(self) -> None:
            name = self._mc_current
            if not name:
                return
            used = [k for k, v in self.prof["remap"].items() if v.split(":")[:2] == ["macro", name]]
            if used:
                self.status("✘ " + tr("The macro is used by keys {keys} – change their function first", keys=", ".join(used))); return
            def go():
                del self.prof["macros"][name]
                self.refresh_macros()
                self.send(["keys"], "✔ " + tr("Macro '{name}' deleted", name=name))
            self.confirm(tr("Delete macro '{name}'?", name=name), "", tr("Delete"), go)

        # ---------------------------------------------------------------- game mode
        @on(Switch.Changed, "#gm_on")
        @on(Checkbox.Changed)
        def _gm(self) -> None:
            g = self.prof["gamemode"]
            g["enabled"] = self.query_one("#gm_on", Switch).value
            for k in ("alt_tab", "alt_f4", "win"):
                g[k] = self.query_one(f"#gm_{k}", Checkbox).value
            self.send(["gamemode"], "✔ " + (tr("Game mode on") if g["enabled"] else tr("Game mode off")))

        # ---------------------------------------------------------------- profiles (sidebar)
        def refresh_side(self, dirty=None):
            dirty = is_dirty(self.prof) if dirty is None else dirty
            self.query_one("#pf_active", Static).update(self.pname)
            self.query_one("#pf_state", Static).update(
                "[#fbbf24]● " + tr("Unsaved changes") + "[/]" if dirty else "[#34d399]✔ " + tr("Saved") + "[/]")
            save = self.query_one("#pf_save", Button)
            save.disabled = not dirty
            save.variant = "primary" if dirty else "default"
            self.query_one("#pf_discard", Button).disabled = not dirty

        def refresh_profiles(self):
            ol = self.query_one("#pf_list", OptionList)
            ol.clear_options()
            names = list_profiles()
            ol.add_options([("● " if n == self.pname else "  ") + n for n in names])
            if self.pname in names:
                ol.highlighted = names.index(self.pname)
            self._pf_names = names
            self.show_profile_info(self.pname)
            self.refresh_side()

        def show_profile_info(self, name):
            try:
                txt = describe_profile(self.prof if name == self.pname else load_profile(name))
            except Exception as e:
                txt = tr("error: {error}", error=e)
            self.query_one("#pf_info", Static).update(txt)
            self.query_one("#pf_del", Button).disabled = name == self.pname

        def selected_profile(self):
            ol = self.query_one("#pf_list", OptionList)
            return self._pf_names[ol.highlighted] if ol.highlighted is not None and self._pf_names else None

        @on(OptionList.OptionHighlighted, "#pf_list")
        def _pf_pick(self) -> None:
            n = self.selected_profile()
            if n:
                self.show_profile_info(n)

        @on(OptionList.OptionSelected, "#pf_list")
        def _pf_load(self) -> None:
            """Enter / click on a profile loads it (asks first when there are unsaved changes)"""
            n = self.selected_profile()
            if not n or n == self.pname:
                return
            def go():
                try:
                    prof = use_profile(n)
                except Exception as e:
                    self.status("✘ " + tr("Profile '{name}': {error}", name=n, error=e)); return
                self.pname, self.prof, self.selected = n, prof, set()
                self.refresh_all()
                self.send(("lighting", "keys", "gamemode"), "✔ " + tr("Profile '{name}' is active", name=n))
            if is_dirty(self.prof):
                self.confirm(tr("Load profile '{name}'?", name=n),
                             tr("Unsaved changes to '{active}' will be lost.", active=self.pname), tr("Load profile"), go)
            else:
                go()

        def _pf_target(self):
            n = self.query_one("#pf_name", Input).value.strip()
            if not n or any(c in n for c in '\\/:*?"<>|'):
                self.status(tr("Enter a valid profile name")); return None
            return n

        @on(Button.Pressed, "#pf_new")
        def _pf_new(self) -> None:
            n = self._pf_target()
            if n:
                if n in list_profiles():
                    self.status(tr("The profile already exists")); return
                save_profile(n, _template()); self.query_one("#pf_name", Input).value = ""
                self.refresh_profiles(); self.status("✔ " + tr("Profile '{name}' created", name=n))

        @on(Button.Pressed, "#pf_copy")
        def _pf_copy(self) -> None:
            n = self._pf_target()
            if n:
                self.save()
                self.pname = save_current_as(n)
                self.query_one("#pf_name", Input).value = ""
                self.refresh_profiles(); self.refresh_title()
                self.status("✔ " + tr("Current settings saved as '{name}'", name=n))

        @on(Button.Pressed, "#pf_save")
        def action_save_profile(self) -> None:
            self.save()
            save_current_as(self.pname)
            self.refresh_profiles(); self.refresh_title()
            self.status("✔ " + tr("Saved to profile '{name}'", name=self.pname))

        @on(Button.Pressed, "#pf_discard")
        def _pf_discard(self) -> None:
            if not is_dirty(self.prof):
                self.status(tr("No unsaved changes")); return
            def go():
                self.prof, self.selected = discard_changes(), set()
                self.refresh_all()
                self.send(("lighting", "keys", "gamemode"),
                          "✔ " + tr("Changes discarded – profile '{name}' restored", name=self.pname))
            self.confirm(tr("Discard changes?"), tr("The keyboard goes back to the saved profile '{name}'.", name=self.pname),
                         tr("Discard changes"), go)

        @on(Button.Pressed, "#pf_del")
        def _pf_del(self) -> None:
            n = self.selected_profile()
            if not n:
                return
            if n == self.pname:
                self.status("✘ " + tr("The active profile can't be deleted")); return
            def go():
                (PROFILE_DIR / f"{n}.json").unlink(missing_ok=True)
                self.refresh_profiles(); self.status("✔ " + tr("Profile '{name}' deleted", name=n))
            self.confirm(tr("Delete profile '{name}'?", name=n), tr("This can't be undone."), tr("Delete"), go)

        @on(Button.Pressed, "#send_all")
        def _send_all_button(self) -> None:
            self.action_send_all()

        # ---------------------------------------------------------------- actions
        def action_send_all(self) -> None:
            self.send(("lighting", "keys", "gamemode"), "✔ " + tr("Current settings sent to the keyboard"))

        def action_reload(self) -> None:
            self.load_active()
            self.selected = set()
            self.refresh_all()
            self.status(tr("Current settings reloaded from file"))

        def action_select_all(self) -> None:
            self.selected = set(KEYS); self.refresh_keys()

        def action_clear_sel(self) -> None:
            self.selected = set(); self._picking = False; self.refresh_keys(); self.status(tr("Selection cleared"))

        def action_language(self) -> None:
            """pick a language (or the system's) and restart the UI in it"""
            def picked(value):
                if value is None:
                    return
                save_settings(lang=value)
                set_language(resolve_language(value))
                self.exit("language")
            self.push_screen(LanguageScreen(), picked)

    if RevenantApp().run() == "language":
        return run_tui()


# ================================================================ web UI
WEB_PORT = 8462          # free on stock Windows/macOS/Linux; avoids 5000/7000 (macOS AirPlay) and 8000/8080
WEB_DIR = Path(__file__).resolve().with_name("revenant_web")
WEB_FILES = {"/": ("index.html", "text/html; charset=utf-8"),
             "/style.css": ("style.css", "text/css; charset=utf-8"),
             "/app.js": ("app.js", "text/javascript; charset=utf-8")}
_BAD_NAME = set('\\/:*?"<>|')


def _profile_name(name):
    name = str(name or "").strip()
    if not name or name.startswith(".") or _BAD_NAME & set(name) or len(name) > 64:
        raise ValueError(tr("invalid profile name"))
    return name


def _check_lighting(L):
    """raise ValueError if a lighting block would fail when sent"""
    try:
        for c in [L["color"], L["base"], *L["keys"].values()]:
            parse_color(str(c))
        parse_direction(str(L["direction"]))
    except argparse.ArgumentTypeError as ex:
        raise ValueError(str(ex))
    if L["mode"] not in ("effect", "keys") or L["effect"] not in EFFECTS:
        raise ValueError(tr("unknown mode or effect"))
    for k in L["keys"]:
        resolve_keys(k)
    for v in ("brightness", "speed", "key_brightness"):
        if not 0 <= int(L[v]) <= 16:
            raise ValueError(tr("{name} must be 0-16", name=v))


class _Device:
    """keyboard shared by web request threads; state: 'ok' | 'missing' | 'denied'"""
    def __init__(self, verbose=False):
        self.kb, self.verbose = None, verbose
        self.state, self.error = "missing", ""
        self.lock = threading.Lock()

    def _close(self):
        try:
            self.kb.dev.close()
        except Exception:
            pass
        self.kb = None

    def _fail(self, ex):
        self.state = "missing" if isinstance(ex, RevenantNotFound) else "denied"
        self.error = str(ex)

    def check(self):
        """refresh the status without writing anything to the keyboard"""
        with self.lock:
            if self.kb is not None and not keyboard_present():
                self._close()                             # unplugged
            if self.kb is None:
                try:
                    self.kb = Revenant(self.verbose)
                    self.state, self.error = "ok", ""
                except RevenantError as ex:
                    self._fail(ex)
        return self.info()

    def info(self):
        return {"state": self.state, "error": self.error,
                "setup": setup_kind() if self.state == "denied" else None}

    def send(self, prof, parts):
        with self.lock:
            for attempt in (1, 2):
                try:
                    if self.kb is None:
                        self.kb = Revenant(self.verbose)
                    ok = sync(self.kb, prof, parts)
                    self.state, self.error = "ok", ""
                    return ok
                except RevenantError as ex:
                    self._close()
                    self._fail(ex)
                    raise
                except (OSError, IOError) as ex:          # unplugged since last use: reopen once
                    self._close()
                    if attempt == 2:
                        self.state, self.error = "missing", str(ex)
                        raise RevenantError(tr("communication error with the keyboard: {error}", error=ex))


def _web_setup(dev):
    """run the one-time OS setup from the web page"""
    import shutil
    kind = setup_kind()
    if kind == "macos":
        open_macos_privacy()
        return tr("Opened Settings → Input Monitoring. Allow the app revenant runs from and restart it."), "warn"
    if kind != "udev":
        raise ValueError(tr("no setup is needed on this system – close the original CZC program"))
    gui = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if gui and shutil.which("pkexec"):
        install_udev_rule("pkexec")               # system password dialog
    elif sys.stdin.isatty() and shutil.which("sudo"):
        print("\nrevenant web: " + tr("enter the administrator password to install the udev rule"), flush=True)
        install_udev_rule("sudo")                 # asks in the terminal running `revenant web`
    else:
        raise RevenantError(tr("Can't ask for the password – run in a terminal:  revenant setup"))
    info = dev.check()
    if info["state"] == "ok":
        return tr("Access set up – the keyboard is connected"), "ok"
    return tr("Rule installed; unplug and re-plug the keyboard cable"), "warn"


def _web_state(dev):
    active = get_active()
    names = list_profiles()
    info = {}
    for n in names:
        try:
            info[n] = describe_profile(load_profile(n))
        except Exception as ex:                          # broken JSON etc.
            info[n] = tr("error: {error}", error=ex)
    current = load_current()
    return {"version": __version__, "active": active, "profile": current, "dirty": is_dirty(current), "profiles": names,
            "info": info, "device": dev.info(), "rows": ROWS, "labels": LABELS, "palette": PALETTE,
            "groups": KEY_GROUPS, "keys": sorted(KEYS, key=KEYS.get), "effects": effect_choices(),
            "funcTypes": func_types(), "funcHints": func_hints(), "macroModes": macro_modes(),
            "lang": LANG, "languages": LANGUAGES, "langSetting": load_settings().get("lang", "auto"),
            "systemLang": resolve_language("auto"),
            "strings": _catalog}


def _web_action(dev, path, req):
    """returns (message, level) ; raises ValueError/KeyError/FileNotFoundError on bad input"""
    def send(prof, parts, done):
        try:
            ok = dev.send(prof, parts)
        except RevenantError as ex:
            return tr("Saved, but the keyboard: {error}", error=ex), "warn"
        return (done, "ok") if ok else (tr("Sent, but the checksum does not match – try again"), "warn")

    ALL = ("lighting", "keys", "gamemode")
    if path == "/api/setup":
        return _web_setup(dev)
    if path == "/api/lang":
        value = str(req.get("lang") or "auto")
        if value != "auto" and value not in LANGUAGES:
            raise ValueError(tr("unknown language"))
        save_settings(lang=value)
        set_language(resolve_language(value))
        return tr("Language: {lang}", lang=LANGUAGES[LANG]), "ok"
    if path == "/api/save":
        prof = normalize_profile(req["profile"])
        _check_lighting(prof["lighting"])
        validate_profile(prof)
        parts = [x for x in req.get("parts", []) if x in ALL]
        save_current(prof)
        return send(prof, parts, req.get("done") or tr("Saved and sent")) if parts else (tr("Saved"), "ok")
    if path == "/api/apply":
        return send(load_current(), ALL, tr("Whole profile sent"))
    if path == "/api/use":
        name = _profile_name(req.get("name"))
        return send(use_profile(name), ALL, tr("Profile '{name}' is active", name=name))
    if path == "/api/profile-save":
        name = save_current_as(get_active())
        return tr("Saved to profile '{name}'", name=name), "ok"
    if path == "/api/discard":
        return send(discard_changes(), ALL, tr("Changes discarded – profile '{name}' restored", name=get_active()))
    if path == "/api/new":
        name = _profile_name(req.get("name"))
        if name in list_profiles():
            raise ValueError(tr("The profile already exists"))
        save_profile(name, _template())
        return tr("Profile '{name}' created", name=name), "ok"
    if path == "/api/copy":
        name = save_current_as(_profile_name(req.get("name")))
        return tr("Current settings saved as '{name}'", name=name), "ok"
    if path == "/api/delete":
        name = _profile_name(req.get("name"))
        if name == get_active():
            raise ValueError(tr("The active profile can't be deleted"))
        (PROFILE_DIR / f"{name}.json").unlink(missing_ok=True)
        return tr("Profile '{name}' deleted", name=name), "ok"
    raise KeyError(tr("unknown action"))


def make_web_server(port=None, verbose=False):
    """create the web UI server on 127.0.0.1 (port None = WEB_PORT or any free one); call serve_forever() on it"""
    import http.server
    if not WEB_DIR.is_dir():
        raise RevenantError(tr("the web UI folder is missing: {path}", path=WEB_DIR))
    dev = _Device(verbose)
    get_active()
    dev.check()

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "revenant"

        def log_message(self, fmt, *args):
            if verbose:
                sys.stderr.write("web: " + fmt % args + "\n")

        def _reply(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def _local(self):
            """reject other hosts (DNS rebinding): the page is served only as 127.0.0.1/localhost"""
            host = (self.headers.get("Host") or "").lower()
            host = host.rsplit("]", 1)[0].lstrip("[") if host.startswith("[") else host.split(":")[0]
            return host in ("127.0.0.1", "localhost", "::1")

        def do_GET(self):
            if not self._local():
                return self._reply(403, {"error": "forbidden"})
            path = self.path.split("?")[0]
            if path == "/api/state":
                return self._reply(200, _web_state(dev))
            if path == "/api/device":
                return self._reply(200, dev.check())
            if path in WEB_FILES:
                fname, ctype = WEB_FILES[path]
                return self._reply(200, (WEB_DIR / fname).read_bytes(), ctype)
            self._reply(404, {"error": "not found"})

        def do_POST(self):
            # custom header = browsers must preflight cross-site requests, which we never allow
            if not self._local() or self.headers.get("X-Revenant") != "1":
                return self._reply(403, {"ok": False, "error": "forbidden"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                return self._reply(413, {"ok": False, "error": tr("request too large")})
            try:
                req = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(req, dict):
                    raise ValueError(tr("expected a JSON object"))
                msg, level = _web_action(dev, self.path, req)
                self._reply(200, {"ok": True, "msg": msg, "level": level, "state": _web_state(dev)})
            except (ValueError, KeyError, TypeError, FileNotFoundError, RevenantError) as ex:
                err = ex.args[0] if isinstance(ex, KeyError) and ex.args else str(ex)
                self._reply(400, {"ok": False, "error": f"{err}", "state": _web_state(dev)})

    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address = os.name != "nt"     # on Windows it would let two servers share one port
        daemon_threads = True

    srv = None
    for p in ([port] if port is not None else [WEB_PORT, 0]):  # 0 = any free port chosen by the OS
        try:
            srv = Server(("127.0.0.1", p), Handler)
            break
        except OSError as ex:
            if port:
                raise RevenantError(tr("port {port} can't be used: {error}", port=port, error=ex))
    srv.device = dev
    return srv


def open_browser_quietly(url):
    """open the page; the browser inherits our stdout/stderr, and Chrome prints internal noise there
    ("Opening in existing browser session", zygote "Broken pipe" ...) - give it /dev/null instead"""
    import webbrowser
    sys.stdout.flush(); sys.stderr.flush()
    saved = []
    try:
        saved = [os.dup(1), os.dup(2)]
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, 1); os.dup2(null, 2); os.close(null)
    except OSError:
        saved = []
    try:
        webbrowser.open(url)
    except Exception:
        pass
    finally:
        for fd, orig in zip((1, 2), saved):
            os.dup2(orig, fd); os.close(orig)


def run_web(port=None, open_browser=True, verbose=False):
    srv = make_web_server(port, verbose)
    url = f"http://127.0.0.1:{srv.server_port}/"
    print(f"revenant web: {url}   " + tr("(Ctrl+C to stop)"), flush=True)
    if open_browser:
        if verbose:                          # -v: let the browser's own messages through, for debugging
            import webbrowser
            webbrowser.open(url)
        else:
            open_browser_quietly(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        srv.server_close()


def cli():
    """entry point (python revenant.py, uvx revenant-rgb, revenant)"""
    for i, arg in enumerate(sys.argv):                # --lang must apply before argparse builds its help
        if arg.startswith("--lang="):
            set_language(resolve_language(arg.split("=", 1)[1]))
        elif arg == "--lang" and i + 1 < len(sys.argv):
            set_language(resolve_language(sys.argv[i + 1]))
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")       # never crash on a console that can't show diacritics
        except (AttributeError, ValueError):
            pass
    try:
        main()
    except RevenantError as ex:
        sys.exit(str(ex))


if __name__ == "__main__":
    cli()
