#!/bin/sh
# Add G502 Hub to the application menu, running it from this checkout.
set -eu
repo=$(cd "$(dirname "$0")/.." && pwd)
dest="${XDG_DATA_HOME:-$HOME/.local/share}/applications/g502-hub.desktop"
mkdir -p "$(dirname "$dest")"
cat > "$dest" <<ENTRY
[Desktop Entry]
Type=Application
Name=G502 Hub
GenericName=Mouse Settings
Comment=DPI, lighting, buttons and profiles for the Logitech G502 HERO
Exec=env "PYTHONPATH=$repo" python3 -m g502hub.gui
Icon=input-mouse
Terminal=false
Categories=Settings;HardwareSettings;
Keywords=logitech;g502;mouse;dpi;rgb;ghub;
StartupWMClass=g502-hub
ENTRY
echo "Installed $dest"
