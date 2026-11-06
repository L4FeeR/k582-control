"""Shared widgets: the on-screen keyboard, colour button, background device worker."""
from __future__ import annotations

import queue
import traceback

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QColorDialog, QPushButton, QSizePolicy, QWidget

from .. import layout


class KeyboardView(QWidget):
    """Draws the K582 layout. Emits ledPressed on click and ledDragged while dragging."""
    ledPressed = Signal(int)
    ledDragged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.colors: dict[int, QColor] = {}
        self.badges: dict[int, str] = {}
        self.selected: set[int] = set()
        self._drag_last = None
        self.setMinimumSize(640, 230)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(False)

    def set_colors(self, colors: dict):
        self.colors = {int(k): QColor(v) for k, v in colors.items()}
        self.update()

    def _geom(self):
        pad = 8
        s = min((self.width() - 2 * pad) / layout.WIDTH, (self.height() - 2 * pad) / layout.HEIGHT)
        ox = (self.width() - s * layout.WIDTH) / 2
        oy = (self.height() - s * layout.HEIGHT) / 2
        return s, ox, oy

    def _rect(self, k, s, ox, oy):
        g = max(2.0, s * 0.08)
        return QRectF(ox + k.x * s + g / 2, oy + k.y * s + g / 2, k.w * s - g, k.h * s - g)

    def led_at(self, pos: QPointF):
        s, ox, oy = self._geom()
        for k in layout.KEYS:
            if self._rect(k, s, ox, oy).contains(pos):
                return k.led
        return None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, ox, oy = self._geom()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#0d0d10"))
        p.drawRoundedRect(QRectF(ox - 6, oy - 6, s * layout.WIDTH + 12, s * layout.HEIGHT + 12), 10, 10)
        font = QFont(self.font())
        for k in layout.KEYS:
            r = self._rect(k, s, ox, oy)
            c = self.colors.get(k.led, QColor(0, 0, 0))
            base = QColor("#24242a")
            lit = QColor(int(base.red() * .25 + c.red() * .75), int(base.green() * .25 + c.green() * .75),
                         int(base.blue() * .25 + c.blue() * .75))
            p.setPen(QPen(QColor("#ffffff") if k.led in self.selected else QColor("#3a3a42"),
                          3 if k.led in self.selected else 1))
            p.setBrush(lit)
            p.drawRoundedRect(r, s * 0.12, s * 0.12)
            lum = 0.299 * lit.red() + 0.587 * lit.green() + 0.114 * lit.blue()
            p.setPen(QColor("#111") if lum > 150 else QColor("#e8e8ea"))
            font.setPixelSize(max(8, int(s * (0.26 if len(k.label) > 3 else 0.32))))
            p.setFont(font)
            p.drawText(r.adjusted(3, 2, -3, -2), Qt.AlignLeft | Qt.AlignTop, k.label)
            badge = self.badges.get(k.led)
            if badge:
                font.setPixelSize(max(7, int(s * 0.22)))
                p.setFont(font)
                p.setPen(QColor("#ffcc33"))
                p.drawText(r.adjusted(3, 2, -3, -2), Qt.AlignRight | Qt.AlignBottom, badge)

    def mousePressEvent(self, ev):
        led = self.led_at(ev.position())
        if led is not None:
            self._drag_last = led
            self.ledPressed.emit(led)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            led = self.led_at(ev.position())
            if led is not None and led != self._drag_last:
                self._drag_last = led
                self.ledDragged.emit(led)

    def mouseReleaseEvent(self, _):
        self._drag_last = None


class ColorButton(QPushButton):
    changed = Signal(str)

    def __init__(self, color="#ff0000", parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 28)
        self.clicked.connect(self._pick)
        self.set_color(color)

    def color(self) -> str:
        return self._color

    def set_color(self, h: str):
        self._color = QColor(h).name()
        self.setStyleSheet(f"background:{self._color}; border:1px solid #555; border-radius:4px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Choose colour")
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit(self._color)


class DeviceWorker(QObject):
    """Runs keyboard writes on a background thread so the window never freezes."""
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.q: queue.Queue = queue.Queue()
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self._loop)
        self.dev = None
        self.thread.start()

    def submit(self, fn, message="Done"):
        """fn(dev) runs on the worker thread. Older queued jobs are dropped (only latest matters)."""
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        self.q.put((fn, message))

    def stop(self):
        self.q.put(None)
        self.thread.quit()
        self.thread.wait(2000)

    def _loop(self):
        from ..device import K582
        while True:
            job = self.q.get()
            if job is None:
                break
            fn, message = job
            try:
                if self.dev is None:
                    self.dev = K582()
                fn(self.dev)
                self.finished.emit(message)
            except Exception as err:  # report and reconnect next time
                traceback.print_exc()
                if self.dev:
                    self.dev.close()
                self.dev = None
                self.failed.emit(str(err))
        if self.dev:
            self.dev.close()
