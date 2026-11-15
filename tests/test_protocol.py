"""Protocol encoding, checked against data captured from the original CZC software (research/)."""
import argparse

import pytest

from conftest import ROOT, rv

RESEARCH = ROOT / "research"
needs_captures = pytest.mark.skipif(not RESEARCH.is_dir(), reason="research/ captures are only in the git repository")


# ---------------------------------------------------------------- captures

@needs_captures
def test_keymap_matches_capture():
    """key function table with Caps Lock disabled, byte for byte"""
    capture = (RESEARCH / "capture_keymap_caps_disabled.bin").read_bytes()
    packets = rv.build_keymap({rv.KEYS["caps"]: rv.encode_action("disable")})
    assert len(packets) == 10
    assert b"".join(packets) == capture


def _macro_events(capture, slot):
    """events of macro `slot` from a captured macro table"""
    offset = int.from_bytes(capture[slot * 4: slot * 4 + 4], "little")
    count = int.from_bytes(capture[offset: offset + 2], "little")
    start = offset + 8
    return [int.from_bytes(capture[start + 4 * i: start + 4 * i + 4], "little") for i in range(count)]


@needs_captures
@pytest.mark.parametrize("name, macros", [("capture_macro_m1.bin", 1), ("capture_macro_m1m2.bin", 2)])
def test_macro_table_matches_capture(name, macros):
    """the captured macros were recorded with real pauses, so the table is rebuilt from the same events:
    this checks the layout (offset table, counts, padding, packet count, aa 55) byte for byte"""
    capture = (RESEARCH / name).read_bytes()
    events = [_macro_events(capture, i) for i in range(macros)]
    assert all(events)
    assert b"".join(rv.build_macros(events)) == capture


def _captured_lighting():
    """the 18 data packets of the captured lighting write and the keyboard's checksum reply"""
    rows = []
    for line in (RESEARCH / "capture_static_b4.txt").read_text().splitlines():
        rows.append(bytes.fromhex("".join(line.split()[3:])))
    start = next(i for i, r in enumerate(rows) if r[1:3] == b"\x04\x13")       # 04 13 = begin lighting write
    data = [r[1:] for r in rows[start + 2: start + 2 + 18]]                    # skip the ack, drop report id
    reply = next(r for r in rows[start + 20:] if r[1:3] == b"\x04\x02" and r[4] == 1)
    return data, reply


@needs_captures
def test_captured_lighting_checksum():
    data, reply = _captured_lighting()
    assert sum(sum(p) for p in data) & 0xFFFF == reply[5] | reply[6] << 8


@needs_captures
def test_lighting_table_matches_capture():
    """static 5affff, brightness 4: active record, reserved packets, per-key table and active packet.
    (The other effect records hold whatever the original software had set before, so they are not compared.)"""
    data, _ = _captured_lighting()
    table = rv.build_table(rv.record(rv.EFFECTS["static"], (0x5A, 0xFF, 0xFF), rainbow=0, brightness=4, speed=12))
    assert len(table) == 18 and all(len(p) == 64 for p in table)
    assert table[0][:16] == data[0][:16]
    assert table[5:17] == data[5:17]
    assert table[17] == data[17]


# ---------------------------------------------------------------- encoders

@pytest.mark.parametrize("spec, expected", [
    ("default", "00000000"),
    ("disable", "05030000"),
    ("key:esc", "02002900"),
    ("esc", "02002900"),
    ("key:f13", "02006800"),
    ("combo:ctrl+shift+esc", "07e0e129"),
    ("media:voldown", "03ea0000"),
    ("media:calc", "03920100"),
    ("mouse:right", "01010200"),
    ("mouse:wheelup", "01030100"),
    ("mouse:wheeldown", "0103ff00"),
    ("macro:m", "06030000"),
    ("macro:m:repeat:5", "06030105"),
    ("macro:m:toggle", "06030200"),
])
def test_encode_action(spec, expected):
    assert rv.encode_action(spec, {"m": 3}).hex() == expected


@pytest.mark.parametrize("spec", ["combo:a+b+c+d", "macro:missing", "media:nope", "mouse:nope", "nonsense", "key:nope"])
def test_encode_action_rejects(spec):
    with pytest.raises(ValueError):
        rv.encode_action(spec, {"m": 0})


def test_compile_macro_text_uses_shift_for_capitals():
    key = lambda code, down: ((0xB0 if down else 0x30) << 24) | (code << 16)
    gap = 0x50000000 | 10
    assert rv.compile_macro(["text:A"]) == [key(0xE1, True), gap, key(0x04, True), gap, key(0x04, False), gap,
                                            key(0xE1, False), gap]


def test_compile_macro_steps():
    assert rv.compile_macro(["50ms"]) == [0x50000000 | 50]
    assert rv.compile_macro(["delay:7"]) == [0x50000000 | 7]
    assert rv.compile_macro(["mouse:left"]) == [0x90010000, 0x5000000A, 0x10010000, 0x5000000A]
    assert len(rv.compile_macro(["combo:ctrl+c"])) == 8
    with pytest.raises(ValueError):
        rv.compile_macro(["nope"])


def test_build_macros_limit():
    with pytest.raises(ValueError):
        rv.build_macros([[0]] * 101)


def test_record_layout():
    r = rv.record(rv.EFFECTS["breathing"], (1, 2, 3), rainbow=0, brightness=9, speed=5, direction=2)
    assert r.hex() == "07010203000000000009050200" + "00aa55"


def test_parse_color_and_direction():
    assert rv.parse_color("red") == (255, 0, 0)
    assert rv.parse_color("#00ff80") == (0, 255, 128)
    assert rv.parse_color("modra") == (0, 0, 255)
    with pytest.raises(argparse.ArgumentTypeError):
        rv.parse_color("12345")
    assert rv.parse_direction("down") == 3 and rv.parse_direction("doleva") == 1 and rv.parse_direction("2") == 2
    with pytest.raises(argparse.ArgumentTypeError):
        rv.parse_direction("sideways")


def test_key_map():
    assert len(rv.KEYS) == 104
    assert rv.KEYS["esc"] == 1 and rv.KEYS["a"] == 3 * 18 + 2
    assert sorted(rv.resolve_keys("wasd")) == sorted(rv.KEYS[k] for k in "wasd")
    with pytest.raises(KeyError):
        rv.resolve_keys("nope")
