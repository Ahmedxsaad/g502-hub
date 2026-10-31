# G502 Hub — experimental native implementation

A native Rust daemon **and** native egui/eframe settings application for the wired
Logitech G502 HERO (`046d:c08b`). Derived from
[Ahmedxsaad/g502-hub](https://github.com/Ahmedxsaad/g502-hub), GPL-3.0-or-later.
The Python implementation can remain installed alongside this experimental port.

## Build and test

```sh
cargo test --release
cargo build --release
# Optional per-user installation (no root): ./install.sh
# Launch a separate test UI; hands over from the installed Python build:
./target/release/g502-hub --take-over
```

The daemon is `g502-hubd`. Build it without GUI dependencies with
`cargo build --release --no-default-features --bin g502-hubd`.
Use `g502-hubd --status` or `--stop` for diagnostics and shutdown.
The integrated header contains the window controls. Drag the header to move the
window; double-click it to maximize/restore, or use F11 for fullscreen. Resizing
works from the edges. Closing waits for a pending profile save.

Closing the graphical window leaves only the daemon. Reopen the test launcher
to edit settings. Stop Rust before reopening the original Python application.

The first launch copies existing `g502-hub/settings.json` into a separate
`g502-hub-rust/settings.json` under the XDG config directory. It does not update
Python's configuration. Both applications configure the same physical onboard
memory: profile edits saved to the mouse are therefore shared between them.
The UI automatically saves profile edits after a short debounce and control release.

## Implemented

- Direct HID++ transport over hidraw, feature discovery, identity and firmware.
- Profile-format-2 codecs preserving unknown bytes, CRC verification, restricted
  writes, whole-sector busy retry and read-back verification. Automatic complete
  backup before the first write in each session.
- DPI levels, defaults, DPI Shift, report intervals, primary and
  G-Shift button layers, keyboard shortcuts and media bindings.
- Both LED zones: off, static, cycle, breathing; separate live effects including
  wave, DPI colors, audio spectrum/pulse/rainbow and screen sampling.
- Profile names, switching, cycle inclusion, reset, copy, compatible .g502profile
  import/export, complete backup and restore.
- Macro editor and keyboard recording, delays, text, key/button press/release,
  movement, scroll and media; once/held/toggle playback over Linux uinput.
  AZERTY text via native libxkbcommon; optional onboard macro storage.
- Steam process detection, X11/KWin active windows, MPRIS media rules, profile
  switching/restoration, cover-art colors, CS2/Dota 2 GSI and LIGHTSYNC UDP input.
- GSI config installation and Wine/Proton registry management with backups and
  running-prefix checks. Existing upstream SDK bridge DLLs are wire-compatible.
- Per-user Unix JSON IPC, single-instance service, independent GUI lifecycle,
  optional login startup, and KDE DPI/profile OSD.

## Native boundaries and dependencies

No Python interpreter or Qt is used by the Rust daemon or GUI. The program links
libxkbcommon for keyboard layout and uses Linux hidraw/uinput. Audio monitoring
uses the system `parec` capture utility; screen capture uses system GStreamer
(`gst-launch-1.0`, ximagesrc or PipeWire plus the desktop portal). This is system
multimedia infrastructure rather than a Python fallback. The small KWin adapter
remains JavaScript because that is KWin's scripting interface. SDK bridge DLLs
are optional existing upstream Windows binaries, not part of this Rust rewrite.

The native UI follows the original Qt layout, with matching mouse hit regions,
LED previews, profile cards and editors. It is not verified pixel-for-pixel.
GSI visual effects, cover-art palettes and audio analysis use the Python formulas,
with numeric reference tests extracted from the original implementation. Wayland screen sharing still requires the desktop's permission;
active-window rules on Wayland require KDE, as in the original implementation.

## Experimental status

Protocol/codec tests use the upstream public real-device dump. Destructive
writes, errors and retries are exercised against a simulated HID transport.
Native macro cancellation tests use an isolated virtual event sink. An opt-in
`cargo test --locked --release --test text_device -- --ignored --nocapture` check
reads its own grabbed uinput device; it requires local input permissions. The complete feature set still needs
hands-on validation on real games, portals and Wine prefixes; compilation and
unit tests alone do not establish complete behavioral equivalence.

Configuration and backups are separate, but onboard saves affect the physical
mouse. A previous Python installation remains usable after stopping the Rust
service. The login option controls the normal G502 Hub autostart entry. Installation
preserves an existing enabled startup entry and updates it to the installed
service. Previous desktop launchers are backed up in the data directory.

File selection uses the optional system `zenity` utility, with a path-entry
fallback. Linux development packages include libxkbcommon, X11 and Wayland.

The Logitech photo is not included in this repository. The UI reads its existing
XDG cache, downloads it on first use when absent, and offers a new-download button
in Settings. Downloading uses the optional system `curl` utility; see NOTICE.md.

The executables and application menu use `g502-hub` and `g502-hubd`.
The legacy `g502-hub-rust` data/config/runtime directories are retained for
compatibility with existing native installations and to avoid overwriting
the earlier Python configuration.

## Parity audit

The functional gaps listed in the initial audit have been ported, including DPI track insertion, factory assignments, macro labels/storage validation, rule templates/recent context, photo/access/GSI settings and the About page. See [the parity audit](PARITY.md) for test evidence and remaining platform/rendering limitations.
