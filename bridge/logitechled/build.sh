#!/bin/sh
# Build LogitechLed.dll for 64-bit and 32-bit Windows games, without mingw:
# clang compiles freestanding C, llvm-dlltool makes the import libraries and
# lld links. Needs: clang, llvm (llvm-dlltool), lld.
#   sudo pacman -S --needed clang llvm lld
# Output: g502hub/bridge_bin/{x64,x86}/LogitechLed.dll
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out="$here/../../g502hub/bridge_bin"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

compile_only=0
if ! command -v ld.lld >/dev/null 2>&1; then
    echo "ld.lld not found: only checking that the source compiles (sudo pacman -S lld to build the DLLs)" >&2
    compile_only=1
fi

CFLAGS="-O2 -ffreestanding -nostdlib -fno-stack-protector -mno-stack-arg-probe -fno-builtin -Wall -Wextra -Werror"

build() {  # arch-dir clang-target dlltool-machine
    dir=$1 target=$2 machine=$3
    mkdir -p "$work/$dir"
    clang --target="$target" $CFLAGS -c "$here/logitechled.c" -o "$work/$dir/logitechled.o"
    [ "$compile_only" = 1 ] && { echo "compiled $dir"; return; }
    for lib in kernel32 ws2_32; do
        if [ "$dir" = x64 ]; then
            sed 's/@[0-9]*$//' "$here/imports/$lib.def" > "$work/$dir/$lib.def"
            llvm-dlltool -m "$machine" -d "$work/$dir/$lib.def" -l "$work/$dir/lib$lib.a"
        else
            llvm-dlltool -m "$machine" -k -d "$here/imports/$lib.def" -l "$work/$dir/lib$lib.a"
        fi
    done
    mkdir -p "$out/$dir"
    clang --target="$target" -shared -nostdlib -fuse-ld=lld -o "$out/$dir/LogitechLed.dll" \
        "$work/$dir/logitechled.o" "$here/LogitechLed.def" -L"$work/$dir" -lkernel32 -lws2_32 \
        -Wl,--disable-auto-import -Wl,--no-insert-timestamp
    echo "built $out/$dir/LogitechLed.dll"
}

build x64 x86_64-w64-windows-gnu i386:x86-64
build x86 i686-w64-windows-gnu i386
