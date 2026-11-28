#!/bin/sh
# Build the plugin zip for Decky's "Install plugin from ZIP" (Decky settings > Developer).
#
#   scripts/package.sh            build the frontend, then out/rook-deck.zip
#   scripts/package.sh --no-build zip what is there (dist/index.js must exist)
#
# Decky unpacks the zip into ~/homebrew/plugins and wants exactly one top-level folder with a plugin.json in it
# (decky-loader backend/decky_loader/browser.py: "plugin.json" one level deep). The folder holds what the plugin runs:
# plugin.json, package.json, main.py, dist/index.js, py_modules/, overlay/ (the overlay process and the page the backend
# serves), bin/ when there is one, LICENSE and README.md. Tests, sources and dev tools stay out.
set -eu
here=$(cd "$(dirname "$0")/.." && pwd)
name=rook-deck
out="$here/out"
stage="$out/stage/$name"

build=1
[ "${1:-}" = "--no-build" ] && build=0

if [ "$build" = 1 ]; then
  cd "$here"
  # The frontend's own build (src/ and package.json belong to the frontend): pnpm 9 as the template asks, else npm.
  if command -v pnpm >/dev/null 2>&1; then
    pnpm install && pnpm build
  elif command -v npx >/dev/null 2>&1; then
    npx --yes pnpm@9 install && npx --yes pnpm@9 build
  else
    npm install && npm run build
  fi
fi

[ -f "$here/dist/index.js" ] || { echo "dist/index.js is missing: build the frontend first" >&2; exit 1; }
[ -f "$here/main.py" ] && [ -f "$here/plugin.json" ] && [ -f "$here/package.json" ] || {
  echo "main.py, plugin.json and package.json must all exist" >&2; exit 1; }

# Decky runs a backend as root only when plugin.json's flags hold "root" ("_root" is the template's switched-off
# spelling). Without root the backend still runs as the Deck user, but /dev/uinput and the controller's raw HID node
# may refuse it. Say so rather than change another stream's file.
if ! python3 -c 'import json,sys; sys.exit(0 if "root" in json.load(open(sys.argv[1])).get("flags", []) else 1)' \
    "$here/plugin.json"; then
  echo "warning: plugin.json flags do not include \"root\" (\"_root\" does not count); the backend will run as deck" >&2
fi

rm -rf "$out/stage"
mkdir -p "$stage"
cp "$here/plugin.json" "$here/package.json" "$here/main.py" "$stage/"
for f in LICENSE LICENSE.md README.md; do [ -f "$here/$f" ] && cp "$here/$f" "$stage/"; done
mkdir -p "$stage/dist" && cp -R "$here/dist/." "$stage/dist/"
cp -R "$here/py_modules" "$stage/py_modules"
[ -d "$here/overlay" ] && cp -R "$here/overlay" "$stage/overlay"
[ -d "$here/bin" ] && cp -R "$here/bin" "$stage/bin"
[ -d "$here/backend/out" ] && mkdir -p "$stage/bin" && cp -R "$here/backend/out/." "$stage/bin/"
[ -d "$here/defaults" ] && cp -R "$here/defaults/." "$stage/"
rm -f "$stage/defaults.txt"  # The template's placeholder.
# Development leftovers stay out of the zip.
find "$stage" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$stage" -name '*.pyc' -delete
rm -rf "$stage/overlay/dev" "$stage/overlay/screenshots"

rm -f "$out/$name.zip"
(cd "$out/stage" && python3 -m zipfile -c "$out/$name.zip" "$name")
rm -rf "$out/stage"
echo "$out/$name.zip"
python3 -m zipfile -l "$out/$name.zip" | awk 'NR>1 {print $1}' | sed -n '1,200p' | grep -E '/(plugin.json|main.py|dist/index.js)$'
