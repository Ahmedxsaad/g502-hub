# g502-hub

A G HUB replacement for the Logitech G502 HERO (USB `046d:c08b`) on Linux.

It talks to the mouse directly over HID++ 2.0 (`/dev/hidraw`), using no
libratbag and no root.

## Status

| Phase | Status |
|---|---|
| 1. Core engine: onboard profiles (incl. G-Shift layer, lighting, names), backup/restore, CLI | done |
| 2. App window (G HUB-style) for onboard mode: lighting, sensitivity, assignments, profiles | done |
| 3. Software mode service: animated lighting, per-game profiles, DPI OSD, tray, G-Shift with any action | next |
| 4. Macros, Lua scripts, profile import/export | planned |

## Setup

One-time, so your user can open the mouse's HID++ interface:

```sh
sudo install -m644 udev/70-g502-hub.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger --action=change --subsystem-match=hidraw
```

Stop Piper/ratbagd while using this. ratbagd forces onboard mode, and every save it makes wipes the G-Shift layer.

## App

Needs PySide6 (`sudo pacman -S pyside6`).

```sh
python -m g502hub.gui             # run from this folder
./tools/install-desktop.sh        # add "G502 Hub" to the application menu
```

- **Lightsync**: Fixed, Breathing, Color cycle or Off for the DPI lights and
  the logo, together or separately. Changes show on the mouse right away.
  Saved colors are kept in `~/.config/g502-hub/settings.json`.
- **Assignments**: any button on the primary or G-Shift layer, set to a mouse,
  scroll, DPI, profile or G-Shift command, a key combo, or a media key. Key
  names follow your keyboard layout.
- **Sensitivity**: up to 5 DPI levels on a draggable track (click it to add
  a level), default and sniper level, report rate. While you drag the level
  you're on, the mouse's DPI changes so you can feel it.
- **Profiles**: the 5 onboard slots. Rename, activate, include in or skip
  from the G9 cycle, reset to factory, copy, plus backup and restore.

Changes are saved to the mouse automatically about a second after you make
them, so they keep working without the app, and on other computers.

## CLI

```sh
python -m g502hub info            # device, firmware, live DPI/rate, LED zones
python -m g502hub profiles        # all 5 onboard slots at a glance
python -m g502hub show 2          # one slot: DPI, buttons + G-Shift layer, lighting
python -m g502hub backup          # full onboard memory dump
python -m g502hub restore FILE --yes

python -m g502hub activate 3
python -m g502hub set 2 --dpi 400,800,1600,3200 --default 3 --shift 1 --rate 1000 --name "Desktop"
python -m g502hub bind 2 g7 key:ctrl+c
python -m g502hub bind 2 g8 media:volume-up --gshift
python -m g502hub led 2 all breathing 00dcff --period 4000 --brightness 80
python -m g502hub disable 5       # skip slot 5 when cycling profiles with G9
python -m g502hub spy             # print raw button presses (Mouse Button Spy)
```

Before its first write, every write command saves a full backup to
`~/.local/share/g502-hub/backups/`. Every sector written is read back and
compared.

## Safety

- The app writes only user flash sectors (`0x0000`–`0x000F`), never ROM.
- Writes are read-modify-write. Bytes the app doesn't understand are kept
  verbatim, and a byte-exact round trip of real dumps is part of the tests.
- A sector with a bad CRC is ignored by the firmware, which falls back to the
  factory profile. The mouse can always be recovered with `restore`.
- The hidden factory/engineering HID++ features are never used.

## Layout

```
g502hub/hidpp.py    HID++ 2.0 transport over hidraw
g502hub/device.py   G502 features: 0x8100 onboard, 0x2201 DPI, 0x8060 rate, 0x8070 LEDs, 0x8110 spy
g502hub/onboard.py  profile/directory/binding/LED codecs (format 2)
g502hub/macro.py    onboard macro codec (format 1)
g502hub/backup.py   dump/restore
g502hub/cli.py      command line
g502hub/gui/        the app (PySide6)
docs/protocol.md    wire protocol reference with sources
docs/ghub-features.md  what G HUB offers for this mouse
docs/hardware-notes.md behaviour verified on this unit
tools/hidpp_probe.py   standalone feature probe
```

## Tests

```sh
python -m pytest
```
