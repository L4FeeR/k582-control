"""Physical ANSI 104-key layout of the K582 with LED index and Linux key code for each key.

LED indices come from OpenRGB's EVision matrix map. Positions/sizes are in key units (1u).
If a key lights up in the wrong place on your board, fix its LED number here.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Key:
    label: str
    x: float
    y: float
    w: float
    h: float
    led: int
    code: str | None  # evdev name, None for Fn (handled inside the keyboard)


def _row(y, start_x, items):
    """items: (label, width, led, code) or a float = gap."""
    keys, x = [], start_x
    for it in items:
        if isinstance(it, (int, float)):
            x += it
            continue
        label, w, led, code, *h = it
        keys.append(Key(label, x, y, w, h[0] if h else 1, led, code))
        x += w
    return keys


def _letters(s, leds):
    return [(c, 1, led, f"KEY_{c}") for c, led in zip(s, leds)]


Y0, Y1 = 0, 1.25
KEYS: list[Key] = []
KEYS += _row(Y0, 0, [("Esc", 1, 0, "KEY_ESC"), 1,
                     *[(f"F{i}", 1, i, f"KEY_F{i}") for i in range(1, 5)], .5,
                     *[(f"F{i}", 1, i, f"KEY_F{i}") for i in range(5, 9)], .5,
                     *[(f"F{i}", 1, i, f"KEY_F{i}") for i in range(9, 13)], .25,
                     ("PrtSc", 1, 14, "KEY_SYSRQ"), ("ScrLk", 1, 15, "KEY_SCROLLLOCK"),
                     ("Pause", 1, 16, "KEY_PAUSE")])
KEYS += _row(Y1, 0, [("`", 1, 21, "KEY_GRAVE"),
                     *[(str(n % 10), 1, 21 + n, f"KEY_{n % 10}") for n in range(1, 11)],
                     ("-", 1, 32, "KEY_MINUS"), ("=", 1, 33, "KEY_EQUAL"),
                     ("Backspace", 2, 34, "KEY_BACKSPACE"), .25,
                     ("Ins", 1, 35, "KEY_INSERT"), ("Home", 1, 36, "KEY_HOME"),
                     ("PgUp", 1, 37, "KEY_PAGEUP"), .25,
                     ("Num", 1, 38, "KEY_NUMLOCK"), ("/", 1, 39, "KEY_KPSLASH"),
                     ("*", 1, 40, "KEY_KPASTERISK"), ("-", 1, 41, "KEY_KPMINUS")])
KEYS += _row(Y1 + 1, 0, [("Tab", 1.5, 42, "KEY_TAB"), *_letters("QWERTYUIOP", range(43, 53)),
                         ("[", 1, 53, "KEY_LEFTBRACE"), ("]", 1, 54, "KEY_RIGHTBRACE"),
                         ("\\", 1.5, 55, "KEY_BACKSLASH"), .25,
                         ("Del", 1, 56, "KEY_DELETE"), ("End", 1, 57, "KEY_END"),
                         ("PgDn", 1, 58, "KEY_PAGEDOWN"), .25,
                         ("7", 1, 59, "KEY_KP7"), ("8", 1, 60, "KEY_KP8"), ("9", 1, 61, "KEY_KP9"),
                         ("+", 1, 62, "KEY_KPPLUS", 2)])
KEYS += _row(Y1 + 2, 0, [("Caps", 1.75, 63, "KEY_CAPSLOCK"), *_letters("ASDFGHJKL", range(64, 73)),
                         (";", 1, 73, "KEY_SEMICOLON"), ("'", 1, 74, "KEY_APOSTROPHE"),
                         ("Enter", 2.25, 76, "KEY_ENTER"), 3.5,
                         ("4", 1, 80, "KEY_KP4"), ("5", 1, 81, "KEY_KP5"), ("6", 1, 82, "KEY_KP6")])
KEYS += _row(Y1 + 3, 0, [("Shift", 2.25, 84, "KEY_LEFTSHIFT"), *_letters("ZXCVBNM", range(86, 93)),
                         (",", 1, 93, "KEY_COMMA"), (".", 1, 94, "KEY_DOT"), ("/", 1, 95, "KEY_SLASH"),
                         ("Shift", 2.75, 97, "KEY_RIGHTSHIFT"), 1.25,
                         ("↑", 1, 99, "KEY_UP"), 1.25,
                         ("1", 1, 101, "KEY_KP1"), ("2", 1, 102, "KEY_KP2"), ("3", 1, 103, "KEY_KP3"),
                         ("Enter", 1, 104, "KEY_KPENTER", 2)])
KEYS += _row(Y1 + 4, 0, [("Ctrl", 1.25, 105, "KEY_LEFTCTRL"), ("Win", 1.25, 106, "KEY_LEFTMETA"),
                         ("Alt", 1.25, 107, "KEY_LEFTALT"), ("Space", 6.25, 108, "KEY_SPACE"),
                         ("Alt", 1.25, 109, "KEY_RIGHTALT"), ("Fn", 1.25, 110, None),
                         ("Menu", 1.25, 111, "KEY_COMPOSE"), ("Ctrl", 1.25, 113, "KEY_RIGHTCTRL"), .25,
                         ("←", 1, 119, "KEY_LEFT"), ("↓", 1, 120, "KEY_DOWN"), ("→", 1, 121, "KEY_RIGHT"), .25,
                         ("0", 2, 123, "KEY_KP0"), (".", 1, 124, "KEY_KPDOT")])

WIDTH = max(k.x + k.w for k in KEYS)
HEIGHT = max(k.y + k.h for k in KEYS)
BY_LED = {k.led: k for k in KEYS}
BY_CODE = {k.code: k for k in KEYS if k.code}

GROUPS = {
    "All": [k.led for k in KEYS],
    "Letters": [k.led for k in KEYS if len(k.label) == 1 and k.label.isalpha()],
    "WASD": [BY_CODE[c].led for c in ("KEY_W", "KEY_A", "KEY_S", "KEY_D")],
    "Arrows": [BY_CODE[c].led for c in ("KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT")],
    "F-row": [BY_CODE[f"KEY_F{i}"].led for i in range(1, 13)],
    "Numbers": [BY_CODE[f"KEY_{i}"].led for i in range(10)],
    "Numpad": [k.led for k in KEYS if (k.code or "").startswith("KEY_KP") or k.code == "KEY_NUMLOCK"],
    "Modifiers": [k.led for k in KEYS if k.label in ("Ctrl", "Shift", "Alt", "Win", "Fn", "Menu", "Caps", "Tab")],
}

# Extra remap targets that are not physical keys on the board
EXTRA_TARGETS = ["KEY_VOLUMEUP", "KEY_VOLUMEDOWN", "KEY_MUTE", "KEY_PLAYPAUSE", "KEY_NEXTSONG",
                 "KEY_PREVIOUSSONG", "KEY_STOPCD", "KEY_CALC", "KEY_MAIL", "KEY_HOMEPAGE",
                 "KEY_BRIGHTNESSUP", "KEY_BRIGHTNESSDOWN", "KEY_PRINT",
                 *[f"KEY_F{i}" for i in range(13, 25)]]

ALL_TARGETS = sorted({k.code for k in KEYS if k.code} | set(EXTRA_TARGETS))


def pretty(code: str) -> str:
    return code.removeprefix("KEY_").replace("_", " ").title() if code else "?"
