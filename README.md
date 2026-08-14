# Cinder-Connect

Windows-only Firefox-to-process binding bridge.

Cinder-Connect launches a user-selected Windows application, captures the PID Windows actually assigns, records that process identity, and lets a Firefox add-on verify that it is still attached to that exact process.

## Important PID rule

Windows chooses process IDs. This project does **not** reserve or force an arbitrary numeric PID.

Instead, `scripts/launch_and_bind.ps1` launches the configured executable and records:

- PID
- actual executable path
- Windows process creation timestamp (`ToFileTimeUtc()`)
- random binding UUID
- binding creation time

The Firefox native host requires the PID, path, and creation timestamp to all match. A reused PID therefore does not silently bind to a different process.

## Layout

- `extension/` - Firefox Manifest V3 add-on
- `native-host/native_host.ps1` - read-only native-messaging verifier
- `scripts/launch_and_bind.ps1` - user-editable launcher
- `scripts/install_native_host.ps1` - current-user Firefox native-host installer
- `tests/` - parser and native-protocol smoke tests
## Setup

1. Edit the USER CONFIG block at the top of `scripts/launch_and_bind.ps1`.
2. Run `scripts/install_native_host.ps1` once.
3. In Firefox open `about:debugging` -> **This Firefox** -> **Load Temporary Add-on**.
4. Select `extension/manifest.json`.
5. Run `scripts/launch_and_bind.ps1`.
6. Click the Cinder Connect toolbar button to view the exact bound PID and executable.

A temporary Firefox add-on is removed when Firefox restarts. Package/sign it later if permanent installation is desired.

## Runtime behavior

The add-on has no content scripts and requests no website permissions. It talks only to the registered native host `cinder_connect`.

The native host accepts only one command: `status`. It cannot launch programs, inject code, read process memory, kill processes, or query an arbitrary PID supplied by a webpage or extension message.

Possible states include:

- `attached` - PID, path, and creation timestamp all match
- `not_bound` - no binding file exists
- `stale_pid` - the bound process has exited
- `path_mismatch` - the PID belongs to another executable
- `start_time_mismatch` - the PID was reused by a newer process
- `bad_binding` - the binding file is malformed

The binding file lives at `%LOCALAPPDATA%\CinderConnect\binding.json`.
## Notes

If the configured executable is only a launcher that immediately spawns another process and exits, Cinder-Connect will correctly report the launcher PID as stale. Point `$TargetExe` at the long-lived executable you actually want to bind.

The native host is installed for the current Windows user under:

`HKCU\Software\Mozilla\NativeMessagingHosts\cinder_connect`

No administrator rights are required for that registration.

## Verified on GamePC

The development smoke test verified:

1. PowerShell source files parse with zero errors.
2. `launch_and_bind.ps1` launched Notepad and created a binding.
3. Native messaging returned `attached` with the exact PID/path/binding UUID.
4. After that process exited, the same binding returned `stale_pid`.
5. The installed `.bat` host wrapper returned the same correct statuses.
