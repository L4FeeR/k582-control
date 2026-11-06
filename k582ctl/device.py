"""Low-level driver for the Redragon K582 (EVision chip, USB 320F:5000).

Talks to the vendor HID interface (usage page 0xFF1C) through /dev/hidrawN.
Every packet is 64 bytes:

    [0]    0x04            report ID
    [1:3]  checksum        LE16 sum of bytes[3:64]
    [3]    command         0x01 begin, 0x02 end, 0x06 set parameter, 0x11 write per-key colours
    [4]    length          number of data bytes
    [5:7]  offset          LE16 parameter / data offset
    [7]    0
    [8:]   data

The keyboard echoes every packet back on its interrupt IN endpoint; we wait for it.
Protocol details cross-checked against OpenRGB's EVisionKeyboardController (GPL-2.0+).
"""
from __future__ import annotations

import glob
import os
import select
import threading
import time

VID, PID = 0x320F, 0x5000
VENDOR_PAGE = b"\x06\x1c\xff"  # "Usage Page (0xFF1C)" in the HID report descriptor
REPORT_LEN = 64

CMD_BEGIN = 0x01
CMD_END = 0x02
CMD_SET_PARAM = 0x06
CMD_WRITE_COLORS = 0x11

PARAM_MODE_BLOCK = 0x00   # mode, brightness, speed, direction, random, r, g, b
PARAM_POLLING_RATE = 0x0F

NUM_LEDS = 126
COLOR_CHUNK = 0x36        # 54 bytes = 18 LEDs per packet
COLOR_BYTES = COLOR_CHUNK * 7  # 378 = 126 * 3

BRIGHTNESS_MAX = 4        # 0 = off .. 4 = full
SPEED_FASTEST, SPEED_SLOWEST = 0, 5


class DeviceError(RuntimeError):
    pass


def build_packet(cmd: int, offset: int = 0, data: bytes = b"") -> bytes:
    if len(data) > REPORT_LEN - 8:
        raise ValueError("data too long for one packet")
    p = bytearray(REPORT_LEN)
    p[0] = 0x04
    p[3] = cmd
    p[4] = len(data)
    p[5] = offset & 0xFF
    p[6] = (offset >> 8) & 0xFF
    p[8:8 + len(data)] = data
    s = sum(p[3:]) & 0xFFFF
    p[1], p[2] = s & 0xFF, s >> 8
    return bytes(p)


def find_hidraw() -> str:
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            uevent = open(f"{node}/device/uevent").read().upper()
            desc = open(f"{node}/device/report_descriptor", "rb").read()
        except OSError:
            continue
        if f"{VID:08X}:{PID:08X}" in uevent and VENDOR_PAGE in desc:
            return "/dev/" + os.path.basename(node)
    raise DeviceError("K582 not found. Is it plugged in? (lsusb | grep 320f)")


class K582:
    """One open connection to the keyboard. Thread-safe; each transaction is atomic."""

    def __init__(self, path: str | None = None, timeout: float = 0.5):
        self.path = path or find_hidraw()
        self.timeout = timeout
        self.lock = threading.Lock()
        try:
            self.fd = os.open(self.path, os.O_RDWR)
        except PermissionError as e:
            raise DeviceError(f"No permission for {self.path}. Install the udev rule "
                              "(see README) and replug the keyboard.") from e
        self.last_ack_ms = 0.0

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- transport --------------------------------------------------------------
    def _drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, REPORT_LEN)

    def _send(self, pkt: bytes):
        t = time.perf_counter()
        os.write(self.fd, pkt)
        # The keyboard echoes each packet; wait for it so we never outrun the MCU.
        if select.select([self.fd], [], [], self.timeout)[0]:
            os.read(self.fd, REPORT_LEN)
        else:
            raise DeviceError("keyboard did not acknowledge a packet")
        self.last_ack_ms = (time.perf_counter() - t) * 1000

    def transaction(self, packets: list[bytes]):
        """begin, packets..., end — the same framing the Windows app uses."""
        with self.lock:
            self._drain()
            self._send(build_packet(CMD_BEGIN))
            for p in packets:
                self._send(p)
            self._send(build_packet(CMD_END))

    # -- high-level -------------------------------------------------------------
    @staticmethod
    def mode_packet(mode: int, brightness: int = BRIGHTNESS_MAX, speed: int = 3,
                    direction: int = 0, random: bool = False,
                    color: tuple[int, int, int] = (255, 255, 255)) -> bytes:
        r, g, b = color
        data = bytes([mode, _clamp(brightness, 0, BRIGHTNESS_MAX), _clamp(speed, 0, 5),
                      direction & 0xFF, 1 if random else 0, r & 0xFF, g & 0xFF, b & 0xFF])
        return build_packet(CMD_SET_PARAM, PARAM_MODE_BLOCK, data)

    @staticmethod
    def color_packets(colors: list[tuple[int, int, int]]) -> list[bytes]:
        buf = bytearray(COLOR_BYTES)
        for i, (r, g, b) in enumerate(colors[:NUM_LEDS]):
            buf[3 * i:3 * i + 3] = bytes((r & 0xFF, g & 0xFF, b & 0xFF))
        return [build_packet(CMD_WRITE_COLORS, off, bytes(buf[off:off + COLOR_CHUNK]))
                for off in range(0, COLOR_BYTES, COLOR_CHUNK)]

    def set_mode(self, mode: int, **kw):
        self.transaction([self.mode_packet(mode, **kw)])

    def set_custom(self, colors: list[tuple[int, int, int]], brightness: int = BRIGHTNESS_MAX):
        """Switch to Custom mode and write a colour for every LED (index = LED number)."""
        from .effects import CUSTOM_MODE
        self.transaction([self.mode_packet(CUSTOM_MODE, brightness=brightness)]
                         + self.color_packets(colors))

    def write_colors(self, colors: list[tuple[int, int, int]]):
        """Only rewrite per-key colours (keyboard must already be in Custom mode)."""
        self.transaction(self.color_packets(colors))


def _clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))
