#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
cargo build --locked --release
data="${XDG_DATA_HOME:-$HOME/.local/share}/g502-hub-rust"
menu="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$data/bin" "$menu"
for binary in g502-hub-rust g502-hubd-rust; do
    install -m755 "target/release/$binary" "$data/bin/$binary.new"
    mv "$data/bin/$binary.new" "$data/bin/$binary"
done
cp LICENSE NOTICE.md README.md "$data/"
cat > "$menu/g502-hub-rust.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=G502 Hub Rust
Comment=Native Rust G502 HERO test build
Exec="$data/bin/g502-hub-rust" --take-over
Icon=input-mouse
Terminal=false
Categories=Settings;HardwareSettings;
StartupWMClass=g502-hub-rust
ENTRY
printf 'Installed G502 Hub Rust. Open it from the application menu.\n'
