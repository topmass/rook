# Rook on macOS

## Rook.app owns every permission

macOS gives each permission to the responsible process. launchd runs `Rook.app/Contents/MacOS/RookHelper --launch <python> desktop/rook.py ...`, and Python, the presence panel and every tool run as its children. So Microphone, Input Monitoring, Screen Recording, Accessibility and Automation all belong to `Rook.app` (`com.rook.helper`), and they survive Python and Rook updates. `launchd/install.sh` writes that plist.

Opening `Rook.app` by hand, or through System Settings' "Quit & Reopen", restarts Rook through launchd and never starts a second Rook.

`RookHelper --check-access` prints each grant without a prompt. `RookHelper --request-access microphone|input|screen|accessibility` shows Apple's prompt. Run them through `relay.py mac-access`, so the answer is Rook.app's.

## Herdr with the Claude sandbox

Rook's Claude session allows its own local relay socket. To connect Rook to an existing Herdr instance, export `HERDR_SOCKET_PATH` with the absolute path of the running socket before generating the LaunchAgent with `launchd/install.sh`. Set `HERDR_CONFIG_PATH` to your Herdr config file to use its saved machines. Export `ROOK_ALLOW_HERDR_SOCKET=1` to let Rook's Claude session use the configured Herdr socket. This grants access to Herdr's control API, including writes. Reload the launch job after updating its plist.

## Obsidian dictation

Export `ROOK_OBSIDIAN_VAULT="$HOME/obsidian"` (or your own absolute vault path) before generating the companion LaunchAgent. For an existing install, run `launchd/install.sh` from the updated Rook source using the same `--app`, `--python`, and `--workspace` paths as your current job. Reload the launch job after updating its plist. A manually started Rook uses the same variable in its launch environment.

Use your talk key and say “Save this to Obsidian” followed by the note. By default, Rook creates or appends to `rook/YYYY-MM-DD.md` inside the vault. Export `ROOK_OBSIDIAN_FOLDER` before generating the LaunchAgent to choose a different top-level folder name. The `daily` folder name is reserved.

## Helper build and dev signing

Run `macos/RookHelper/build.sh` to compile and sign `~/Applications/Rook.app`. On first run, it creates a dedicated keychain at `~/Library/Keychains/rook-dev.keychain-db` (password stored with mode `0600` at `~/.config/rook/dev-keychain.pass`) and a self-signed `"Rook Dev"` code-signing certificate, without touching `login.keychain-db` or trust settings. Because the designated requirement binds to `com.rook.helper` and the certificate rather than a binary code hash, macOS keeps each grant across rebuilds.

Both signing paths use hardened runtime with `Rook.entitlements` (microphone and Apple Events). Without them, those calls fail silently.

## Public release signing

A public release needs an Apple Developer ID Application certificate (passed via `ROOK_SIGN_IDENTITY`) instead of the local self-signed dev certificate.
It also needs Apple notarisation (`xcrun notarytool` plus `xcrun stapler`) so Gatekeeper accepts the helper on other Macs without manual overrides.
