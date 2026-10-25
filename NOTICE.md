# Notices

## License

G502 Hub is free software: you can redistribute it and/or modify it under the
terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See [LICENSE](LICENSE).

## Not affiliated with Logitech

G502 Hub is an unofficial, independent project. It is not affiliated with,
endorsed, sponsored or supported by Logitech. Logitech, Logitech G, G HUB,
LIGHTSYNC, HERO and G502 are trademarks of Logitech Europe S.A., used here only
to say which mouse this software works with.

Counter-Strike 2, Dota 2 and Steam are trademarks of Valve Corporation.
All other trademarks are the property of their respective owners.

## The mouse photo

The picture of the mouse in the app is Logitech's product photo. The photo file
is not part of this project's code or packages: each installation downloads it
once, directly from Logitech's website (logitechg.com), the first time the app
starts, and keeps it in `~/.local/share/g502-hub/` for that user. The project
website loads it the same way, from Logitech's server. Screenshots of the app
in this repository show the app as it looks, with that photo in it.

## How the mouse is supported

G502 Hub talks to the mouse over Logitech's HID++ protocol, learned from the
public source code and notes of other open-source projects (see
[docs/protocol.md](docs/protocol.md) for every reference) and from talking to
the mouse itself. It contains no code from Logitech, and no Logitech software
was decompiled to write it.

The LIGHTSYNC bridge (`bridge/logitechled/`) is an independent implementation
of the function names of Logitech's LED SDK, written so that games can talk to
G502 Hub for interoperability. It contains no Logitech code or headers.

CS2 and Dota 2 lighting uses Valve's Game State Integration, a feature Valve
provides for exactly this purpose.

## Third-party software

G502 Hub uses these libraries at run time. They are installed separately by
your package manager and are not included in this repository.

| Component | License |
|---|---|
| Qt 6 and PySide6 | LGPL-3.0 |
| NumPy | BSD-3-Clause |
| PyGObject and GStreamer | LGPL-2.1-or-later |
| dbus-fast | MIT |
| libxkbcommon | MIT |
| PipeWire / libpulse (`parec`) | MIT / LGPL-2.1-or-later |

The website uses the Big Shoulders Display, Instrument Sans and JetBrains Mono
fonts from Google Fonts, all under the SIL Open Font License.

## Privacy

Everything runs on your computer. Screen and audio are analysed locally for
the live effects and are never stored or sent anywhere. The only network
access is the one-time download of the mouse photo from Logitech's website.
