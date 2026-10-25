#!/bin/sh
# Fill in your GitHub username everywhere it's needed before publishing:
#   tools/set-github-user.sh yourname
set -eu
[ $# -eq 1 ] || { echo "usage: $0 GITHUB_USERNAME" >&2; exit 2; }
name=$1
case "$name" in *[!A-Za-z0-9-]*|"") echo "not a GitHub username: $name" >&2; exit 2 ;; esac
cd "$(dirname "$0")/.."
for f in install.sh README.md packaging/aur/PKGBUILD packaging/aur/.SRCINFO website/*.html website/*.js; do
    [ -f "$f" ] && sed -i "s/GITHUB_USER/$name/g" "$f" && echo "updated $f"
done
sed -i "s/^GITHUB = \"[^\"]*\"/GITHUB = \"$name\"/" g502hub/about.py && echo "updated g502hub/about.py"
echo "Done. Check REDDIT and DONATE in g502hub/about.py too."
