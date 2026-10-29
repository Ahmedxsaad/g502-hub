#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
cargo build --locked --release
data="${XDG_DATA_HOME:-$HOME/.local/share}/g502-hub-rust"
menu="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$data/bin" "$menu"
for binary in g502-hub g502-hubd; do
    install -m755 "target/release/$binary" "$data/bin/$binary.new"
    mv "$data/bin/$binary.new" "$data/bin/$binary"
done
cp LICENSE NOTICE.md README.md "$data/"
if [ -f "$menu/g502-hub.desktop" ] && [ ! -f "$data/previous-launcher.desktop" ]; then
    cp "$menu/g502-hub.desktop" "$data/previous-launcher.desktop"
fi
rm -f "$menu/g502-hub-rust.desktop"
cat > "$menu/g502-hub.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=G502 Hub
Comment=DPI, lighting, buttons and profiles for the Logitech G502 HERO
Exec="$data/bin/g502-hub" --take-over
Icon=input-mouse
Terminal=false
Categories=Settings;HardwareSettings;
StartupWMClass=g502-hub
ENTRY
printf 'Installed G502 Hub. Open it from the application menu.\n'
# Preserve enabled login startup while replacing earlier launcher names.
auto="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
if [ -f "$auto/g502-hub.desktop" ] || [ -f "$auto/g502-hub-rust.desktop" ]; then
    if [ -f "$auto/g502-hub.desktop" ] && [ ! -f "$data/previous-autostart.desktop" ]; then
        cp "$auto/g502-hub.desktop" "$data/previous-autostart.desktop"
    fi
    cat > "$auto/g502-hub.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=G502 Hub
Comment=G502 HERO background service
Exec="$data/bin/g502-hub" --background --take-over
Icon=input-mouse
Terminal=false
X-GNOME-Autostart-enabled=true
ENTRY
    rm -f "$auto/g502-hub-rust.desktop"
fi
