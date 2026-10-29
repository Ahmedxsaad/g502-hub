#!/bin/sh
# Check that the AUR package g502-hub only ever shipped this repository's own packaging.
# Someone else maintains it for now. Every commit of theirs must equal packaging/aur at
# the release tag it names, byte for byte, apart from the "# Maintainer:" lines at the top.
# Also checks the tarball the AUR serves, who maintains it, and for look-alike packages.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
aurweb=${G502HUB_AURWEB:-https://aur.archlinux.org}
trusted="ilovesusu Ahmedxsaad"  # AUR accounts allowed to maintain it
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git clone -q "${G502HUB_AUR:-$aurweb/g502-hub.git}" "$work/aur"
aur() { git -C "$work/aur" "$@"; }
bad=0
fail() { echo "FAIL: $*"; bad=1; }

# The file minus its leading "# Maintainer:" / "# Contributor:" lines, which must be plain text
body() {
    n=$(awk '!/^# (Maintainer|Contributor):/ {print NR; exit}' "$1")
    # (the note makes the body differ from ours, so the check fails)
    if head -n "$((${n:-1} - 1))" "$1" | grep -q '[^][A-Za-z0-9 ._@<>()+:#-]'; then
        echo "odd characters in the maintainer lines"
    fi
    tail -n "+${n:-1}" "$1"
}

# 1. Every commit in the AUR history, so a change that was reverted later still shows
for commit in $(aur rev-list HEAD); do
    files=$(aur ls-tree --name-only "$commit" | tr '\n' ' ')
    ver=$(aur show "$commit:PKGBUILD" 2>/dev/null | sed -n 's/^pkgver=//p')
    what="AUR commit $(aur log -1 --format='%h %cs' "$commit"), version $ver"
    if [ "$files" != ".SRCINFO PKGBUILD " ]; then
        fail "$what: unexpected files: $files"; continue
    fi
    case "$ver" in *[!0-9.]* | "") fail "$what: odd pkgver"; continue ;; esac
    if ! git -C "$root" rev-parse -q --verify "refs/tags/v$ver" >/dev/null; then
        fail "$what: v$ver was never released here"; continue
    fi
    for f in PKGBUILD .SRCINFO; do
        git -C "$root" show "v$ver:packaging/aur/$f" > "$work/ours.raw"
        aur show "$commit:$f" > "$work/theirs.raw"
        body "$work/ours.raw" > "$work/ours"
        body "$work/theirs.raw" > "$work/theirs"
        if ! cmp -s "$work/ours" "$work/theirs"; then
            fail "$what: $f differs from v$ver"; diff -u "$work/ours" "$work/theirs" || true
        fi
    done
done

# 2. The snapshot tarball some AUR helpers download instead of cloning
mkdir "$work/snap"
curl -fsSL "$aurweb/cgit/aur.git/snapshot/g502-hub.tar.gz" | tar -xz -C "$work/snap"
snap_files=$(cd "$work/snap" && find . -mindepth 1 | LC_ALL=C sort | tr '\n' ' ')
if [ "$snap_files" != "./g502-hub ./g502-hub/.SRCINFO ./g502-hub/PKGBUILD " ]; then
    fail "snapshot tarball has unexpected files: $snap_files"
else
    for f in PKGBUILD .SRCINFO; do
        aur show "HEAD:$f" | cmp -s - "$work/snap/g502-hub/$f" || fail "snapshot tarball's $f differs from the git repository"
    done
fi

# 3. Who maintains it, and packages that could pass for it
AURWEB=$aurweb TRUSTED=$trusted python3 - <<'EOF' || bad=1
import json, os, sys, urllib.request

def rpc(path):
    with urllib.request.urlopen(os.environ["AURWEB"] + "/rpc/v5/" + path, timeout=30) as r:
        return json.load(r)["results"]

ok = True
info = rpc("info?arg[]=g502-hub")
maintainer = info[0]["Maintainer"] if info else None
if maintainer not in os.environ["TRUSTED"].split():
    print(f"FAIL: g502-hub is now maintained by {maintainer!r}")
    ok = False
others = set()
for by, arg in (("name", "g502hub"), ("name", "g502-hub"), ("name", "g502%20hub"),
                ("provides", "g502-hub"), ("replaces", "g502-hub"), ("conflicts", "g502-hub")):
    others |= {r["Name"] for r in rpc(f"search/{arg}?by={by}")} - {"g502-hub"}
if others:
    print(f"FAIL: other AUR packages look like this one: {', '.join(sorted(others))}")
    ok = False
sys.exit(0 if ok else 1)
EOF

if [ "$bad" = 0 ]; then
    echo "AUR package matches this repository: $(aur rev-list --count HEAD) commits, the snapshot, maintainer and look-alikes checked"
fi
exit "$bad"
