"""Turn a profile's lighting section into keyboard commands, plus animation generators."""
from __future__ import annotations

import colorsys
import math

from . import layout
from .device import K582
from .effects import BY_NAME, DIRECTION_VALUES
from .profiles import colors_to_list, hex_to_rgb, rgb_to_hex


def apply_lighting(dev: K582, lighting: dict):
    if lighting.get("kind") == "custom":
        dev.set_custom(colors_to_list(lighting.get("colors", {})),
                       brightness=lighting.get("brightness", 4))
        return
    eff = BY_NAME.get(lighting.get("effect", "static").lower())
    if eff is None:
        raise ValueError(f"unknown effect {lighting.get('effect')!r}")
    dev.set_mode(eff.value,
                 brightness=lighting.get("brightness", 4),
                 speed=lighting.get("speed", 3),
                 direction=DIRECTION_VALUES.get(lighting.get("direction", "Left"), 0),
                 random=bool(lighting.get("random")) and eff.random,
                 color=hex_to_rgb(lighting.get("color", "#ffffff")))


# -- animation generators (preview on screen; frames are plain per-key colour maps) ------
def _centers():
    return {k.led: (k.x + k.w / 2, k.y + k.h / 2) for k in layout.KEYS}


def _hsv(h, s=1.0, v=1.0):
    return rgb_to_hex(int(c * 255) for c in colorsys.hsv_to_rgb(h % 1.0, s, v))


def _lerp(a, b, t):
    ra, rb = hex_to_rgb(a), hex_to_rgb(b)
    return rgb_to_hex(int(x + (y - x) * t) for x, y in zip(ra, rb))


def gen_rainbow(frames=24, ms=80, **_):
    c = _centers()
    return [{"ms": ms, "colors": {str(l): _hsv(x / layout.WIDTH + f / frames) for l, (x, _y) in c.items()}}
            for f in range(frames)]


def gen_wave(color_a="#ff0000", color_b="#0000ff", frames=24, ms=80, **_):
    c = _centers()
    out = []
    for f in range(frames):
        cols = {}
        for l, (x, _y) in c.items():
            t = (math.sin(2 * math.pi * (x / layout.WIDTH - f / frames)) + 1) / 2
            cols[str(l)] = _lerp(color_a, color_b, t)
        out.append({"ms": ms, "colors": cols})
    return out


def gen_pulse(color_a="#00ffff", frames=20, ms=80, **_):
    leds = [k.led for k in layout.KEYS]
    out = []
    for f in range(frames):
        t = (1 - math.cos(2 * math.pi * f / frames)) / 2
        h = _lerp("#000000", color_a, 0.1 + 0.9 * t)
        out.append({"ms": ms, "colors": {str(l): h for l in leds}})
    return out


def gen_ripple(color_a="#ffffff", color_b="#000000", frames=20, ms=70, center="KEY_G", **_):
    c = _centers()
    cx, cy = c[layout.BY_CODE.get(center, layout.BY_CODE["KEY_G"]).led]
    maxd = math.hypot(layout.WIDTH, layout.HEIGHT)
    out = []
    for f in range(frames):
        r = maxd * f / frames
        cols = {}
        for l, (x, y) in c.items():
            d = abs(math.hypot(x - cx, y - cy) - r)
            cols[str(l)] = _lerp(color_b, color_a, max(0.0, 1 - d / 1.5))
        out.append({"ms": ms, "colors": cols})
    return out


GENERATORS = {"Rainbow sweep": gen_rainbow, "Two-colour wave": gen_wave,
              "Pulse": gen_pulse, "Ripple": gen_ripple}
