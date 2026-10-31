# Rust port notices

This experimental port is derived from Ahmed Saad’s G502 Hub, licensed under
GPL-3.0-or-later. Protocol definitions, key maps, photo geometry, KWin adapter
and public test fixtures retain their upstream provenance.

Upstream: https://github.com/Ahmedxsaad/g502-hub
Protocol references: https://github.com/Ahmedxsaad/g502-hub/blob/main/docs/protocol.md

This project is independent of Logitech. Logitech, G HUB, LIGHTSYNC, HERO and
G502 are trademarks of their respective owners. The Logitech mouse photo is
not distributed here; this port reads an existing local image cache.

The Rust GUI and service use egui/eframe, serde, zbus, image, rustfft, x11rb,
libc and their transitive dependencies. Cargo.lock records dependency versions;
their individual licenses apply. System libxkbcommon, multimedia utilities,
optional Zenity and fonts are installed separately. Qt and Python are not
runtime dependencies of this port. The optional Windows SDK bridge binaries
remain an upstream component and are not included in this directory.

See LICENSE for this port’s GPL-3.0-or-later terms and README.md for system
requirements and experimental limitations.
