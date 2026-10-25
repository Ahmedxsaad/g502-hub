#!/bin/sh
# Build the website (website/ plus the installer at its root) and deploy it to Cloudflare.
# Needs `npx wrangler login` once.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
out="$root/dist/site"
rm -rf "${out:?}"
mkdir -p "$out"
cp -R "$root/website/." "$out/"
cp "$root/install.sh" "$out/install.sh"
cd "$root"
npx --yes wrangler@4 deploy "$@"
