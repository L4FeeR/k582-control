# K582 RGB — where we are (handoff from the Windows session)

**Device:** Redragon K582 SURARA, USB `320F:5000` (EVision chip).
Lighting runs on interface 1, a HID collection with usage page `0xFF1C` / usage `0x92` and 64-byte reports, report ID `0x04`.

**Transport (from captures):** the Windows app sends HID SET_REPORT control transfers
(output report 4, wIndex 1). The keyboard echoes each packet back on interrupt IN endpoint 0x82.

**Packet layout (64 bytes):**
`[0]=04 report id | [1..2]=checksum LE16 = sum(bytes[3:64]) | [3]=cmd | [4]=len | [5..6]=offset LE | [7]=0 | [8..]=data`
The checksum was verified on every captured packet.

**Commands seen:** `01` begin, `06` write setting (len, offset, value), `02` end/save.

**Static red (static_red.txt):** begin → set[0]=0x05 → set[4]=0x01 → end.
Best guess: offset 0 = mode (5 = static), offset 4 = colour preset or brightness. Not confirmed yet.

**Next steps:**
1. On CachyOS: add the udev rule (GUIDE.md §5), then run `python k582.py replay static_red.txt -v` and check that the keyboard turns red.
2. Back on Windows, capture more variants (static_green, different brightness, wave, a custom colour) using
   `USBPcapCMD.exe -d \\.\USBPcap1 -A -o C:\cap\NAME.pcap`, then `Stop-Process -Name USBPcapCMD`.
   The K582 shows up on USBPcap1 as device address 3.
   Extract with: `tshark -r X.pcap -Y "usb.device_address==3 && usb.setup.bRequest==9" -T fields -e usb.data_fragment`
3. Diff the captures to map the offsets, then add a `set` command to k582.py that builds packets itself.
