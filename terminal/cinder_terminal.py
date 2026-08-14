import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from multiprocessing.connection import Client
from pathlib import Path

BASE = Path(os.environ.get("LOCALAPPDATA", ".")) / "CinderConnect"
SECRET_PATH = Path(os.environ.get("CINDER_SECRET_PATH", BASE / "bridge_secret.bin"))
BINDING_PATH = Path(os.environ.get("CINDER_BINDING_PATH", BASE / "binding.json"))
PIPE_NAME = os.environ.get("CINDER_PIPE_NAME", r"\\.\pipe\CinderConnect")
MAX_OUTPUT = 32768

conn = None
send_lock = threading.Lock()
selected_chat = None
known_chats = set()
unsafe_mode = False
command_busy = False

DANGEROUS = (
    "format ", "diskpart", "shutdown", "restart-computer", "stop-computer",
    "rm -rf", "del /s", "rd /s", "reg delete", "bcdedit", "vssadmin delete",
    "git reset --hard", "git clean -fd", "remove-item -recurse -force"
)
def authkey():
    if not SECRET_PATH.exists():
        raise FileNotFoundError("Cinder bridge secret not found. Reload the Firefox extension first.")
    return hashlib.sha256(SECRET_PATH.read_bytes()).digest()


def send(message):
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    with send_lock:
        conn.send_bytes(payload)


def clip(value):
    text = "" if value is None else str(value)
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + "\n...[truncated by Cinder-Connect]"


def blocked_shell(command, risk):
    if unsafe_mode:
        return False
    if str(risk).lower() in {"high", "critical", "destructive"}:
        return True
    lowered = command.lower()
    return any(pattern in lowered for pattern in DANGEROUS)
def result_base(command):
    return {
        "id": str(command.get("id", "")),
        "action": str(command.get("action", "")),
        "ok": False,
    }


def run_shell(command, result):
    text = str(command.get("command", ""))
    if not text:
        raise ValueError("shell.run requires command")
    if blocked_shell(text, command.get("risk")):
        result["blocked"] = True
        result["detail"] = "Blocked by local safety policy. Use /unsafe on to allow high-risk commands."
        return
    cwd = command.get("cwd") or None
    timeout = max(1, min(int(command.get("timeout_sec", 60)), 3600))
    shell_name = str(command.get("shell", "powershell")).lower()
    if shell_name == "cmd":
        argv = ["cmd.exe", "/d", "/s", "/c", text]
    else:
        argv = ["powershell.exe", "-NoLogo", "-NoProfile", "-Command", text]
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
    result.update(ok=completed.returncode == 0, exit_code=completed.returncode,
                  stdout=clip(completed.stdout), stderr=clip(completed.stderr))
def run_process_start(command, result):
    path = str(command.get("path", ""))
    if not path:
        raise ValueError("process.start requires path")
    args = [str(x) for x in (command.get("args") or [])]
    proc = subprocess.Popen([path, *args], cwd=command.get("cwd") or None)
    result.update(ok=True, pid=proc.pid)


def run_process_stop(command, result):
    pid = int(command.get("pid"))
    if not unsafe_mode and str(command.get("risk", "")).lower() in {"high", "critical"}:
        result.update(blocked=True, detail="Blocked by local safety policy.")
        return
    os.kill(pid, signal.SIGTERM)
    result.update(ok=True, pid=pid)


def run_file_read(command, result):
    path = Path(str(command.get("path", ""))).expanduser()
    max_chars = max(1, min(int(command.get("max_chars", 65536)), 262144))
    text = path.read_text(encoding=command.get("encoding", "utf-8"), errors="replace")
    result.update(ok=True, path=str(path), content=clip(text[:max_chars]),
                  truncated=len(text) > max_chars)
def run_file_write(command, result):
    path = Path(str(command.get("path", ""))).expanduser()
    content = str(command.get("content", ""))
    mode = str(command.get("mode", "overwrite")).lower()
    if command.get("create_parents", True):
        path.parent.mkdir(parents=True, exist_ok=True)
    encoding = command.get("encoding", "utf-8")
    if mode == "append":
        with path.open("a", encoding=encoding, newline="") as handle:
            handle.write(content)
    else:
        path.write_text(content, encoding=encoding)
    result.update(ok=True, path=str(path), chars_written=len(content), mode=mode)


def run_file_list(command, result):
    path = Path(str(command.get("path", "."))).expanduser()
    limit = max(1, min(int(command.get("limit", 200)), 1000))
    entries = []
    for item in list(path.iterdir())[:limit]:
        try:
            size = item.stat().st_size if item.is_file() else None
        except OSError:
            size = None
        entries.append({"name": item.name, "type": "dir" if item.is_dir() else "file", "size": size})
    result.update(ok=True, path=str(path), entries=entries)
