"""Profiles, macros and animations, stored as JSON under ~/.config/k582-control/.

Profile:
  {
    "lighting": {"kind": "effect" | "custom",
                 "effect": "Static", "color": "#ff0000", "random": false,
                 "brightness": 4, "speed": 3, "direction": "Left",
                 "colors": {"<led>": "#rrggbb", ...}},          # used when kind == custom
    "remaps": {"KEY_CAPSLOCK": {"type": "key", "key": "KEY_ESC"},
               "KEY_F1":       {"type": "combo", "keys": ["KEY_LEFTCTRL", "KEY_C"]},
               "KEY_F2":       {"type": "macro", "macro": "greeting"},
               "KEY_F3":       {"type": "command", "command": "konsole"},
               "KEY_INSERT":   {"type": "disabled"}}
  }

Macro: {"steps": [{"action": "tap"|"down"|"up", "key": "KEY_A"},
                  {"action": "delay", "ms": 50}, {"action": "text", "text": "hello"}]}

Animation: {"frames": [{"ms": 200, "colors": {"<led>": "#rrggbb"}}], "loop": true}
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "k582-control"
PROFILES = CONFIG / "profiles"
MACROS = CONFIG / "macros.json"
ANIMATIONS = CONFIG / "animations"
SETTINGS = CONFIG / "settings.json"

DEFAULT_PROFILE = {
    "lighting": {"kind": "effect", "effect": "Static", "color": "#ff0000", "random": False,
                 "brightness": 4, "speed": 3, "direction": "Left", "colors": {}},
    "remaps": {},
}


def _safe(name: str) -> str:
    name = re.sub(r"[^\w\- ]", "", name).strip()
    if not name:
        raise ValueError("name must contain letters or numbers")
    return name


def _read(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


# -- profiles -------------------------------------------------------------------
def list_profiles() -> list[str]:
    PROFILES.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in PROFILES.glob("*.json"))
    if not names:
        save_profile("Default", DEFAULT_PROFILE)
        names = ["Default"]
    return names


def load_profile(name: str) -> dict:
    data = _read(PROFILES / f"{_safe(name)}.json", None)
    if data is None:
        raise FileNotFoundError(f"no profile named {name!r}")
    merged = json.loads(json.dumps(DEFAULT_PROFILE))
    merged["lighting"].update(data.get("lighting", {}))
    merged["remaps"] = data.get("remaps", {})
    return merged


def save_profile(name: str, data: dict):
    _write(PROFILES / f"{_safe(name)}.json", data)


def delete_profile(name: str):
    (PROFILES / f"{_safe(name)}.json").unlink(missing_ok=True)


def rename_profile(old: str, new: str):
    (PROFILES / f"{_safe(old)}.json").rename(PROFILES / f"{_safe(new)}.json")
    s = load_settings()
    if s.get("default_profile") == old:
        s["default_profile"] = new
        save_settings(s)


# -- settings -------------------------------------------------------------------
def load_settings() -> dict:
    return _read(SETTINGS, {})


def save_settings(s: dict):
    _write(SETTINGS, s)


def default_profile() -> str:
    names = list_profiles()
    d = load_settings().get("default_profile")
    return d if d in names else names[0]


# -- macros ---------------------------------------------------------------------
def load_macros() -> dict:
    return _read(MACROS, {})


def save_macros(m: dict):
    _write(MACROS, m)


# -- animations -----------------------------------------------------------------
def list_animations() -> list[str]:
    ANIMATIONS.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in ANIMATIONS.glob("*.json"))


def load_animation(name: str) -> dict:
    return _read(ANIMATIONS / f"{_safe(name)}.json", {"frames": [], "loop": True})


def save_animation(name: str, data: dict):
    _write(ANIMATIONS / f"{_safe(name)}.json", data)


def delete_animation(name: str):
    (ANIMATIONS / f"{_safe(name)}.json").unlink(missing_ok=True)


# -- helpers --------------------------------------------------------------------
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(c) -> str:
    return "#%02x%02x%02x" % tuple(c)


def colors_to_list(colors: dict, n: int = 126) -> list[tuple[int, int, int]]:
    out = [(0, 0, 0)] * n
    for led, h in colors.items():
        i = int(led)
        if 0 <= i < n:
            out[i] = hex_to_rgb(h)
    return out
