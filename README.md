# Cinder-Connect

Firefox-to-Windows exact-process binding bridge.

## Scope

This repository exists for one purpose only:

1. Launch a user-selected Windows application.
2. Capture the PID Windows actually assigns to that process.
3. Bind a Firefox add-on to that exact process identity through Firefox Native Messaging.
4. Refuse stale or mismatched bindings.

It is intentionally **not** a general MIRA repository and should not collect unrelated code.

## Important PID rule

Windows assigns process IDs. This project does **not** attempt to reserve or force an arbitrary numeric PID.

Instead, `scripts/launch_and_bind.ps1` launches the configured executable with `Start-Process -PassThru`, captures the assigned PID, executable path, process creation time, and a random binding nonce, then writes the exact binding to:

`%LOCALAPPDATA%\CinderConnect\binding.json`

The native host validates the PID, executable path, and process creation time before reporting the target as attached. This prevents a stale PID from silently binding to an unrelated process after PID reuse.

## Layout

- `extension/` - Firefox WebExtension.
- `native-host/` - Firefox Native Messaging host.
- `scripts/launch_and_bind.ps1` - user-editable application launcher and binder.
- `scripts/install_native_host.ps1` - registers the native host for the current Windows user.

## Basic setup

1. Edit the clearly marked configuration block at the top of `scripts/launch_and_bind.ps1`.
2. Run `scripts/install_native_host.ps1` once.
3. Load `extension/manifest.json` as a temporary Firefox add-on from `about:debugging`, or package/sign it later.
4. Run `scripts/launch_and_bind.ps1`.
5. Open the Cinder-Connect toolbar popup. It should show the exact bound PID and executable.

The add-on deliberately has no content-script access and no arbitrary webpage-to-native command bridge in this initial version.