def execute_command(command):
    result = result_base(command)
    try:
        action = result["action"]
        if action == "shell.run":
            run_shell(command, result)
        elif action == "process.start":
            run_process_start(command, result)
        elif action == "process.stop":
            run_process_stop(command, result)
        elif action == "file.read":
            run_file_read(command, result)
        elif action == "file.write":
            run_file_write(command, result)
        elif action == "file.list":
            run_file_list(command, result)
        else:
            result["detail"] = f"Unsupported action: {action}"
    except subprocess.TimeoutExpired as exc:
        result.update(detail=f"Command timed out after {exc.timeout}s", timed_out=True)
    except Exception as exc:
        result["detail"] = f"{type(exc).__name__}: {exc}"
    return result


def execute_batch(message):
    global command_busy
    command_busy = True
    try:
        commands = message.get("commands") or []
        results = [execute_command(command) for command in commands]
        send({"type": "command.batch_result", "batch_id": message.get("batch_id"),
              "conversation_id": message.get("conversation_id"), "results": results})
    finally:
        command_busy = False
def handle_message(message):
    global selected_chat
    msg_type = message.get("type")
    if msg_type == "bridge.accepted":
        binding = message.get("binding") or {}
        print(f"\n[Cinder-Connect] Bound PID {message.get('pid')} - {binding.get('state')}\n")
    elif msg_type == "bridge.rejected":
        print(f"\n[Cinder-Connect] REJECTED: {json.dumps(message, indent=2)}\n")
    elif msg_type == "chat.ready":
        chat = message.get("conversation_id")
        if chat:
            known_chats.add(chat)
            if selected_chat is None and len(known_chats) == 1:
                selected_chat = chat
            print(f"\n[chat ready] {chat}\n")
    elif msg_type == "assistant.reply":
        text = str(message.get("text") or "").strip()
        if text:
            print(f"\nCinder> {text}\n")
    elif msg_type == "command.batch":
        print(f"\n[commands] {len(message.get('commands') or [])} action(s)\n")
        execute_batch(message)
    elif msg_type == "chat.error":
        print(f"\n[chat error] {message.get('detail')}\n")
    elif msg_type == "bridge.status":
        print("\n" + json.dumps(message.get("binding"), indent=2) + "\n")
def reader_loop():
    try:
        while True:
            raw = conn.recv_bytes()
            handle_message(json.loads(raw.decode("utf-8")))
    except (EOFError, OSError, json.JSONDecodeError):
        print("\n[Cinder-Connect] bridge disconnected.\n")


def binding_targets_me():
    try:
        binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))
        return int(binding.get("pid", -1)) == os.getpid()
    except Exception:
        return False


def connect_bridge():
    global conn
    announced_binding_wait = False
    while True:
        if not binding_targets_me():
            if not announced_binding_wait:
                print("[Cinder-Connect] waiting for launcher to bind this PID...")
                announced_binding_wait = True
            time.sleep(0.05)
            continue
        try:
            conn = Client(PIPE_NAME, family="AF_PIPE", authkey=authkey())
            return
        except (FileNotFoundError, ConnectionRefusedError, OSError) as exc:
            print(f"[Cinder-Connect] waiting for Firefox bridge: {exc}")
            time.sleep(1)


def print_help():
    print("/status       show exact binding status")
    print("/chats        list ChatGPT conversation IDs")
    print("/use <id>     select a conversation")
    print("/unsafe on    allow locally flagged high-risk commands")
    print("/unsafe off   restore local high-risk blocking")
    print("/quit         exit terminal")
def main():
    global selected_chat, unsafe_mode
    print("Cinder-Connect Terminal")
    print(f"PID: {os.getpid()}")
    print("Connecting to Firefox native bridge...")
    connect_bridge()
    threading.Thread(target=reader_loop, name="cinder-reader", daemon=True).start()
    print_help()
    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/status":
            send({"type": "terminal.status"})
            continue
        if text == "/chats":
            print("\n".join(sorted(known_chats)) or "No chats connected yet.")
            continue
        if text.startswith("/use "):
            selected_chat = text[5:].strip()
            print(f"Selected chat: {selected_chat}")
            continue
        if text == "/unsafe on":
            unsafe_mode = True
            print("Local high-risk blocking disabled for this terminal session.")
            continue
        if text == "/unsafe off":
            unsafe_mode = False
            print("Local high-risk blocking enabled.")
            continue
        if text.startswith("/"):
            print_help()
            continue
        if command_busy:
            print("A command batch is still running; wait for its result before sending another turn.")
            continue
        send({"type": "terminal.chat", "conversation_id": selected_chat, "text": text})


if __name__ == "__main__":
    main()
