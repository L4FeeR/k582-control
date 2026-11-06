"""Main window of K582 Control."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel, QMainWindow,
                               QStatusBar, QTabWidget, QVBoxLayout, QWidget)

from .. import profiles
from ..lighting import apply_lighting
from .tabs import AnimationTab, EffectsTab, PainterTab, ProfilesTab, RemapTab
from .widgets import DeviceWorker

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "k582ctl.sh"
PIDFILE = profiles.CONFIG / "remap.pid"
LOGFILE = profiles.CONFIG / "remap.log"
AUTOSTART = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "k582-control.desktop"

STYLE = """
QWidget { background:#16161a; color:#e6e6ea; font-size:10.5pt; }
QTabWidget::pane { border:1px solid #2c2c33; border-radius:6px; top:-1px; }
QTabBar::tab { background:#1e1e24; padding:8px 18px; border:1px solid #2c2c33; border-bottom:none;
               border-top-left-radius:6px; border-top-right-radius:6px; margin-right:2px; }
QTabBar::tab:selected { background:#26262e; color:#ff4d4d; }
QPushButton { background:#26262e; border:1px solid #3a3a44; border-radius:5px; padding:6px 12px; }
QPushButton:hover { border-color:#ff4d4d; }
QPushButton#primary { background:#c81e1e; border-color:#e03030; color:white; font-weight:bold; }
QPushButton#primary:hover { background:#e02828; }
QGroupBox { border:1px solid #2c2c33; border-radius:6px; margin-top:12px; padding-top:8px; }
QGroupBox::title { subcontrol-origin:margin; left:10px; color:#ff6b6b; }
QListWidget, QComboBox, QLineEdit, QSpinBox { background:#1e1e24; border:1px solid #33333c;
               border-radius:4px; padding:3px; }
QListWidget::item:selected { background:#c81e1e; color:white; }
QSlider::groove:horizontal { height:6px; background:#2c2c33; border-radius:3px; }
QSlider::handle:horizontal { background:#ff4d4d; width:14px; margin:-5px 0; border-radius:7px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #6a6a76; border-radius:3px;
               background:#1e1e24; }
QCheckBox::indicator:checked { background:#c81e1e; border-color:#ff4d4d; }
QCheckBox:disabled, QLabel:disabled { color:#5a5a64; }
QLabel#hint { color:#8d8d98; font-size:9pt; }
QLabel#title { font-size:15pt; font-weight:bold; color:#ff4d4d; }
"""


class MainWindow(QMainWindow):
    remap_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("K582 Control")
        self.resize(1320, 640)
        self.worker = DeviceWorker()
        self.worker.finished.connect(self.status)
        self.worker.failed.connect(lambda m: self.status(f"⚠ Keyboard error: {m}", 10000))
        self.name = profiles.default_profile()
        self.profile = profiles.load_profile(self.name)

        central = QWidget()
        lay = QVBoxLayout(central)
        top = QHBoxLayout()
        title = QLabel("K582 Control")
        title.setObjectName("title")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("Profile"))
        self.picker = QComboBox()
        self.picker.setMinimumWidth(200)
        self.picker.currentTextChanged.connect(lambda n: n and n != self.name and self.switch_profile(n))
        top.addWidget(self.picker)
        lay.addLayout(top)

        self.tabs = QTabWidget()
        self.effects = EffectsTab(self)
        self.painter = PainterTab(self)
        self.animation = AnimationTab(self)
        self.remap = RemapTab(self)
        self.profiles_tab = ProfilesTab(self)
        for w, n in ((self.effects, "Effects"), (self.painter, "Per-key"), (self.animation, "Animations"),
                     (self.remap, "Remap && Macros"), (self.profiles_tab, "Profiles")):
            self.tabs.addTab(w, n)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.reload_tabs()
        self._poll = QTimer(self)
        self._poll.timeout.connect(self.remap_changed.emit)
        self._poll.start(2000)

    # -- profile state --
    def status(self, msg, ms=4000):
        self.statusBar().showMessage(msg, ms)

    def save(self):
        profiles.save_profile(self.name, self.profile)

    def reload_tabs(self):
        self.picker.blockSignals(True)
        self.picker.clear()
        self.picker.addItems(profiles.list_profiles())
        self.picker.setCurrentText(self.name)
        self.picker.blockSignals(False)
        for t in (self.effects, self.painter, self.remap, self.profiles_tab):
            t.load()

    def switch_profile(self, name):
        self.name = name
        self.profile = profiles.load_profile(name)
        self.reload_tabs()
        self.status(f"Switched to profile '{name}'. Press Apply to send its lighting.")

    def apply_profile(self):
        li = dict(self.profile["lighting"])
        self.worker.submit(lambda dev: apply_lighting(dev, li), f"Applied profile '{self.name}'")
        if self.remap_running():
            self.remap_start()

    # -- remapper process --
    def _pid(self):
        try:
            pid = int(PIDFILE.read_text())
            if "k582ctl" in Path(f"/proc/{pid}/cmdline").read_text():
                return pid
        except (OSError, ValueError):
            pass
        return None

    def remap_running(self):
        return self._pid() is not None

    def remap_stop(self):
        pid = self._pid()
        if pid:
            os.kill(pid, signal.SIGTERM)
        PIDFILE.unlink(missing_ok=True)
        QTimer.singleShot(400, self.remap_changed.emit)
        self.status("Remapper stopped")

    def remap_start(self):
        self.remap_stop()
        if not self.profile.get("remaps"):
            return self.status("This profile has no remaps yet")
        try:
            import evdev  # noqa: F401
        except ImportError:
            return self.status("⚠ python-evdev is not installed (sudo pacman -S python-evdev)", 10000)
        profiles.CONFIG.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        log = open(LOGFILE, "w")
        p = subprocess.Popen([sys.executable, "-m", "k582ctl", "remap", self.name], env=env,
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        PIDFILE.write_text(str(p.pid))
        QTimer.singleShot(1500, lambda: self._check_started(p))

    def _check_started(self, p):
        if p.poll() is not None:
            msg = LOGFILE.read_text().strip().splitlines()
            self.status("⚠ Remapper stopped: " + (msg[-1] if msg else "unknown error"), 12000)
            PIDFILE.unlink(missing_ok=True)
        else:
            self.status(f"Remapper running for '{self.name}'")
        self.remap_changed.emit()

    # -- autostart --
    def autostart_enabled(self):
        return AUTOSTART.exists()

    def set_autostart(self, on):
        if on:
            AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART.write_text(f"[Desktop Entry]\nType=Application\nName=K582 Control (login)\n"
                                 f"Exec=\"{LAUNCHER}\" login\nX-GNOME-Autostart-enabled=true\n"
                                 f"NoDisplay=true\n")
            self.status("Default profile will be applied at every login")
        else:
            AUTOSTART.unlink(missing_ok=True)
            self.status("Login autostart removed")

    def closeEvent(self, ev):
        self.worker.stop()
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("K582 Control")
    app.setDesktopFileName("k582-control")
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#16161a"))
    pal.setColor(QPalette.Base, QColor("#1e1e24"))
    pal.setColor(QPalette.Text, QColor("#e6e6ea"))
    pal.setColor(QPalette.WindowText, QColor("#e6e6ea"))
    pal.setColor(QPalette.Button, QColor("#26262e"))
    pal.setColor(QPalette.ButtonText, QColor("#e6e6ea"))
    pal.setColor(QPalette.Highlight, QColor("#c81e1e"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon.fromTheme("input-keyboard"))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
