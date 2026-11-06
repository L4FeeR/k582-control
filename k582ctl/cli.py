"""k582ctl command line.

  k582ctl                         open the app
  k582ctl effect static --color ff0000 [--brightness 0-4] [--speed 0-5] [--direction left]
  k582ctl effects                 list built-in effects
  k582ctl apply [PROFILE]         apply a profile's lighting (default profile if omitted)
  k582ctl remap [PROFILE]         run the key remapper / macros for a profile (foreground)
  k582ctl login                   apply the default profile and start its remapper (autostart)
"""
import argparse
import sys

from .profiles import default_profile, hex_to_rgb, load_profile


def _device():
    from .device import K582, DeviceError
    try:
        return K582()
    except DeviceError as err:
        sys.exit(str(err))


def cmd_effect(a):
    from .effects import BY_NAME, DIRECTION_VALUES
    eff = BY_NAME.get(a.name.lower())
    if not eff:
        sys.exit(f"unknown effect {a.name!r}; run: k582ctl effects")
    with _device() as dev:
        dev.set_mode(eff.value, brightness=a.brightness, speed=a.speed,
                     direction=DIRECTION_VALUES.get(a.direction.title(), 0),
                     random=a.random, color=hex_to_rgb(a.color))


def cmd_effects(_):
    from .effects import EFFECTS
    for eff in EFFECTS:
        extra = [x for x, ok in (("colour", eff.color), ("speed", eff.speed), ("random", eff.random)) if ok]
        if eff.directions:
            extra.append("/".join(eff.directions))
        print(f"{eff.name:20} {', '.join(extra)}")


def cmd_apply(a):
    from .lighting import apply_lighting
    prof = load_profile(a.profile or default_profile())
    with _device() as dev:
        apply_lighting(dev, prof["lighting"])
    print(f"applied {a.profile or default_profile()!r}")


def cmd_remap(a):
    from .remapd import main
    main(a.profile or default_profile())


def cmd_login(_):
    import time
    from .device import DeviceError
    name = default_profile()
    for _ in range(10):  # keyboard may still be enumerating right after login
        try:
            cmd_apply(argparse.Namespace(profile=name))
            break
        except (DeviceError, SystemExit):
            time.sleep(1)
    if load_profile(name).get("remaps"):
        cmd_remap(argparse.Namespace(profile=name))


def cmd_gui(_):
    try:
        from .gui.app import main
    except ImportError as err:
        msg = (f"K582 Control can't start: {err.name or err} is missing.\n"
               "Install it with:  sudo pacman -S pyside6 python-evdev")
        print(msg, file=sys.stderr)
        import shutil
        import subprocess
        if shutil.which("notify-send"):  # launched from the app menu: no terminal to show errors
            subprocess.run(["notify-send", "-i", "input-keyboard", "K582 Control", msg])
        sys.exit(1)
    main()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="k582ctl", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("effect")
    e.add_argument("name")
    e.add_argument("--color", default="ffffff")
    e.add_argument("--brightness", type=int, default=4)
    e.add_argument("--speed", type=int, default=3, help="0 fastest .. 5 slowest")
    e.add_argument("--direction", default="left")
    e.add_argument("--random", action="store_true")
    sub.add_parser("effects")
    for n in ("apply", "remap"):
        p = sub.add_parser(n)
        p.add_argument("profile", nargs="?")
    sub.add_parser("login")
    sub.add_parser("gui")
    a = ap.parse_args(argv)
    {"effect": cmd_effect, "effects": cmd_effects, "apply": cmd_apply, "remap": cmd_remap,
     "login": cmd_login, "gui": cmd_gui, None: cmd_gui}[a.cmd](a)
