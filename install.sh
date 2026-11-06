#!/bin/sh
# Installs the udev rule (needs sudo) and adds K582 Control to your app menu.
set -e
if ! python3 -c "import PySide6, evdev" 2>/dev/null; then
    echo "Installing PySide6 and python-evdev..."
    sudo pacman -S --needed pyside6 python-evdev
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Installing udev rule (asks for your password)..."
sudo install -m 644 "$DIR/packaging/60-k582.rules" /etc/udev/rules.d/60-k582.rules
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=hidraw --subsystem-match=input --subsystem-match=misc
mkdir -p "$HOME/.local/share/applications"
sed "s|@LAUNCHER@|\"$DIR/k582ctl.sh\"|" "$DIR/packaging/k582-control.desktop" \
    > "$HOME/.local/share/applications/k582-control.desktop"
echo "Done. Open 'K582 Control' from your app menu, or run: $DIR/k582ctl.sh"
