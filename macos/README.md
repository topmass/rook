# Rook on macOS

## Rook.app owns every permission

macOS gives each permission to the responsible process. launchd runs `Rook.app/Contents/MacOS/RookHelper --launch <python> desktop/rook.py ...`, and Python, the presence panel and every tool run as its children. So Microphone, Input Monitoring, Screen Recording, Accessibility and Automation all belong to `Rook.app` (`com.rook.helper`), and they survive Python and Rook updates. `launchd/install.sh` writes that plist.

Opening the installed `Rook.app` in Finder loads and starts its login agent if needed. If the agent is already loaded, Finder and System Settings' "Quit & Reopen" restart the same job through launchd.

`RookHelper --check-access` prints each grant without a prompt. `RookHelper --request-access microphone|input|screen|accessibility` shows Apple's prompt. Run them through `relay.py mac-access`, so the answer is Rook.app's.

## Helper build and dev signing

Run `macos/RookHelper/build.sh` to compile and sign `~/Applications/Rook.app`. On first run, it creates a dedicated keychain at `~/Library/Keychains/rook-dev.keychain-db` (password stored with mode `0600` at `~/.config/rook/dev-keychain.pass`) and a self-signed `"Rook Dev"` code-signing certificate, without touching `login.keychain-db` or trust settings. Because the designated requirement binds to `com.rook.helper` and the certificate rather than a binary code hash, macOS keeps each grant across rebuilds.

Both signing paths use hardened runtime with `Rook.entitlements` (microphone and Apple Events). Without them, those calls fail silently.

## Public release signing

A public release needs an Apple Developer ID Application certificate (passed via `ROOK_SIGN_IDENTITY`) instead of the local self-signed dev certificate.
It also needs Apple notarisation (`xcrun notarytool` plus `xcrun stapler`) so Gatekeeper accepts the helper on other Macs without manual overrides.
