# K582 lighting: capture on Windows, replay on CachyOS

Keyboard: **VID 0x320F / PID 0x5000** (EVision chip). Lighting interface: USB interface 1,
HID collection 4, **usage page 0xFF1C / usage 0x92, 64-byte IN + OUT reports**.

## 0. Try OpenRGB first (might make this whole thing unnecessary)
OpenRGB's "EVision" driver matches exactly this VID + usage page. On CachyOS:
`sudo pacman -S openrgb` (or the AUR `openrgb-git`), load the udev rules, then run `openrgb --list-devices`.
If it shows the K582, you're done.

## 1. Install the capture tools (Windows)
- Wireshark from wireshark.org. During setup, **tick "Install USBPcap"** (this adds a capture filter driver).
- Reboot.

## 2. Find the keyboard's bus and device address
Run `"C:\Program Files\USBPcap\USBPcapCMD.exe"` in an **admin** terminal. It lists each root hub
(`\\.\USBPcap1`, `2`, ...) and the devices on it. Find the hub that has `VID_320F PID_5000`.
That hub number is your **bus**. The **device address** shows up in Wireshark (`usb.device_address`) after you capture.

## 3. Capture one effect per file
Do one action per capture so each file holds exactly one command sequence:
1. In Wireshark, start capturing on that USBPcap interface.
2. In the Redragon app, change **one** thing (e.g. Static, red, full brightness) and click Apply.
3. Stop, then save as `static_red.pcapng`.

Repeat for each effect or color you want: `static_green`, `wave`, `breathing_blue`, `off`, and so on.
Varying one parameter at a time (red vs. green, brightness 1 vs. 4) makes the diff obvious.

**Don't** click firmware update, reset or "restore defaults" while you're capturing.
You only want lighting packets in these files.

Display filter to see the packets in Wireshark:
`usb.device_address == <D> && usb.src == "host" && usb.data_len == 64`

## 4. Extract and analyze (Windows)
```
python k582.py extract static_red.pcapng static_red.txt --bus 1 --dev 5
python k582.py analyze static_red.txt
```
`analyze` prints each packet split into fields: report ID, checksum, command, length, offset, data.
It also checks the checksum guess (16-bit little-endian sum of bytes 3..63, stored in bytes 1..2).
Diff `static_red.txt` against `static_green.txt` to find which bytes hold the color.

## 5. Replay on CachyOS
Copy `k582.py` and the `.txt` files over. Then, once:
```
echo 'KERNEL=="hidraw*", ATTRS{idVendor}=="320f", ATTRS{idProduct}=="5000", MODE="0660", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/60-k582.rules
sudo udevadm control --reload && sudo udevadm trigger
```
After that:
```
python k582.py replay static_red.txt --dry-run   # finds /dev/hidrawN, sends nothing
python k582.py replay static_red.txt -v
```
The script only writes packets that came from your own captures, to the vendor HID interface.
That's the same thing the Windows app does. It doesn't touch firmware.
