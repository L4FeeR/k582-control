#!/usr/bin/env python3
"""Redragon K582 (VID 320F / PID 5000, EVision chip) lighting capture tool.

  extract  <capture.pcapng> <out.txt> --bus B --dev D   (Windows or Linux, needs tshark)
  analyze  <out.txt>                                   (anywhere)
  replay   <out.txt> [--dry-run]                       (Linux only, writes to /dev/hidrawN)

Only replays packets you captured yourself. It never builds or sends anything else.
"""
import argparse, glob, os, select, shutil, subprocess, sys, time
from collections import Counter

VID, PID = 0x320F, 0x5000
VENDOR_PAGE = b"\x06\x1c\xff"  # "Usage Page (0xFF1C)" in the HID report descriptor
REPORT_LEN = 64


def extract(args):
    tshark = shutil.which("tshark") or r"C:\Program Files\Wireshark\tshark.exe"
    filt = (f'usb.bus_id == {args.bus} && usb.device_address == {args.dev} && usb.src == "host"')
    cmd = [tshark, "-r", args.pcap, "-Y", filt, "-T", "fields", "-E", "separator=|",
           "-e", "frame.number", "-e", "usb.capdata", "-e", "usbhid.data", "-e", "usb.data_fragment"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    pkts = []
    for line in out.splitlines():
        frame, *fields = line.split("|")
        data = next((f.replace(":", "") for f in fields if f), "")
        if len(data) == REPORT_LEN * 2:  # skip caps-lock LED reports and other noise
            pkts.append((frame, data))
    with open(args.out, "w") as f:
        for frame, data in pkts:
            f.write(f"{data}  # frame {frame}\n")
    print(f"wrote {len(pkts)} x {REPORT_LEN}-byte host->device reports to {args.out}")


def load(path):
    pkts = []
    for line in open(path):
        hexpart = line.split("#")[0].strip()
        if hexpart:
            b = bytes.fromhex(hexpart)
            if len(b) != REPORT_LEN:
                sys.exit(f"bad length {len(b)} in: {line.strip()}")
            pkts.append(b)
    return pkts


def checksum_ok(p):
    # Hypothesis from OpenRGB's EVision driver: bytes[1:3] = LE16 sum of bytes[3:]
    return int.from_bytes(p[1:3], "little") == sum(p[3:]) & 0xFFFF


def analyze(args):
    pkts = load(args.file)
    print(f"{len(pkts)} packets; report IDs: {dict(Counter(p[0] for p in pkts))}")
    print(f"command byte [3] histogram: {dict(Counter(hex(p[3]) for p in pkts))}")
    ok = sum(checksum_ok(p) for p in pkts)
    print(f"checksum hypothesis matches {ok}/{len(pkts)}\n")
    for i, p in enumerate(pkts):
        tail = p[8:].rstrip(b"\x00")
        print(f"{i:3} id={p[0]:02x} sum={p[1]:02x}{p[2]:02x} cmd={p[3]:02x} len={p[4]:02x} "
              f"off={p[5]:02x}{p[6]:02x} [{p[7]:02x}] {tail.hex(' ')}")


def find_hidraw():
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = open(f"{node}/device/uevent").read()
        if f"{VID:08X}:{PID:08X}" not in uevent.upper():
            continue
        if VENDOR_PAGE in open(f"{node}/device/report_descriptor", "rb").read():
            return "/dev/" + os.path.basename(node)
    sys.exit("K582 vendor interface not found (is it plugged in? try lsusb | grep 320f)")


def replay(args):
    pkts = load(args.file)
    dev = find_hidraw()
    print(f"{dev}: sending {len(pkts)} packets{' (dry run)' if args.dry_run else ''}")
    if args.dry_run:
        return
    fd = os.open(dev, os.O_RDWR)
    try:
        for i, p in enumerate(pkts):
            os.write(fd, p)  # captured data already starts with the report ID
            if select.select([fd], [], [], 0.5)[0]:  # device acks each packet
                reply = os.read(fd, REPORT_LEN)
                if args.verbose:
                    print(f"{i:3} -> {p[:8].hex(' ')}  <- {reply[:8].hex(' ')}")
            time.sleep(0.005)
    finally:
        os.close(fd)
    print("done")


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="cmd", required=True)
e = sub.add_parser("extract"); e.add_argument("pcap"); e.add_argument("out")
e.add_argument("--bus", type=int, required=True); e.add_argument("--dev", type=int, required=True)
a = sub.add_parser("analyze"); a.add_argument("file")
r = sub.add_parser("replay"); r.add_argument("file"); r.add_argument("--dry-run", action="store_true")
r.add_argument("-v", "--verbose", action="store_true")
args = ap.parse_args()
{"extract": extract, "analyze": analyze, "replay": replay}[args.cmd](args)
