"""Software key remapper and macro engine for the K582.

Grabs the K582's keyboard input devices (so the original key presses don't reach apps),
and re-emits keys through a virtual uinput keyboard after applying the profile's remaps.

Safety: if the process exits for any reason the kernel releases the grab, and the keyboard
works normally again. Press  Left Ctrl + Right Ctrl + Backspace  to stop remapping instantly.
"""
from __future__ import annotations

import selectors
import shlex
import signal
import subprocess
import sys
import threading
import time

import evdev
from evdev import UInput, ecodes as e

from .device import PID, VID
from .profiles import load_macros, load_profile

PANIC = {e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL, e.KEY_BACKSPACE}
MODS = [e.KEY_LEFTCTRL, e.KEY_LEFTSHIFT, e.KEY_LEFTALT, e.KEY_LEFTMETA,
        e.KEY_RIGHTCTRL, e.KEY_RIGHTSHIFT, e.KEY_RIGHTALT, e.KEY_RIGHTMETA]

# US layout: character -> (key, needs shift)
_SHIFTED = dict(zip('~!@#$%^&*()_+{}|:"<>?', '`1234567890-=[]\\;\',./'))
_PLAIN = {"`": "GRAVE", "-": "MINUS", "=": "EQUAL", "[": "LEFTBRACE", "]": "RIGHTBRACE",
          "\\": "BACKSLASH", ";": "SEMICOLON", "'": "APOSTROPHE", ",": "COMMA", ".": "DOT",
          "/": "SLASH", " ": "SPACE", "\n": "ENTER", "\t": "TAB"}


def char_to_key(ch: str):
    shift = False
    if ch in _SHIFTED:
        ch, shift = _SHIFTED[ch], True
    elif ch.isalpha() and ch.isupper():
        ch, shift = ch.lower(), True
    name = _PLAIN.get(ch, ch.upper())
    code = getattr(e, f"KEY_{name}", None)
    return (code, shift) if code is not None else (None, False)


def code(name: str) -> int:
    c = e.ecodes.get(name)
    if c is None:
        raise ValueError(f"unknown key {name!r}")
    return c


def find_devices() -> list[evdev.InputDevice]:
    devs = []
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
        except OSError:
            continue
        caps = d.capabilities().get(e.EV_KEY, [])
        if d.info.vendor == VID and d.info.product == PID and caps and \
                (e.KEY_A in caps or e.KEY_VOLUMEUP in caps):
            devs.append(d)
        else:
            d.close()
    return devs


class Remapper:
    def __init__(self, profile: str):
        self.profile = load_profile(profile)
        self.macros = load_macros()
        self.remaps = {}
        for src, action in self.profile.get("remaps", {}).items():
            try:
                self.remaps[code(src)] = action
            except ValueError as err:
                print(f"skipping remap: {err}", file=sys.stderr)
        self.devices = find_devices()
        if not self.devices:
            raise SystemExit("K582 input device not found or no permission (see README, udev rule)")
        keys = set(range(e.KEY_ESC, e.KEY_MICMUTE + 1))
        self.ui = UInput({e.EV_KEY: sorted(keys)}, name="K582 Control virtual keyboard")
        self.out_lock = threading.Lock()
        self.down: set[int] = set()       # physical keys currently held
        self.held_out: dict[int, list[int]] = {}  # physical key -> output keys held for it
        self.running = True

    # -- output ---------------------------------------------------------------
    def emit(self, key: int, value: int):
        with self.out_lock:
            self.ui.write(e.EV_KEY, key, value)
            self.ui.syn()

    def tap(self, key: int, shift=False):
        if shift:
            self.emit(e.KEY_LEFTSHIFT, 1)
        self.emit(key, 1)
        self.emit(key, 0)
        if shift:
            self.emit(e.KEY_LEFTSHIFT, 0)

    def run_macro(self, name: str):
        steps = self.macros.get(name, {}).get("steps", [])
        held = []
        try:
            for s in steps:
                a = s.get("action")
                if a == "delay":
                    time.sleep(max(0, int(s.get("ms", 0))) / 1000)
                elif a == "text":
                    for ch in s.get("text", ""):
                        k, sh = char_to_key(ch)
                        if k is not None:
                            self.tap(k, sh)
                            time.sleep(0.004)
                elif a in ("tap", "down", "up"):
                    k = code(s["key"])
                    if a == "tap":
                        self.tap(k)
                    elif a == "down":
                        self.emit(k, 1)
                        held.append(k)
                    else:
                        self.emit(k, 0)
                        if k in held:
                            held.remove(k)
                time.sleep(0.002)
        except Exception as err:  # never leave keys stuck because of a bad macro
            print(f"macro {name!r} failed: {err}", file=sys.stderr)
        finally:
            for k in held:
                self.emit(k, 0)

    # -- input ----------------------------------------------------------------
    def handle(self, ev):
        k, v = ev.code, ev.value          # v: 1 down, 0 up, 2 repeat
        if v == 1:
            self.down.add(k)
            if PANIC <= self.down:
                print("panic combo pressed, stopping")
                self.running = False
                return
        elif v == 0:
            self.down.discard(k)

        action = self.remaps.get(k)
        if action is None:
            self.emit(k, v)
            return
        t = action.get("type")
        if t == "disabled":
            return
        if t == "key":
            self.emit(code(action["key"]), v)
        elif t == "combo":
            keys = [code(x) for x in action.get("keys", [])]
            if v == 1:
                for x in keys:
                    self.emit(x, 1)
                self.held_out[k] = keys
            elif v == 0:
                for x in reversed(self.held_out.pop(k, keys)):
                    self.emit(x, 0)
        elif v == 1 and t == "macro":
            threading.Thread(target=self.run_macro, args=(action.get("macro", ""),), daemon=True).start()
        elif v == 1 and t == "command":
            cmd = action.get("command", "").strip()
            if cmd:
                subprocess.Popen(shlex.split(cmd), start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(self):
        sel = selectors.DefaultSelector()
        # Wait until no key is held, otherwise grabbing would leave a key stuck down.
        deadline = time.time() + 3
        while any(d.active_keys() for d in self.devices) and time.time() < deadline:
            time.sleep(0.05)
        for d in self.devices:
            d.grab()
            sel.register(d, selectors.EVENT_READ)
        print(f"remapping {len(self.remaps)} keys on {', '.join(d.path for d in self.devices)}", flush=True)
        try:
            while self.running:
                for keyobj, _ in sel.select(timeout=0.5):
                    try:
                        for ev in keyobj.fileobj.read():
                            if ev.type == e.EV_KEY:
                                self.handle(ev)
                    except OSError:  # keyboard unplugged
                        self.running = False
        finally:
            for k in list(self.down):
                self.emit(k, 0)
            for d in self.devices:
                try:
                    d.ungrab()
                except OSError:
                    pass
            self.ui.close()


def main(profile: str):
    r = Remapper(profile)

    def stop(*_):
        r.running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    r.run()
