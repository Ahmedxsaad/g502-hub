#!/bin/sh
# G502 Hub installer: an unofficial G HUB alternative for the Logitech G502 HERO, on Linux.
#
#   curl -fsSL https://g502hub.ahmedxsaad.me/install.sh | sh
#   curl -fsSL https://g502hub.ahmedxsaad.me/install.sh | sh -s -- --uninstall
#
# Installs the dependencies with your package manager (asks for your password;
# set G502HUB_SKIP_DEPS=1 to skip that and install them yourself),
# puts the app in ~/.local/share/g502-hub/app, adds the permission rule that
# lets you configure the mouse without root, and adds "G502 Hub" to your menu.
set -eu

REPO="${G502HUB_REPO:-https://github.com/Ahmedxsaad/g502-hub}"
BRANCH="${G502HUB_BRANCH:-main}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/g502-hub/app"
MENU="$DATA/applications/g502-hub.desktop"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/g502-hub.desktop"
RULE="${G502HUB_RULE:-/etc/udev/rules.d/70-g502-hub.rules}"

bold=$(printf '\033[1m') blue=$(printf '\033[38;5;39m') dim=$(printf '\033[2m') reset=$(printf '\033[0m')
say() { printf '%s==>%s %s\n' "$blue$bold" "$reset" "$*"; }
note() { printf '    %s%s%s\n' "$dim" "$*" "$reset"; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

if [ "$(id -u)" = 0 ]; then
    die "run this as your normal user, not root (it asks for your password when it needs it)"
fi
SUDO=sudo
have sudo || { have doas && SUDO=doas; } || die "needs sudo or doas to install packages"

uninstall() {
    say "Removing G502 Hub"
    rm -rf "$APP" "$MENU" "$AUTOSTART"
    if [ -e "$RULE" ]; then
        $SUDO rm -f "$RULE" && $SUDO udevadm control --reload || true
    fi
    note "Your settings (~/.config/g502-hub) and mouse backups (~/.local/share/g502-hub/backups) were kept."
    note "Everything saved on the mouse itself stays on the mouse."
    exit 0
}
[ "${1:-}" = "--uninstall" ] && uninstall

printf '\n%s  G502 HUB%s  %sinstaller%s\n\n' "$bold" "$reset" "$dim" "$reset"

# ------------------------------------------------------------ dependencies
say "Installing dependencies"
if [ -n "${G502HUB_SKIP_DEPS:-}" ]; then
    note "skipped (G502HUB_SKIP_DEPS is set)"
elif have pacman; then
    $SUDO pacman -S --needed --noconfirm git python pyside6 python-numpy python-gobject python-dbus-fast python-evdev \
        gst-plugins-base gst-plugin-pipewire libpulse clang llvm lld
elif have dnf; then
    $SUDO dnf install -y git python3 python3-pyside6 python3-numpy python3-gobject python3-dbus-fast python3-evdev \
        gstreamer1-plugins-base pipewire-gstreamer pulseaudio-utils clang llvm lld || \
        note "some packages weren't found; the app still runs, a few live effects may not"
elif have apt-get; then
    $SUDO apt-get update -qq
    $SUDO apt-get install -y git python3 python3-pyside6.qtwidgets python3-pyside6.qtgui \
        python3-pyside6.qtcore python3-pyside6.qtdbus python3-numpy python3-gi gir1.2-gstreamer-1.0 \
        gstreamer1.0-plugins-base gstreamer1.0-pipewire python3-dbus-fast python3-evdev pulseaudio-utils clang llvm lld || \
        note "some packages weren't found; the app still runs, a few live effects may not"
else
    note "unknown package manager: install git, Python 3, PySide6, numpy, PyGObject, dbus-fast, evdev,"
    note "GStreamer with the PipeWire plugin and parec yourself, then run this again."
fi
python3 -c "import PySide6" 2>/dev/null || die "PySide6 isn't importable; install it with your package manager"

# ------------------------------------------------------------ the app
say "Getting G502 Hub"
if [ -d "$APP/.git" ]; then
    git -C "$APP" pull --ff-only --quiet
else
    rm -rf "$APP"
    mkdir -p "$(dirname "$APP")"
    git clone --quiet --depth 1 --branch "$BRANCH" "$REPO" "$APP"
fi
note "$(git -C "$APP" log -1 --format='version %h, %cd' --date=short)"

if have clang && have ld.lld && have llvm-dlltool; then
    say "Building the LIGHTSYNC bridge for Proton games"
    sh "$APP/bridge/logitechled/build.sh" >/dev/null && note "built" || note "build failed; the rest works without it"
else
    note "skipping the Proton LIGHTSYNC bridge (needs clang, llvm and lld)"
fi

# ------------------------------------------------------------ permission + menu
say "Letting your user configure the mouse"
if ! cmp -s "$APP/udev/70-g502-hub.rules" "$RULE" 2>/dev/null; then
    $SUDO install -m644 "$APP/udev/70-g502-hub.rules" "$RULE"
    $SUDO udevadm control --reload
    $SUDO udevadm trigger --action=change --subsystem-match=hidraw
    $SUDO udevadm trigger --action=change --sysname-match=uinput
fi
note "$RULE"

say "Adding G502 Hub to your applications"
sh "$APP/tools/install-desktop.sh" >/dev/null
note "$MENU"


printf '\n%s  Done!%s Open %sG502 Hub%s from your applications menu, or run:\n' "$bold" "$reset" "$bold" "$reset"
printf '    PYTHONPATH=%s python3 -m g502hub.gui\n\n' "$APP"
note "Close Piper / ratbagd while using it: it overwrites the mouse's G-Shift layer."
