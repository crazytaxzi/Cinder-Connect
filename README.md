# Cinder-Connect

Cinder-Connect turns Firefox into an authenticated transport worker for ChatGPT while a lightweight local terminal becomes the human interface.

No OpenAI API, MCP service, or external relay is required. Firefox remains logged into `chatgpt.com`; Cinder-Connect moves text and command results between that web conversation and one exact local terminal process.

## Architecture

```text
You <-> Cinder Terminal <-> Windows named pipe <-> Native Messaging host
                                                    ^
                                                    |
                                              Firefox extension
                                                    |
                                             chatgpt.com /c/<id>
                                                    |
                                                 ChatGPT
```

The native host is a broker, not a general shell. Local commands are executed by the exact bound terminal process.
## Exact-process binding

Windows assigns the PID. `scripts/start_cinder_terminal.ps1` launches the terminal and records:

- PID
- executable path
- Windows process creation FILETIME
- binding UUID
- elevation request state

The native host asks Windows for the real named-pipe client PID and accepts the terminal only when it is the exact process instance in the binding. A different process cannot simply claim the PID in JSON.

The isolated bridge test verifies both acceptance of the exact bound process and rejection of a different child PID.

## Firefox bridge

The extension injects `extension/content.js` only on `https://chatgpt.com/*`. Each conversation page reports the UUID from `/c/<conversation-id>` to the background script.

Terminal messages are routed to that exact conversation. If several Cinder-enabled ChatGPT tabs are open, use `/use <conversation-id>` in the terminal instead of relying on a title or active-tab guess.
The content script watches ChatGPT's rendered conversation with a `MutationObserver`. When an assistant turn finishes, the visible text is forwarded to the terminal.

Older rendered turns are compacted out of layout/paint while the newest eight turns remain visible. This is intentionally conservative: it reduces browser rendering load without physically deleting React-managed conversation nodes.

## Command loop

Assistant replies may append machine-readable command blocks:

```text
[[CINDER_CMD:v1]]
{"id":"check-1","action":"shell.run","command":"git status","cwd":"C:\\Projects\\MIRA"}
[[/CINDER_CMD]]
```

Command blocks are removed from the text shown in the terminal. The exact bound terminal executes the command batch and returns one `CINDER_RESULT` turn to the same ChatGPT conversation. That result can trigger the next assistant turn without manual copy/paste.
Supported v1 actions:

- `shell.run`
- `process.start`
- `process.stop`
- `file.read`
- `file.write`
- `file.list`

The terminal blocks a small set of obviously destructive shell patterns and commands marked high/critical/destructive risk unless `/unsafe on` is explicitly enabled for that terminal session.

## Setup

1. Run `scripts/install_native_host.ps1` once.
2. In Firefox open `about:debugging` -> **This Firefox**.
3. Load `extension/manifest.json`, or press **Reload** if Cinder Connect is already loaded.
4. Run `scripts/start_cinder_terminal.ps1`.
5. Approve UAC if the launcher is configured for an elevated terminal.
6. Type in the terminal. Firefox can remain minimized.

The add-on is temporary when loaded through `about:debugging` and must be reloaded after Firefox restarts.
## Terminal commands

- `/status` - show exact process/binding state
- `/chats` - list ChatGPT conversation UUIDs currently connected through Firefox
- `/use <id>` - select one exact conversation when more than one is open
- `/unsafe on` - allow locally flagged high-risk command execution for this process lifetime
- `/unsafe off` - restore high-risk blocking
- `/quit` - exit

## Files

- `extension/manifest.json` - Firefox MV3 manifest
- `extension/background.js` - persistent Native Messaging and exact-chat router
- `extension/content.js` - ChatGPT page transport, response capture, render compaction
- `native-host/native_host.py` - Native Messaging/named-pipe broker
- `terminal/cinder_terminal.py` - terminal UI and local executor
- `scripts/install_native_host.ps1` - per-user Firefox native-host installer
- `scripts/start_cinder_terminal.ps1` - exact terminal launcher/binder
- `scripts/launch_and_bind.ps1` - generic user-editable process binder retained for other uses

## Verified on GamePC

Python, JavaScript, JSON, and PowerShell sources pass syntax/parse checks. `tests/test_pipe_bridge.py` verifies exact PID acceptance plus mismatched PID rejection. `tests/test_terminal_executor.py` verifies file read/write/list, PowerShell execution, and local high-risk blocking.
