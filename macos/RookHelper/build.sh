#!/bin/sh
# Build and sign Rook.app for this Mac user (no sudo, no Xcode IDE needed).
# launchd runs Rook.app, and Rook.app runs Python, so every macOS permission belongs to this bundle.
# Uses a dedicated dev keychain (~/Library/Keychains/rook-dev.keychain-db) and a
# self-signed "Rook Dev" code-signing certificate so macOS TCC keeps each grant across
# rebuilds. Override with ROOK_SIGN_IDENTITY for release signing. Both paths sign with
# hardened runtime and Rook.entitlements (microphone and Apple Events).
# Usage: macos/RookHelper/build.sh [OUTPUT_APP_PATH]
set -eu

here=$(cd "$(dirname "$0")" && pwd)
out="${1:-$HOME/Applications/Rook.app}"
macos_dir="$out/Contents/MacOS"
bundle_id="com.rook.helper"
entitlements="$here/Rook.entitlements"

mkdir -p "$macos_dir" "$out/Contents/Resources"
cp "$here/Info.plist" "$out/Contents/Info.plist"
cp "$here/RookIcon.icns" "$out/Contents/Resources/"

clang -O2 -fobjc-arc -Wall -Wextra \
  -framework Cocoa -framework WebKit -framework CoreGraphics \
  -framework AVFoundation -framework ApplicationServices \
  "$here/main.m" -o "$macos_dir/RookHelper"

if [ -n "${ROOK_SIGN_IDENTITY:-}" ]; then
  codesign --force --options runtime --entitlements "$entitlements" \
    --sign "$ROOK_SIGN_IDENTITY" --identifier "$bundle_id" "$out"
else
  kc="$HOME/Library/Keychains/rook-dev.keychain-db"
  pass_dir="${XDG_CONFIG_HOME:-$HOME/.config}/rook"
  pass_file="$pass_dir/dev-keychain.pass"
  cert_cn="Rook Dev"

  mkdir -p "$pass_dir"
  chmod 700 "$pass_dir"
  if [ ! -f "$pass_file" ]; then
    (umask 077 && openssl rand -hex 24 > "$pass_file")
    chmod 600 "$pass_file"
  fi
  pass=$(cat "$pass_file")

  if [ ! -f "$kc" ]; then
    security create-keychain -p "$pass" "$kc"
    security set-keychain-settings "$kc"
  fi
  security unlock-keychain -p "$pass" "$kc"

  if ! security find-identity -p codesigning "$kc" 2>/dev/null | grep -Fq "\"$cert_cn\""; then
    tmpd=$(mktemp -d /tmp/rook-cert-XXXXXX)
    trap 'rm -rf "$tmpd"' EXIT
    (
      umask 077
      cat > "$tmpd/cert.cnf" <<EOF
[req]
distinguished_name = dn
x509_extensions = v3_codesign
prompt = no

[dn]
CN = $cert_cn

[v3_codesign]
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, codeSigning
subjectKeyIdentifier = hash
EOF
      openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout "$tmpd/key.pem" -out "$tmpd/cert.pem" -config "$tmpd/cert.cnf" 2>/dev/null
      if openssl pkcs12 -help 2>&1 | grep -q -- '-legacy'; then
        openssl pkcs12 -export -legacy -inkey "$tmpd/key.pem" -in "$tmpd/cert.pem" \
          -out "$tmpd/dev.p12" -passout "pass:$pass"
      else
        openssl pkcs12 -export -inkey "$tmpd/key.pem" -in "$tmpd/cert.pem" \
          -out "$tmpd/dev.p12" -passout "pass:$pass"
      fi
    )
    security import "$tmpd/dev.p12" -k "$kc" -P "$pass" -T /usr/bin/codesign -T /usr/bin/security >/dev/null
    security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$pass" "$kc" >/dev/null
    rm -rf "$tmpd"
    trap - EXIT
  fi

  # Ensure rook-dev.keychain-db is in the user keychain search list without touching login.keychain-db.
  python3 - "$kc" <<'PY'
import subprocess, sys
kc = sys.argv[1]
out = subprocess.check_output(["security", "list-keychains", "-d", "user"], text=True)
chains = [ln.strip().strip('"') for ln in out.splitlines() if ln.strip()]
if kc not in chains:
    chains.append(kc)
    subprocess.check_call(["security", "list-keychains", "-d", "user", "-s", *chains])
PY

  codesign --force --options runtime --entitlements "$entitlements" \
    --keychain "$kc" --sign "$cert_cn" --identifier "$bundle_id" "$out"
fi

codesign --verify --deep --strict "$out"
codesign -d -r- "$out" 2>&1 | grep 'designated =>' || true
echo "Built and signed $out"
