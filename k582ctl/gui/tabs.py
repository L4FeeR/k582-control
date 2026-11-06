"""The five tabs of the main window. Each edits app.profile and calls app.save()."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QSlider, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import layout, profiles
from ..effects import EFFECTS, BY_NAME
from ..lighting import GENERATORS, apply_lighting
from .widgets import ColorButton, KeyboardView

SWATCHES = ["#ff0000", "#ff6600", "#ffcc00", "#00ff00", "#00ffcc", "#0088ff", "#0000ff",
            "#8800ff", "#ff00ff", "#ffffff", "#000000"]

WEAR_NOTE = ("Each Apply is saved in the keyboard's memory, like the Windows app does. "
             "That's fine for normal use, so there's no live preview on the keyboard.")


def hint(text):
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setObjectName("hint")
    return lab


def slider(lo, hi, val):
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(val)
    s.setPageStep(1)
    s.setTickPosition(QSlider.TicksBelow)
    return s


class Palette(QWidget):
    """Brush colour button plus quick swatches."""

    def __init__(self, color="#ff0000"):
        super().__init__()
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.button = ColorButton(color)
        lay.addWidget(QLabel("Colour"), 0, 0)
        lay.addWidget(self.button, 0, 1, 1, 4)
        for i, h in enumerate(SWATCHES):
            b = QPushButton()
            b.setFixedSize(24, 24)
            b.setStyleSheet(f"background:{h}; border:1px solid #555; border-radius:12px;")
            b.clicked.connect(lambda _=False, h=h: self.button.set_color(h))
            lay.addWidget(b, 1 + i // 6, i % 6)

    def color(self):
        return self.button.color()


# ---------------------------------------------------------------------------------------------
class EffectsTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QHBoxLayout(self)
        self.list = QListWidget()
        for eff in EFFECTS:
            self.list.addItem(eff.name)
        self.list.setMaximumWidth(220)
        lay.addWidget(self.list)

        right = QVBoxLayout()
        box = QGroupBox("Effect settings")
        form = QFormLayout(box)
        self.color = ColorButton()
        self.random = QCheckBox("Random colours")
        self.brightness = slider(0, 4, 4)
        self.speed = slider(0, 5, 2)
        self.direction = QComboBox()
        form.addRow("Colour", self.color)
        form.addRow("", self.random)
        form.addRow("Brightness", self.brightness)
        form.addRow("Speed (slow → fast)", self.speed)
        form.addRow("Direction", self.direction)
        right.addWidget(box)
        self.apply_btn = QPushButton("Apply to keyboard")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self.apply)
        right.addWidget(self.apply_btn)
        right.addWidget(hint(WEAR_NOTE))
        right.addStretch()
        lay.addLayout(right, 1)
        self.list.currentTextChanged.connect(self._update_controls)

    def load(self):
        li = self.app.profile["lighting"]
        items = self.list.findItems(li.get("effect", "Static"), Qt.MatchExactly)
        self.list.setCurrentItem(items[0] if items else self.list.item(0))
        self.color.set_color(li.get("color", "#ff0000"))
        self.random.setChecked(bool(li.get("random")))
        self.brightness.setValue(li.get("brightness", 4))
        self.speed.setValue(5 - li.get("speed", 3))
        self._update_controls(self.list.currentItem().text())
        i = self.direction.findText(li.get("direction", "Left"))
        if i >= 0:
            self.direction.setCurrentIndex(i)

    def _update_controls(self, name):
        eff = BY_NAME.get(name.lower())
        if not eff:
            return
        self.color.setEnabled(eff.color)
        self.random.setEnabled(eff.random)
        self.speed.setEnabled(eff.speed)
        self.direction.clear()
        self.direction.addItems(eff.directions)
        self.direction.setEnabled(bool(eff.directions))

    def apply(self):
        li = self.app.profile["lighting"]
        li.update(kind="effect", effect=self.list.currentItem().text(), color=self.color.color(),
                  random=self.random.isChecked(), brightness=self.brightness.value(),
                  speed=5 - self.speed.value(), direction=self.direction.currentText() or "Left")
        self.app.save()
        lighting = copy.deepcopy(li)
        self.app.worker.submit(lambda dev: apply_lighting(dev, lighting), f"Applied {li['effect']}")


# ---------------------------------------------------------------------------------------------
class PainterTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.colors: dict[str, str] = {}
        lay = QHBoxLayout(self)
        self.kb = KeyboardView()
        self.kb.ledPressed.connect(self.paint)
        self.kb.ledDragged.connect(self.paint)
        lay.addWidget(self.kb, 1)

        side = QVBoxLayout()
        self.palette = Palette()
        side.addWidget(self.palette)
        self.eraser = QCheckBox("Eraser (paint black)")
        side.addWidget(self.eraser)
        grp = QGroupBox("Fill a group")
        g = QGridLayout(grp)
        for i, name in enumerate(layout.GROUPS):
            b = QPushButton(name)
            b.clicked.connect(lambda _=False, n=name: self.fill(layout.GROUPS[n]))
            g.addWidget(b, i // 2, i % 2)
        side.addWidget(grp)
        clear = QPushButton("Clear all")
        clear.clicked.connect(lambda: self.fill(layout.GROUPS["All"], "#000000"))
        side.addWidget(clear)
        self.brightness = slider(0, 4, 4)
        f = QFormLayout()
        f.addRow("Brightness", self.brightness)
        side.addLayout(f)
        apply_btn = QPushButton("Apply to keyboard")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self.apply)
        side.addWidget(apply_btn)
        side.addWidget(hint("Click or drag across keys to paint them. " + WEAR_NOTE))
        side.addStretch()
        lay.addLayout(side)

    def load(self):
        li = self.app.profile["lighting"]
        self.colors = dict(li.get("colors", {}))
        self.brightness.setValue(li.get("brightness", 4))
        self.kb.set_colors(self.colors)

    def brush(self):
        return "#000000" if self.eraser.isChecked() else self.palette.color()

    def paint(self, led):
        self.colors[str(led)] = self.brush()
        self.kb.set_colors(self.colors)

    def fill(self, leds, color=None):
        for led in leds:
            self.colors[str(led)] = color or self.brush()
        self.kb.set_colors(self.colors)

    def apply(self):
        li = self.app.profile["lighting"]
        li.update(kind="custom", colors=dict(self.colors), brightness=self.brightness.value())
        self.app.save()
        lighting = copy.deepcopy(li)
        self.app.worker.submit(lambda dev: apply_lighting(dev, lighting), "Applied per-key colours")


# ---------------------------------------------------------------------------------------------
class AnimationTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.name = None
        self.anim = {"frames": [], "loop": True}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.play_index = 0

        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        self.pick = QComboBox()
        self.pick.setMinimumWidth(200)
        self.pick.currentTextChanged.connect(self.open)
        top.addWidget(QLabel("Animation"))
        top.addWidget(self.pick)
        for text, fn in (("New", self.new), ("Rename", self.rename), ("Delete", self.delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            top.addWidget(b)
        top.addStretch()
        self.play_btn = QPushButton("▶ Play preview")
        self.play_btn.setObjectName("primary")
        self.play_btn.clicked.connect(self.toggle_play)
        top.addWidget(self.play_btn)
        outer.addLayout(top)

        mid = QHBoxLayout()
        frames_col = QVBoxLayout()
        self.frames = QListWidget()
        self.frames.setMaximumWidth(190)
        self.frames.currentRowChanged.connect(self.show_frame)
        frames_col.addWidget(self.frames)
        fb = QGridLayout()
        for i, (text, fn) in enumerate((("Add", self.add_frame), ("Duplicate", self.dup_frame),
                                        ("Delete", self.del_frame), ("Up", lambda: self.move(-1)),
                                        ("Down", lambda: self.move(1)))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            fb.addWidget(b, i // 2, i % 2)
        frames_col.addLayout(fb)
        dur = QFormLayout()
        self.ms = QSpinBox()
        self.ms.setRange(20, 10000)
        self.ms.setSingleStep(10)
        self.ms.setSuffix(" ms")
        self.ms.valueChanged.connect(self._set_ms)
        dur.addRow("Frame time", self.ms)
        self.loop = QCheckBox("Loop")
        self.loop.setChecked(True)
        self.loop.toggled.connect(lambda v: (self.anim.__setitem__("loop", v), self._save()))
        dur.addRow("", self.loop)
        frames_col.addLayout(dur)
        mid.addLayout(frames_col)

        self.kb = KeyboardView()
        self.kb.ledPressed.connect(self.paint)
        self.kb.ledDragged.connect(self.paint)
        mid.addWidget(self.kb, 1)

        side = QVBoxLayout()
        self.palette = Palette("#00ffcc")
        side.addWidget(self.palette)
        fill = QPushButton("Fill frame")
        fill.clicked.connect(self.fill_frame)
        side.addWidget(fill)
        gen = QGroupBox("Generate frames")
        gf = QFormLayout(gen)
        self.gen_kind = QComboBox()
        self.gen_kind.addItems(GENERATORS)
        self.gen_a = ColorButton("#ff0000")
        self.gen_b = ColorButton("#0000ff")
        self.gen_n = QSpinBox()
        self.gen_n.setRange(2, 120)
        self.gen_n.setValue(24)
        self.gen_ms = QSpinBox()
        self.gen_ms.setRange(20, 2000)
        self.gen_ms.setValue(80)
        self.gen_ms.setSuffix(" ms")
        gf.addRow("Style", self.gen_kind)
        gf.addRow("Colour A", self.gen_a)
        gf.addRow("Colour B", self.gen_b)
        gf.addRow("Frames", self.gen_n)
        gf.addRow("Frame time", self.gen_ms)
        gbtn = QPushButton("Generate (replaces frames)")
        gbtn.clicked.connect(self.generate)
        gf.addRow(gbtn)
        side.addWidget(gen)
        send = QPushButton("Send this frame to keyboard")
        send.clicked.connect(self.send_frame)
        side.addWidget(send)
        use = QPushButton("Use this frame in profile")
        use.clicked.connect(self.use_frame)
        side.addWidget(use)
        side.addWidget(hint("Animations play on screen only. Streaming them to the K582 would rewrite "
                            "its memory many times a second and wear it out."))
        side.addStretch()
        mid.addLayout(side)
        outer.addLayout(mid, 1)
        self.refresh_list()

    # -- file handling --
    def refresh_list(self, select=None):
        names = profiles.list_animations()
        if not names:
            profiles.save_animation("Rainbow", {"frames": GENERATORS["Rainbow sweep"](), "loop": True})
            names = ["Rainbow"]
        self.pick.blockSignals(True)
        self.pick.clear()
        self.pick.addItems(names)
        self.pick.blockSignals(False)
        self.pick.setCurrentText(select or self.name or names[0])
        self.open(self.pick.currentText())

    def open(self, name):
        if not name:
            return
        self.stop()
        self.name = name
        self.anim = profiles.load_animation(name)
        self.loop.blockSignals(True)
        self.loop.setChecked(self.anim.get("loop", True))
        self.loop.blockSignals(False)
        self._rebuild_frames(0)

    def _save(self):
        if self.name:
            profiles.save_animation(self.name, self.anim)

    def _ask(self, title, default=""):
        name, ok = QInputDialog.getText(self, title, "Name:", text=default)
        return name.strip() if ok and name.strip() else None

    def new(self):
        name = self._ask("New animation")
        if name:
            profiles.save_animation(name, {"frames": [{"ms": 200, "colors": {}}], "loop": True})
            self.refresh_list(name)

    def rename(self):
        name = self._ask("Rename animation", self.name)
        if name and name != self.name:
            profiles.save_animation(name, self.anim)
            profiles.delete_animation(self.name)
            self.name = name
            self.refresh_list(name)

    def delete(self):
        if self.name and QMessageBox.question(self, "Delete", f"Delete animation '{self.name}'?") \
                == QMessageBox.Yes:
            profiles.delete_animation(self.name)
            self.name = None
            self.refresh_list()

    # -- frames --
    def _rebuild_frames(self, row):
        self.frames.blockSignals(True)
        self.frames.clear()
        for i, fr in enumerate(self.anim["frames"]):
            self.frames.addItem(f"Frame {i + 1}  ·  {fr.get('ms', 100)} ms")
        self.frames.blockSignals(False)
        if self.anim["frames"]:
            self.frames.setCurrentRow(max(0, min(row, len(self.anim["frames"]) - 1)))
        else:
            self.kb.set_colors({})

    def cur(self):
        r = self.frames.currentRow()
        return self.anim["frames"][r] if 0 <= r < len(self.anim["frames"]) else None

    def show_frame(self, row):
        if 0 <= row < len(self.anim["frames"]):
            fr = self.anim["frames"][row]
            self.kb.set_colors(fr.get("colors", {}))
            self.ms.blockSignals(True)
            self.ms.setValue(fr.get("ms", 100))
            self.ms.blockSignals(False)

    def _set_ms(self, v):
        fr = self.cur()
        if fr:
            fr["ms"] = v
            self.frames.currentItem().setText(f"Frame {self.frames.currentRow() + 1}  ·  {v} ms")
            self._save()

    def add_frame(self):
        r = self.frames.currentRow() + 1
        self.anim["frames"].insert(r, {"ms": self.ms.value() or 200, "colors": {}})
        self._rebuild_frames(r)
        self._save()

    def dup_frame(self):
        fr = self.cur()
        if fr:
            r = self.frames.currentRow() + 1
            self.anim["frames"].insert(r, copy.deepcopy(fr))
            self._rebuild_frames(r)
            self._save()

    def del_frame(self):
        r = self.frames.currentRow()
        if 0 <= r < len(self.anim["frames"]):
            del self.anim["frames"][r]
            self._rebuild_frames(r)
            self._save()

    def move(self, d):
        r = self.frames.currentRow()
        f = self.anim["frames"]
        if 0 <= r < len(f) and 0 <= r + d < len(f):
            f[r], f[r + d] = f[r + d], f[r]
            self._rebuild_frames(r + d)
            self._save()

    def paint(self, led):
        fr = self.cur()
        if fr is None:
            self.add_frame()
            fr = self.cur()
        fr.setdefault("colors", {})[str(led)] = self.palette.color()
        self.kb.set_colors(fr["colors"])
        self._save()

    def fill_frame(self):
        fr = self.cur()
        if fr:
            fr["colors"] = {str(k.led): self.palette.color() for k in layout.KEYS}
            self.kb.set_colors(fr["colors"])
            self._save()

    def generate(self):
        fn = GENERATORS[self.gen_kind.currentText()]
        self.anim["frames"] = fn(color_a=self.gen_a.color(), color_b=self.gen_b.color(),
                                 frames=self.gen_n.value(), ms=self.gen_ms.value())
        self._rebuild_frames(0)
        self._save()

    # -- playback (screen only) --
    def toggle_play(self):
        if self.timer.isActive():
            self.stop()
        elif self.anim["frames"]:
            self.play_index = max(0, self.frames.currentRow())
            self.play_btn.setText("■ Stop")
            self._tick()

    def stop(self):
        self.timer.stop()
        self.play_btn.setText("▶ Play preview")

    def _tick(self):
        f = self.anim["frames"]
        if not f:
            return self.stop()
        if self.play_index >= len(f):
            if not self.anim.get("loop", True):
                return self.stop()
            self.play_index = 0
        fr = f[self.play_index]
        self.kb.set_colors(fr.get("colors", {}))
        self.timer.start(max(20, int(fr.get("ms", 100))))
        self.play_index += 1

    def _frame_lighting(self):
        fr = self.cur()
        return None if fr is None else {"kind": "custom", "colors": dict(fr.get("colors", {})),
                                        "brightness": self.app.profile["lighting"].get("brightness", 4)}

    def send_frame(self):
        li = self._frame_lighting()
        if li:
            self.app.worker.submit(lambda dev: apply_lighting(dev, li), "Sent frame to keyboard")

    def use_frame(self):
        li = self._frame_lighting()
        if li:
            self.app.profile["lighting"].update(li)
            self.app.save()
            self.app.reload_tabs()
            self.app.status("Frame saved as the profile's per-key lighting (Per-key tab)")


# ---------------------------------------------------------------------------------------------
ACTIONS = ["Default", "Disabled", "Another key", "Key combination", "Macro", "Run command"]
ACTION_TYPES = {"Disabled": "disabled", "Another key": "key", "Key combination": "combo",
                "Macro": "macro", "Run command": "command"}
TYPE_ACTIONS = {v: k for k, v in ACTION_TYPES.items()}


def key_combo():
    c = QComboBox()
    c.setEditable(True)
    for code in layout.ALL_TARGETS:
        c.addItem(layout.pretty(code), code)
    c.setInsertPolicy(QComboBox.NoInsert)
    return c


class RemapTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.sel = None
        outer = QVBoxLayout(self)
        status = QHBoxLayout()
        self.state = QLabel()
        status.addWidget(self.state, 1)
        for text, fn in (("Start remapper", self.app.remap_start), ("Stop", self.app.remap_stop)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            status.addWidget(b)
        outer.addLayout(status)
        outer.addWidget(hint("Remaps run in a small background program (it keeps running after you close "
                             "this window). Emergency stop: Left Ctrl + Right Ctrl + Backspace."))

        mid = QHBoxLayout()
        self.kb = KeyboardView()
        self.kb.ledPressed.connect(self.select)
        mid.addWidget(self.kb, 1)

        side = QVBoxLayout()
        box = QGroupBox("Selected key")
        f = QFormLayout(box)
        self.key_label = QLabel("Click a key")
        f.addRow("Key", self.key_label)
        self.action = QComboBox()
        self.action.addItems(ACTIONS)
        self.action.currentIndexChanged.connect(lambda i: self.stack.setCurrentIndex(i))
        f.addRow("Action", self.action)
        self.stack = QStackedWidget()
        self.stack.addWidget(QWidget())
        self.stack.addWidget(QLabel("Key does nothing"))
        self.target = key_combo()
        self.stack.addWidget(self.target)
        combo_w = QWidget()
        cl = QVBoxLayout(combo_w)
        cl.setContentsMargins(0, 0, 0, 0)
        mods = QHBoxLayout()
        self.mod_checks = {}
        for m, code in (("Ctrl", "KEY_LEFTCTRL"), ("Shift", "KEY_LEFTSHIFT"), ("Alt", "KEY_LEFTALT"),
                        ("Super", "KEY_LEFTMETA")):
            cb = QCheckBox(m)
            self.mod_checks[code] = cb
            mods.addWidget(cb)
        cl.addLayout(mods)
        self.combo_key = key_combo()
        cl.addWidget(self.combo_key)
        self.stack.addWidget(combo_w)
        self.macro_pick = QComboBox()
        self.stack.addWidget(self.macro_pick)
        self.command = QLineEdit()
        self.command.setPlaceholderText("e.g. konsole  or  spectacle -r")
        self.stack.addWidget(self.command)
        f.addRow(self.stack)
        row = QHBoxLayout()
        setb = QPushButton("Set")
        setb.setObjectName("primary")
        setb.clicked.connect(self.set_action)
        row.addWidget(setb)
        side.addWidget(box)
        side.addLayout(row)
        side.addWidget(MacroEditor(self))
        mid.addLayout(side)
        outer.addLayout(mid, 1)
        self.app.remap_changed.connect(self.update_state)

    def load(self):
        self.refresh_macros()
        badges = {}
        for src, a in self.app.profile.get("remaps", {}).items():
            k = layout.BY_CODE.get(src)
            if k:
                badges[k.led] = {"disabled": "✕", "key": layout.pretty(a.get("key", "")),
                                 "combo": "combo", "macro": "M", "command": "▶"}.get(a.get("type"), "?")
        self.kb.badges = badges
        self.kb.set_colors({str(k.led): "#3a3a46" for k in layout.KEYS if k.led in badges})
        self.update_state()
        if self.sel is not None:
            self.select(self.sel)

    def refresh_macros(self):
        cur = self.macro_pick.currentText()
        self.macro_pick.clear()
        self.macro_pick.addItems(sorted(profiles.load_macros()))
        self.macro_pick.setCurrentText(cur)

    def update_state(self):
        running = self.app.remap_running()
        n = len(self.app.profile.get("remaps", {}))
        self.state.setText(f"Remapper: <b>{'running' if running else 'stopped'}</b> · "
                           f"{n} remapped key{'s' if n != 1 else ''} in this profile")

    def select(self, led):
        k = layout.BY_LED[led]
        if not k.code:
            self.app.status("Fn is handled inside the keyboard and can't be remapped")
            return
        self.sel = led
        self.kb.selected = {led}
        self.kb.update()
        self.key_label.setText(f"<b>{k.label}</b>  ({k.code})")
        a = self.app.profile.get("remaps", {}).get(k.code)
        self.action.setCurrentText(TYPE_ACTIONS.get(a.get("type")) if a else "Default")
        if a:
            t = a.get("type")
            if t == "key":
                self.target.setCurrentIndex(max(0, self.target.findData(a.get("key"))))
            elif t == "combo":
                keys = a.get("keys", [])
                for code, cb in self.mod_checks.items():
                    cb.setChecked(code in keys)
                rest = [x for x in keys if x not in self.mod_checks]
                if rest:
                    self.combo_key.setCurrentIndex(max(0, self.combo_key.findData(rest[-1])))
            elif t == "macro":
                self.macro_pick.setCurrentText(a.get("macro", ""))
            elif t == "command":
                self.command.setText(a.get("command", ""))

    def set_action(self):
        if self.sel is None:
            return
        code = layout.BY_LED[self.sel].code
        choice = self.action.currentText()
        remaps = self.app.profile.setdefault("remaps", {})
        if choice == "Default":
            remaps.pop(code, None)
        else:
            t = ACTION_TYPES[choice]
            a = {"type": t}
            if t == "key":
                a["key"] = self.target.currentData()
            elif t == "combo":
                a["keys"] = [c for c, cb in self.mod_checks.items() if cb.isChecked()] + \
                            [self.combo_key.currentData()]
            elif t == "macro":
                if not self.macro_pick.currentText():
                    return self.app.status("Create a macro first (below)")
                a["macro"] = self.macro_pick.currentText()
            elif t == "command":
                a["command"] = self.command.text().strip()
            remaps[code] = a
        self.app.save()
        self.load()
        self.app.status("Saved. Restart the remapper to use the change." if self.app.remap_running()
                        else "Saved. Press Start remapper to use it.")


class MacroEditor(QGroupBox):
    def __init__(self, tab: RemapTab):
        super().__init__("Macros")
        self.tab = tab
        self.macros = profiles.load_macros()
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.pick = QComboBox()
        self.pick.currentTextChanged.connect(self.show_macro)
        top.addWidget(self.pick, 1)
        for text, fn in (("New", self.new), ("Delete", self.delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            top.addWidget(b)
        lay.addLayout(top)
        self.steps = QListWidget()
        self.steps.setSelectionMode(QAbstractItemView.SingleSelection)
        lay.addWidget(self.steps)
        add = QGridLayout()
        self.kind = QComboBox()
        self.kind.addItems(["Tap key", "Press key", "Release key", "Delay", "Type text"])
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.key = key_combo()
        self.ms = QSpinBox()
        self.ms.setRange(1, 60000)
        self.ms.setValue(50)
        self.ms.setSuffix(" ms")
        self.text = QLineEdit()
        self.text.setPlaceholderText("Text to type (US layout)")
        add.addWidget(self.kind, 0, 0)
        add.addWidget(self.key, 0, 1)
        add.addWidget(self.ms, 0, 1)
        add.addWidget(self.text, 0, 1)
        for i, (text, fn) in enumerate((("Add step", self.add_step), ("Remove", self.remove_step),
                                        ("Up", lambda: self.move(-1)), ("Down", lambda: self.move(1)))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            add.addWidget(b, 1 + i // 2, i % 2)
        lay.addLayout(add)
        self._kind_changed(0)
        self.refresh()

    def _kind_changed(self, i):
        self.key.setVisible(i <= 2)
        self.ms.setVisible(i == 3)
        self.text.setVisible(i == 4)

    def refresh(self, select=None):
        cur = select or self.pick.currentText()
        self.pick.blockSignals(True)
        self.pick.clear()
        self.pick.addItems(sorted(self.macros))
        self.pick.blockSignals(False)
        if cur:
            self.pick.setCurrentText(cur)
        self.show_macro(self.pick.currentText())
        self.tab.refresh_macros()

    def _save(self):
        profiles.save_macros(self.macros)

    def steps_of(self):
        return self.macros.get(self.pick.currentText(), {}).setdefault("steps", []) \
            if self.pick.currentText() else None

    def show_macro(self, name):
        self.steps.clear()
        for s in self.macros.get(name, {}).get("steps", []):
            a = s.get("action")
            txt = {"tap": f"Tap {layout.pretty(s.get('key', ''))}",
                   "down": f"Press {layout.pretty(s.get('key', ''))}",
                   "up": f"Release {layout.pretty(s.get('key', ''))}",
                   "delay": f"Wait {s.get('ms')} ms", "text": f"Type “{s.get('text', '')}”"}.get(a, a)
            self.steps.addItem(QListWidgetItem(txt))

    def new(self):
        name, ok = QInputDialog.getText(self, "New macro", "Name:")
        if ok and name.strip():
            self.macros.setdefault(name.strip(), {"steps": []})
            self._save()
            self.refresh(name.strip())

    def delete(self):
        name = self.pick.currentText()
        if name and QMessageBox.question(self, "Delete", f"Delete macro '{name}'?") == QMessageBox.Yes:
            self.macros.pop(name, None)
            self._save()
            self.refresh("")

    def add_step(self):
        steps = self.steps_of()
        if steps is None:
            return self.tab.app.status("Create a macro first")
        i = self.kind.currentIndex()
        step = [{"action": "tap", "key": self.key.currentData()},
                {"action": "down", "key": self.key.currentData()},
                {"action": "up", "key": self.key.currentData()},
                {"action": "delay", "ms": self.ms.value()},
                {"action": "text", "text": self.text.text()}][i]
        steps.append(step)
        self._save()
        self.show_macro(self.pick.currentText())
        self.steps.setCurrentRow(len(steps) - 1)

    def remove_step(self):
        steps, r = self.steps_of(), self.steps.currentRow()
        if steps is not None and 0 <= r < len(steps):
            del steps[r]
            self._save()
            self.show_macro(self.pick.currentText())

    def move(self, d):
        steps, r = self.steps_of(), self.steps.currentRow()
        if steps is not None and 0 <= r < len(steps) and 0 <= r + d < len(steps):
            steps[r], steps[r + d] = steps[r + d], steps[r]
            self._save()
            self.show_macro(self.pick.currentText())
            self.steps.setCurrentRow(r + d)


# ---------------------------------------------------------------------------------------------
class ProfilesTab(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        lay = QHBoxLayout(self)
        self.list = QListWidget()
        self.list.setMaximumWidth(260)
        self.list.itemDoubleClicked.connect(lambda it: self.app.switch_profile(it.data(Qt.UserRole)))
        lay.addWidget(self.list)
        side = QVBoxLayout()
        for text, fn in (("Switch to selected", lambda: self._sel() and self.app.switch_profile(self._sel())),
                         ("New", self.new), ("Duplicate", self.dup), ("Rename", self.rename),
                         ("Delete", self.delete), ("Set as default", self.set_default)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            side.addWidget(b)
        apply_btn = QPushButton("Apply current profile to keyboard")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self.app.apply_profile)
        side.addWidget(apply_btn)
        self.autostart = QCheckBox("At login: apply the default profile and start its remapper")
        self.autostart.toggled.connect(self.app.set_autostart)
        side.addWidget(self.autostart)
        side.addWidget(hint("A profile holds lighting (an effect or per-key colours) and key remaps. "
                            "The default profile is the one used at login."))
        side.addStretch()
        lay.addLayout(side, 1)

    def _sel(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def load(self):
        self.list.clear()
        default = profiles.default_profile()
        for n in profiles.list_profiles():
            label = n + ("   ★ default" if n == default else "") + ("   (current)" if n == self.app.name else "")
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, n)
            self.list.addItem(it)
            if n == self.app.name:
                self.list.setCurrentItem(it)
        self.autostart.blockSignals(True)
        self.autostart.setChecked(self.app.autostart_enabled())
        self.autostart.blockSignals(False)

    def _ask(self, title, default=""):
        name, ok = QInputDialog.getText(self, title, "Profile name:", text=default)
        name = name.strip()
        if not ok or not name:
            return None
        if name in profiles.list_profiles():
            QMessageBox.warning(self, title, f"A profile named '{name}' already exists.")
            return None
        return name

    def new(self):
        name = self._ask("New profile")
        if name:
            profiles.save_profile(name, profiles.DEFAULT_PROFILE)
            self.app.switch_profile(name)

    def dup(self):
        src = self._sel()
        name = src and self._ask("Duplicate profile", f"{src} copy")
        if name:
            profiles.save_profile(name, profiles.load_profile(src))
            self.app.switch_profile(name)

    def rename(self):
        src = self._sel()
        name = src and self._ask("Rename profile", src)
        if name:
            profiles.rename_profile(src, name)
            self.app.switch_profile(name if src == self.app.name else self.app.name)

    def delete(self):
        src = self._sel()
        if not src:
            return
        if len(profiles.list_profiles()) == 1:
            return self.app.status("You need at least one profile")
        if QMessageBox.question(self, "Delete", f"Delete profile '{src}'?") == QMessageBox.Yes:
            profiles.delete_profile(src)
            self.app.switch_profile(profiles.default_profile() if src == self.app.name else self.app.name)

    def set_default(self):
        src = self._sel()
        if src:
            s = profiles.load_settings()
            s["default_profile"] = src
            profiles.save_settings(s)
            self.load()
