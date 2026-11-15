# revenant

[Čeština](https://github.com/lachyn/revenant-rgb/blob/main/README.cs.md) · **English**

Unofficial cross-platform driver for the **CZC.Gaming Revenant** gaming keyboard
(SONiX chip, USB `0C45:8006`). It replaces the original CZC software, which exists only for Windows
and does less – this one runs on **Windows, Linux and macOS**.

- **Lighting** – 19 hardware effects (colour/rainbow, brightness, speed, direction) and a custom colour for each of the 104 keys
- **Key functions** – remap to another key, a key combination, a media function, a mouse button, a macro, or disable the key
- **Macros** – type text, key combinations, pauses, mouse clicks; play once / N times / toggle
- **Game mode** – block Alt+Tab, Alt+F4 and the Windows key
- **Profiles** – named complete setups, switched with one command, or automatically by the running game
- **TUI** (mouse-driven text UI), **web UI** in the browser and a **command line** – all working on the same current settings
- **English and Czech** – chosen automatically by the system language, switchable any time
- **Sample profiles** – monokai, nord, ocean, synthwave, sunset, an FPS layout and more, installed on first run

Everything is stored in the keyboard itself, so the settings keep working without the program running and on another computer.

> **The keyboard must be connected with the USB cable** and the mode switch on its bottom must be set to **Off**
> (wired mode). Over the 2.4 GHz dongle or Bluetooth it can't be configured – the original CZC software can't do it
> either. Once configured, the settings work in every mode.

### Why this exists

The keyboard ships with nothing but the original CZC program – a closed, **Windows-only** application that also
wants administrator rights. No Linux or macOS version, no API, SDK or protocol documentation, no command line,
nothing you could script or extend. Switching a profile means clicking around in its window.

So the communication with the keyboard was **sniffed**: the original program was run under
[Frida](https://frida.re), which logged every packet it sent to the keyboard. The program was driven automatically
(clicks and screenshots), so the data sent for every single click was known. From that the whole protocol was
pieced together – lighting, key functions, macros and game mode – and this driver reproduces it byte for byte.
Nothing was decompiled or copied from CZC's code; only the data between the program and the keyboard was observed,
for the purpose of interoperability. Details in [Protocol](#protocol) and
[How the protocol was found](#how-the-protocol-was-found).

---

## Contents
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [TUI](#tui)
- [Web UI](#web-ui)
- [Command line](#command-line)
- [Language](#language)
- [Profiles](#profiles)
- [Automatic profile switching](#automatic-profile-switching)
- [Using it as a library](#using-it-as-a-library)
- [Troubleshooting](#troubleshooting)
- [What is verified](#what-is-verified)
- [Protocol](#protocol)
- [How the protocol was found](#how-the-protocol-was-found)
- [Project layout](#project-layout)

---

## Requirements

- Python **3.9+**
- the keyboard connected with the **USB cable** – the right switch on the bottom set to **Off**.
  It cannot be configured over 2.4 GHz or Bluetooth (same as with the original software).
- libraries `hidapi`, `textual` (TUI) and `psutil` (automatic profile switching) – installed automatically, see below

## Installation

The easiest way is [uv](https://docs.astral.sh/uv/) (it downloads Python too if needed):

```
uv tool install revenant-rgb      # then the `revenant` command works anywhere
revenant                          # text UI
revenant web                      # web UI
uv tool upgrade revenant-rgb      # update
```

or `uvx revenant-rgb` to run it without installing, or `pip install revenant-rgb`.
Then follow the system notes below (Linux: `revenant setup` once).

### From source

The program is `revenant.py` (command line, TUI and web UI server) plus the `revenant_web/` folder with the page.
Python is all you need, nothing has to be installed by hand:

```
git clone https://github.com/lachyn/revenant-rgb.git revenant
cd revenant
python revenant.py            # Windows (or: py revenant.py)
python3 revenant.py           # Linux / macOS (or: ./revenant.py)
```

On first run the program creates its own environment and installs the libraries into it
(`hidapi`, `textual`, `psutil`) – it takes a few seconds and happens only once. The environment lives in:

| System | Location |
|---|---|
| Linux | `~/.cache/revenant/venv` |
| macOS | `~/Library/Caches/revenant/venv` |
| Windows | `%LOCALAPPDATA%\revenant\venv` |

Deleting the folder uninstalls everything. If you prefer your own package management:

- **uv**: `uv run revenant.py …` – the dependencies are declared in the file header (PEP 723)
- **pip**: `pip install -r requirements.txt` and disable the automatic install with `REVENANT_NO_BOOTSTRAP=1`

### Without cloning: with `uv`

With [uv](https://docs.astral.sh/uv/) you don't need to clone or even install Python (uv downloads one if needed):

```
# one-off run (cached by uv, later runs start right away)
uvx --from git+https://github.com/lachyn/revenant-rgb revenant-rgb

# permanent install – then the `revenant` command works anywhere
uv tool install git+https://github.com/lachyn/revenant-rgb
revenant static red
revenant                     # TUI

uv tool upgrade revenant-rgb      # update to the latest release
uv tool uninstall revenant-rgb    # uninstall
```

A specific version is chosen by appending `@<tag>` to the repository URL, e.g. `…/revenant-rgb@v0.1.0`.
`revenant --version` shows the installed version.

Debian/Ubuntu: if the automatic install fails, the `python3-venv` package is missing (`sudo apt install python3-venv`).

### Windows
Nothing else is needed, it works without administrator rights. If the original CZC software is running, close it
(the two programs could overwrite each other's settings).

### Linux
To control the keyboard without `sudo`, a udev rule has to be installed once. This does it:
```
python3 revenant.py setup
```
It asks for the administrator password (in the terminal via `sudo`, otherwise in a graphical dialog via `pkexec`),
installs `/etc/udev/rules.d/70-czc-revenant.rules` and checks that the keyboard can be opened. The rule grants access
only to the logged-in user and only to the `0C45:8006` device. When the rule is missing, the TUI and the web UI notice
and offer the setup themselves (a dialog or the `F2` key in the TUI, the *Set up access* button on the web – the
password is entered in the system dialog via `pkexec`, the web page never sees it). The same by hand:
```
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0c45", ATTRS{idProduct}=="8006", MODE="0660", TAG+="uaccess"' \
  | sudo tee /etc/udev/rules.d/70-czc-revenant.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```
On Linux the keyboard is controlled through `/dev/hidraw*`, so it keeps typing normally while being configured.

### macOS
No installation needed. On first use the system may ask you to allow **Input Monitoring**
for Terminal or whatever app you run revenant from: *System Settings → Privacy & Security → Input Monitoring*.
`python3 revenant.py setup --open` opens that pane and checks access to the keyboard.

### Optional: the `revenant` command anywhere
The easiest way is `uv tool install` (see above). Without uv:

PowerShell (`notepad $PROFILE`):
```powershell
function revenant { python C:\path\to\revenant\revenant.py @args }
```
bash / zsh (`~/.bashrc`, `~/.zshrc`):
```bash
alias revenant='python3 /path/to/revenant/revenant.py'
```
On Linux/macOS a symlink works too: `ln -s "$PWD/revenant.py" ~/.local/bin/revenant`.

## Quick start

```
python revenant.py static red                      # whole keyboard red
python revenant.py keys wasd=red --base 101010     # WASD red, the rest dimmed
python revenant.py remap caps=disable              # disable Caps Lock
python revenant.py status                          # what is set
python revenant.py                                 # no command = text UI in the terminal (TUI)
```

---

## TUI

```
python revenant.py          # or: python revenant.py tui
```

Works with mouse and keyboard. Every change goes to the keyboard right away; the profile changes only when you save it
(`Ctrl+S`, or *Save* on the Profiles tab). The title shows `• unsaved` while there are unsaved changes.

| Tab | What it does |
|---|---|
| **Key colours** | a clickable keyboard coloured by the current setup. Click keys (or a group `all`, `letters`, `numbers`, `fkeys`, `wasd`, `arrows`, `numpad`, `nav`, `mods`) and then a palette colour, or type `#RRGGBB`. The eyedropper picks a key's colour, brightness 0–16. |
| **Effects** | choose one of 19 effects, colour or rainbow, brightness, speed, direction → *Run effect* |
| **Key functions** | key + function type (default, disabled, other key, combination, media, mouse, macro) + parameter → *Assign*. The table lists all remaps; click a row to load it for editing. |
| **Macros** | macro list and step editor (one step per line, help below the editor) |
| **Game mode** | on/off switch + what to block (Alt+Tab, Alt+F4, Win) |
| **Profiles** | profile list with descriptions, *save*, *discard changes*, *save as new*, *load selected*, *new empty*, *delete* |

| Shortcut | Action |
|---|---|
| `F5` | re-send the current settings to the keyboard |
| `Ctrl+S` | save the current settings to the active profile |
| `Ctrl+R` | reload the current settings from disk (after a change from the command line) |
| `Ctrl+A` / `Esc` | select all keys / clear selection |
| `F2` | set up access to the keyboard (Linux: udev rule, macOS: Input Monitoring) |
| `Ctrl+L` | choose the language (system / English / Czech) |
| `Ctrl+Q` | quit |

The TUI needs a terminal with 24-bit colour: Windows Terminal, most terminals on Linux and macOS
(iTerm2, Terminal.app, GNOME Terminal, Konsole, kitty…). The old `cmd.exe` window (conhost) won't show the colours.

## Web UI

```
python revenant.py web                 # opens the browser at http://127.0.0.1:8462/
python revenant.py web --port 9000     # another port
python revenant.py web --no-browser    # only start the server (the address is printed)
```

On the left the **profiles**: the active one with its state (saved / unsaved changes) and *Save* / *Discard changes*,
the list (click a profile to load it), *Save as new* and *New empty*. On the right the **editor** of the current
settings: *Lighting* (custom colours or a hardware effect), *Key functions* (click a key on the keyboard),
*Macros* and *Game mode*. Works in light and dark mode and on narrow screens. Stop it with `Ctrl+C` in the terminal.

- Default port **8462** – free on stock Windows, macOS and Linux (doesn't clash with AirPlay on 5000/7000 or with
  dev servers on 8000/8080). If it is taken or reserved by Windows (Hyper-V/WSL), another free port is used automatically.
- The server listens **only on 127.0.0.1** – it is not reachable from other computers and the Windows/macOS firewall
  doesn't ask. Requests from other websites are rejected (checks of the `Host` header and a custom `X-Revenant` header).
- The keyboard status is shown top right (connected / not found / no access) and re-checked every 4 s – it only
  checks whether the keyboard is there and writes nothing to it. Unplugging and re-plugging the cable is detected.
- When the keyboard is connected but access is missing, a banner with a *Set up access* button appears.
- Changes go to the keyboard right away; with unsaved changes the top bar shows `• unsaved` with *Save* (to the
  active profile) and *Discard changes*. *Turn all off* asks for confirmation.

The frontend lives in `revenant_web/` – plain HTML, CSS and JavaScript, no build step. `app.js` carries JSDoc types
and can be type-checked with TypeScript: `npx -p typescript tsc -p revenant_web`.

---

## Command line

```
python revenant.py [-v] [-p PROFILE] <command> …
```

Without a command the TUI starts.

Every command that changes something changes the **current settings** and sends them to the keyboard; save them to
the profile with `profile save` (see [Profiles](#profiles)).

| Global option | Meaning |
|---|---|
| `-p PROFILE` | edit a saved profile file instead of the current settings – the keyboard doesn't change |
| `-v` | verbose output (opened device, checksums) |

### Overview and help
| Command | What it does |
|---|---|
| `status` | summary of the active profile (of another one with `-p`) |
| `--help`, `<command> --help` | help |
| `funcs` | syntax of key functions and macro steps |
| `keylist` | names of all keys and groups |
| `list` | effect names |
| `apply` | send the current settings to the keyboard again |
| `setup` | one-time system setup (Linux: udev rule) and a keyboard access check |
| `web` | web UI, see above |
| `lang [cs\|en\|auto]` | show or set the language |

### Lighting
```
python revenant.py static COLOR [-b BRIGHTNESS]
python revenant.py effect EFFECT [-c COLOR] [-b BRIGHTNESS] [-s SPEED] [-d DIRECTION]
python revenant.py keys KEY=COLOR … [--base COLOR] [-b BRIGHTNESS] [--clear]
python revenant.py off
```

- **Colour**: `RRGGBB` (`ff8800`, `#ff8800`) or a name – `red green blue white yellow cyan magenta orange purple pink off`
  (Czech names work too: `cervena zelena modra bila zluta fialova oranzova ruzova`).
- **Brightness** and **speed**: 0–16.
- **Direction**: `right` / `left` / `up` / `down`.
- `effect` without `-c` runs in rainbow colours.
- `keys` adds to the current colours, `--clear` turns everything off first, `--base` is the colour of keys without
  their own. Instead of a key you can name a group: `all letters numbers fkeys wasd arrows numpad nav mods`.

Effects: `static press-on press-off sparkle rain colors breathing spectrum center-wave vertical-wave
horizontal-wave rotating explosion start ripple snake pulse disco lines`

```
python revenant.py static red
python revenant.py effect breathing -c blue -s 6
python revenant.py effect horizontal-wave -d left -s 16
python revenant.py keys --clear letters=0000ff wasd=red arrows=green fkeys=yellow esc=white numpad=purple --base 101010
```

### Key functions
```
python revenant.py remap KEY=FUNCTION …       # set
python revenant.py remap KEY=default          # restore one key
python revenant.py remap                      # list
python revenant.py remap --clear              # everything back to default
```

| Function | Meaning |
|---|---|
| `default` | the key's default function |
| `disable` | the key does nothing |
| `key:esc` (or just `esc`) | acts as another key (`a`–`z`, `0`–`9`, `f1`–`f24`, `enter`, `space`, `lctrl`, `win`, `num5`… see `keylist`) |
| `combo:ctrl+shift+esc` | combination of up to 3 keys |
| `media:NAME` | `volup voldown mute play next prev stop mail calc mycomputer browser` |
| `mouse:NAME` | `left right middle back forward wheelup wheeldown` |
| `macro:NAME` | plays the macro once |
| `macro:NAME:repeat:N` | plays the macro N times (1–255) |
| `macro:NAME:toggle` | a press starts repeating, the next press stops it |

```
python revenant.py remap caps=disable f12=media:volup f11=media:voldown
python revenant.py remap pause=combo:ctrl+shift+esc menu=mouse:middle
```

### Macros
```
python revenant.py macro set NAME STEP STEP …
python revenant.py macro list | show NAME | delete NAME
```

| Step | Meaning |
|---|---|
| `a`, `enter`, `f5`, `esc` … | press and release a key |
| `text:Hello world!` | types text (capitals and `!@#$%^&*()_+{}|:"<>?~` via Shift) |
| `combo:ctrl+c` | key combination |
| `down:shift` / `up:shift` | press only / release only |
| `100ms` (or `delay:100`) | pause |
| `mouse:left` | mouse click; `mdown:left` / `mup:left` press / release only |

A 10 ms pause is inserted between steps automatically. Assign a macro to a key with `remap`:

```
python revenant.py macro set hello "text:Hello world!" enter
python revenant.py macro set copy combo:ctrl+c 50ms combo:alt+tab 100ms combo:ctrl+v
python revenant.py remap f1=macro:hello f2=macro:copy
```

A macro assigned to a key can't be deleted – change the key's function first. The keyboard holds up to 100 macros.

> Text is typed as key presses in the **US layout**. With another layout active (e.g. Czech or German), some characters
> come out different (`y`↔`z` swapped, digits as accented letters…). Macros are not suitable for accented characters.

### Game mode
```
python revenant.py gamemode on [--alt-tab] [--alt-f4] [--win]
python revenant.py gamemode off
```

### Profiles
```
python revenant.py profile list                 # * = active
python revenant.py profile show [NAME]
python revenant.py profile use NAME             # load into the current settings and send to the keyboard
python revenant.py profile save [NAME]          # save the current settings (to the active profile, or as NAME)
python revenant.py profile discard              # drop unsaved changes, back to the saved active profile
python revenant.py profile new NAME             # empty profile
python revenant.py profile copy SOURCE NEW
python revenant.py profile delete NAME          # the active one can't be deleted
python revenant.py profile path                 # where the files are
python revenant.py profile presets              # add missing sample profiles
```

## Language

The program speaks **English and Czech**. By default it follows the system language (Czech and Slovak systems get
Czech, everything else English). To choose explicitly:

```
python revenant.py lang cs        # cs | en | auto – saved, applies to the CLI, TUI and web UI
python revenant.py --lang en …    # just for this run
```

Also `REVENANT_LANG=cs`, `Ctrl+L` in the TUI and the language menu in the top right of the web UI.

**Translations** live in `revenant_i18n/<language>.json` as `{"English text": "translation"}` – the source strings in
the code are English (`tr("…")` in Python, `t("…")` in the web UI, `data-i18n` in the HTML). After changing a text
run `python tools/i18n_check.py`: it lists missing and unused translations and mismatched `{placeholders}`
(`--add` adds the missing ones marked `TODO`). A new language = a new `xx.json` plus an entry in `LANGUAGES` in
`revenant.py`.

---

## Profiles

A profile is a complete keyboard setup: lighting, key functions, macros and game mode, saved under a name.

- The **current settings** are what is on the keyboard now. The TUI, the web UI and the command line all edit them,
  and every change is sent to the keyboard right away – so you see what you are doing.
- The **active profile** is the one the current settings came from. It changes **only when you save**: `Ctrl+S` in
  the TUI, *Save* in the web UI, `revenant profile save`. *Save as new* / `profile save NAME` stores them under
  a new name. Until then the web UI and the TUI show `• unsaved`, and *Discard changes* / `profile discard` goes back
  to the saved profile – so experimenting can't spoil a profile.
- Clicking a profile (web), *Load selected* (TUI) or `profile use NAME` loads a profile into the current settings (unsaved changes are dropped).
- The first run installs the sample profiles below and starts with `default`.

Location: `~/.config/revenant/` (Windows: `C:\Users\<name>\.config\revenant\`), elsewhere via the `REVENANT_HOME` variable.

### Sample profiles
On first run the program copies these into the profile folder (`python revenant.py profile presets` adds any missing
ones later, without overwriting yours):

| Profile | What it is |
|---|---|
| `default` | calm static cyan |
| `monokai` | the Monokai palette in muted tones – letters, numbers, F-keys, modifiers and numpad each in their own colour |
| `monokai-vivid` | the same in full brightness |
| `nord` | the Nord palette – snow letters, frost modifiers, aurora F-keys, arrows and numpad |
| `ocean` | deep blue to aqua, left to right |
| `synthwave` | hot pink → purple → cyan, top to bottom |
| `sunset` | orange and amber with blue accents |
| `fps` | dark keyboard with WASD, action keys, weapon numbers and modifiers highlighted; game mode blocks the Windows key |
| `cs16` | Counter-Strike 1.6 – keys coloured by their default binds (movement, buy menu, grenades, radio…) |
| `rainbow-wave` | the hardware rainbow wave |
| `breathing` | the hardware breathing effect in purple |

The animated ones run inside the keyboard, so they cost nothing and write nothing while running.

```
~/.config/revenant/
├── active                 # name of the active profile
├── current.json           # the current settings (what is on the keyboard)
├── auto.json              # automatic switching rules
└── profiles/
    ├── default.json
    └── games.json
```

A profile is readable JSON and can be edited by hand (then `python revenant.py profile use NAME`):

```json
{
  "lighting": {
    "mode": "keys",
    "effect": "static", "color": "00aaff", "rainbow": false,
    "brightness": 16, "speed": 10, "direction": "right",
    "keys": { "w": "ff0000", "a": "ff0000", "s": "ff0000", "d": "ff0000" },
    "base": "101010", "key_brightness": 16
  },
  "remap": {
    "caps": "disable",
    "f1": "macro:hello",
    "f12": "media:volup"
  },
  "macros": {
    "hello": ["text:Hello world!", "enter"]
  },
  "gamemode": { "enabled": true, "alt_tab": false, "alt_f4": false, "win": true }
}
```

- `lighting.mode`: `"effect"` uses `effect/color/rainbow/brightness/speed/direction`,
  `"keys"` uses the key colours `keys` + `base` + `key_brightness`. Both sets are kept, so switching loses nothing.
- `remap` and `macros` use the same syntax as the command line.

Profiles are not synced between computers – to use them elsewhere, copy the `profiles/` folder.

## Automatic profile switching

```
python revenant.py auto [--interval 2]
```

The first run creates a sample `~/.config/revenant/auto.json`:

```json
{
  "default": "work",
  "rules": [
    { "process": "cs2.exe",     "profile": "games" },
    { "process": "notepad.exe", "profile": "writing" }
  ]
}
```

Every 2 s it checks the running processes: the first rule whose program is running decides the profile, otherwise
`default` is used. Switching loads the profile into the current settings, so unsaved changes are dropped. The file is re-read every time, so it can be edited while running. On Linux/macOS process names
have no `.exe`. Unplugging the keyboard doesn't stop it – it carries on once the keyboard is back.

Start at login: Windows – a shortcut to `pythonw revenant.py auto` in the `shell:startup` folder;
Linux – a systemd user service; macOS – a LaunchAgent.

## Using it as a library

```python
import revenant as rv

kb = rv.Revenant()
kb.set_effect("breathing", (0, 0, 255), rainbow=0, speed=8)
kb.set_keys({"wasd": (255, 0, 0), "esc": (255, 255, 255)}, base=(16, 16, 16))

kb.write_macros([rv.compile_macro(["text:Hello!", "enter"])])                 # macro no. 0
kb.write_keymap({rv.KEYS["f1"]: rv.encode_action("macro:x", {"x": 0}),
                 rv.KEYS["caps"]: rv.encode_action("disable")})
kb.set_gamemode(True, win=True)

prof = rv.load_profile("games")
rv.apply_profile(kb, prof)
```

`rv.Revenant()` raises `rv.RevenantNotFound` when no keyboard is connected and `rv.RevenantAccessError` when it is
connected but can't be opened (both subclass `rv.RevenantError`).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| *keyboard not found* | connect it with the USB cable, right switch on the bottom set to **Off** (a 2.4 GHz / Bluetooth connection is not enough) |
| *could not open the keyboard's control interface* | Linux: `revenant setup`. macOS: allow Input Monitoring. Windows: close the original CZC software. |
| *checksum does not match* | the data arrived corrupted – repeat the command; another USB port / no hub helps |
| the TUI is black and white | the terminal has no 24-bit colour – use Windows Terminal; make sure `NO_COLOR` isn't set |
| a macro types wrong characters | macros type in the US layout (see the note under macros) |
| the keyboard behaves oddly | factory reset: hold **Fn+Esc** for 3 s, then `python revenant.py apply` |


Useful shortcuts on the keyboard itself (from the CZC manual): Fn+Scroll lighting modes (also controls the side edge),
Fn+Pause colour, Fn+↑/↓ brightness, Fn+←/→ speed, Fn+PrtSc custom lighting, Fn+Win lock the Windows key,
Fn+A / Fn+S Windows / Mac mode, Fn+Esc (3 s) factory reset.

### Keyboard memory wear

**Every write to the keyboard is stored permanently** – even without the final `04 f0` command the setting survives
unplugging the cable. So every change of colour, effect, key function or profile rewrites the keyboard's flash memory,
which only tolerates a limited number of writes (typically tens of thousands for chips like this).

- Normal use (changing a colour, switching a profile, editing in the TUI) is fine – that's a handful of writes.
- **The driver is not suitable for animations, games or fast-changing effects** driven from the computer (e.g. music
  visualisation, a snake game on the keys) – at ~6 frames per second that would be thousands of writes in a few minutes.
- Use the built-in animations – the effects run inside the keyboard and write nothing (`effect snake`, `effect ripple`…).
- `auto` writes only when the profile changes, not on every check.

**The side light edge can't be controlled from the computer** – it doesn't react to any data sent by this driver
or by the original software; it is switched only with Fn+Scroll on the keyboard.

## What is verified

Verified on a real keyboard:
- static colour, brightness, breathing effect, horizontal wave in both directions
- per-key colours – the map of all 104 keys
- a text macro, media keys (volume), disabling a key, game mode (blocking Win)

Matches the data captured from the original software but not separately tested on the keyboard:
the other effects, up/down direction, mouse functions, `wheeldown`, the `toggle` macro mode, key order in `combo`.
The key function and macro tables generated by the driver are byte-for-byte identical to the original software.

Developed on Windows and Linux: on Linux, access via `/dev/hidraw*`, `revenant setup` and sending a whole profile
to the keyboard are verified (the keyboard confirmed every write with its checksum). On macOS nobody has tried it with
a real keyboard yet (it uses the cross-platform `hidapi`). The automated tests (protocol, profiles, command line,
web API, TUI, translations) run on Linux, Windows and macOS.

---

## Protocol

All communication goes through 64-byte HID **feature reports** (report ID 0) on **interface 0** (the keyboard one).
Every write follows the same sequence:

```
04 ab                      start session            → ack
<64 B of random data>
04 02                      query                    → ack
04 <op> 00 00 00 00 00 [n] start writing n packets  → ack
<n × 64 B of data>
04 02                      query → reply 04 02 00 01 [sum lo] [sum hi] = 16-bit sum of all data bytes
04 f0                      commit (lighting only)
```

After every `04 xx` command a feature report is read; the keyboard acknowledges with byte 4 = `01`.

Verified: data is stored permanently even without `04 f0` (the setting survives unplugging) – see
[memory wear](#keyboard-memory-wear).

| op | Content | Packets |
|---|---|---|
| `13` | **lighting** – 20 effect records (5 packets), 3 reserved, key colours 144 × `80 R G B` (9), active effect (1) | 18 |
| `11` | **key functions** – 160 × 4 B, index = the key's LED index, last 2 B `aa 55` | 10 |
| `15` | **macros** – 100 × u32 LE offset, then blocks `[count u16][6 B 00][events u32 …]`, last 2 B `aa 55` | ⌈length/64⌉ + 1 |
| `17` | **game mode** – `0a [enabled] [Alt+Tab] [Alt+F4] [Win] … aa 55` | 1 |

**Key index** = row × 18 + column in an 8 × 18 matrix (layout in `revenant.py`, `KEYS`).

**Effect record** (16 B):
```
[id] [R] [G] [B] 00 00 00 00 [rainbow 0/1] [brightness 0-16] [speed 0-16] [direction 0-3] 00 00 aa 55
```
id: `01` static … `13` lines, `80` custom key colours. Direction: 0 right, 1 left, 2 up, 3 down.

**Key function** (4 B):

| Bytes | Function |
|---|---|
| `00 00 00 00` | default |
| `01 01 [mask]` | mouse button (1 left, 2 right, 4 middle, 8 back, 16 forward) |
| `01 03 [01/ff]` | wheel up / down |
| `02 00 [code]` | key (HID usage) |
| `03 [lo] [hi]` | media (HID consumer usage, e.g. `ea 00` = volume −) |
| `05 03` | disabled |
| `06 [macro] [mode] [count]` | macro; mode 0 once, 1 N times, 2 toggle |
| `07 [k1] [k2] [k3]` | key combination |

**Macro event** (u32 LE) = `type << 24 | code << 16 | value`:
type `30` key, `10` mouse (code = button mask), `50` pause (value = ms, 24 bits); `| 80` = press, without it release.

## How the protocol was found

1. The original CZC software (V1.00.238n) talks through `SonixHidDll.dll` → `HidD_SetFeature` / `HidD_GetFeature`.
2. [`research/sniff.py`](https://github.com/lachyn/revenant-rgb/blob/main/research/sniff.py) attaches to the running CZC program with [Frida](https://frida.re)
   and logs every feature report (the program runs as administrator, so the sniffer has to as well).
3. The CZC program was driven automatically ([`research/`](https://github.com/lachyn/revenant-rgb/tree/main/research) – screenshots and clicking) and every action was
   timestamped; changes in the data were then matched to the actions.
4. The checksum in the reply to `04 02` confirmed that the keyboard accepted the data.
5. Hypotheses (key map, directions, effects) were verified on the keyboard.

The captured samples are in `research/` (`capture_*.bin`, `capture_static_b4.txt`) and the driver reproduces them byte for byte.

## Development

```
uv run --group dev pytest          # tests (no keyboard needed – a fake one is used)
python tools/i18n_check.py         # translations complete?
npx -p typescript tsc -p revenant_web   # type-check the web UI
```

The tests cover the protocol encoders against the captures in `research/` (key function and macro tables
byte for byte, lighting records and checksum), profiles and the sample profiles, the command line, the web API
including its security checks, the TUI (headless) and translations. They never write to a real keyboard.

## Project layout

```
revenant.py          the driver: protocol, profiles, command line, TUI and web UI server
                     (importable as a library; installs its dependencies on first run)
LICENSE              MIT
README.md            documentation in English (README.cs.md in Czech)
revenant_web/        web UI (index.html, style.css, app.js with JSDoc types, tsconfig.json for checking)
revenant_i18n/       translations (cs.json); source strings are English
revenant_profiles/   sample profiles installed on first run
pyproject.toml       the revenant-rgb package for uvx / uv tool install (commands revenant and revenant-rgb)
requirements.txt     hidapi, textual, psutil – for manual installation only
research/            protocol research: captures, the sniffer and the helpers used with it
  sniff.py           Frida sniffer for the original software → hidlog.txt
  capture_*          samples of the lighting, key function and macro tables (used by the tests)
  listen.py          listens to the keyboard's input reports
  clicker.ps1, act.ps1, shot.ps1   automated control of the CZC GUI program (Windows)
tests/               pytest suite (no keyboard needed)
tools/               development tools
  i18n_check.py      checks that every text has a translation
```

---

License: [MIT](https://github.com/lachyn/revenant-rgb/blob/main/LICENSE).

*Unofficial project, not affiliated with CZC.cz s.r.o. Use at your own risk – in the worst case
the Fn+Esc factory reset helps.*
