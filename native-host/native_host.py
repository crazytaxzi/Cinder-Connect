import ctypes
import hashlib
import json
import os
import struct
import sys
import threading
from ctypes import wintypes
from multiprocessing.connection import Listener
from pathlib import Path

BASE = Path(os.environ.get("LOCALAPPDATA", ".")) / "CinderConnect"
BINDING_PATH = Path(os.environ.get("CINDER_BINDING_PATH", BASE / "binding.json"))
SEEN_PATH = Path(os.environ.get("CINDER_SEEN_PATH", BASE / "extension_seen.json"))
SECRET_PATH = Path(os.environ.get("CINDER_SECRET_PATH", BASE / "bridge_secret.bin"))
PIPE_NAME = os.environ.get("CINDER_PIPE_NAME", r"\\.\pipe\CinderConnect")
MAX_NATIVE = 4 * 1024 * 1024

stdout_lock = threading.Lock()
terminal_lock = threading.Lock()
terminal_conn = None
terminal_pid = None
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD)]

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
    ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME)
]
kernel32.GetNamedPipeClientProcessId.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)
]
def _filetime_value(ft):
    return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)


def query_process(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        created = FILETIME(); exited = FILETIME(); kernel = FILETIME(); user = FILETIME()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        path = ""
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            path = buf.value
        return {"pid": int(pid), "start_filetime_utc": _filetime_value(created), "exe_path": path}
    finally:
        kernel32.CloseHandle(handle)
def load_binding():
    try:
        return json.loads(BINDING_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": str(exc)}


def binding_status():
    binding = load_binding()
    if "_error" in binding:
        state = "not_bound" if not BINDING_PATH.exists() else "bad_binding"
        return {"ok": False, "state": state, "detail": binding["_error"]}
    try:
        pid = int(binding["pid"])
        expected_start = int(binding["start_filetime_utc"])
        expected_path = os.path.normcase(os.path.abspath(binding["exe_path"]))
    except Exception as exc:
        return {"ok": False, "state": "bad_binding", "detail": str(exc)}

    live = query_process(pid)
    if live is None:
        return {"ok": False, "state": "stale_pid", "pid": pid, "detail": "Bound process is not queryable or no longer running."}
    if live["start_filetime_utc"] != expected_start:
        return {"ok": False, "state": "start_time_mismatch", "pid": pid, "detail": "PID was reused by a newer process."}
    actual_path = live.get("exe_path") or ""
    if actual_path:
        actual_norm = os.path.normcase(os.path.abspath(actual_path))
        if actual_norm != expected_path:
            return {"ok": False, "state": "path_mismatch", "pid": pid, "exe_path": actual_path}
    status = {
        "ok": True, "state": "attached", "pid": pid,
        "exe_path": actual_path or binding["exe_path"],
        "path_verified": bool(actual_path),
        "binding_id": str(binding.get("binding_id", "")),
        "bound_utc": str(binding.get("bound_utc", "")),
    }
    with terminal_lock:
        status["terminal_connected"] = terminal_conn is not None
        status["terminal_pid"] = terminal_pid
    return add_extension_presence(status)
def write_extension_seen(status):
    BASE.mkdir(parents=True, exist_ok=True)
    record = {
        "last_seen_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "state": status.get("state"),
        "pid": status.get("pid"),
        "binding_id": status.get("binding_id"),
    }
    SEEN_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def add_extension_presence(status):
    if not SEEN_PATH.exists():
        status["extension_seen"] = False
        return status
    try:
        seen = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        status["extension_seen"] = True
        status["extension_last_seen_utc"] = seen.get("last_seen_utc")
        status["extension_last_state"] = seen.get("state")
        status["extension_last_binding_id"] = seen.get("binding_id")
    except Exception:
        status["extension_seen"] = False
    return status
def read_native_message():
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len:
        return None
    length = struct.unpack("<I", raw_len)[0]
    if length > MAX_NATIVE:
        raise ValueError("Native message exceeds 4 MiB")
    payload = sys.stdin.buffer.read(length)
    if len(payload) != length:
        return None
    return json.loads(payload.decode("utf-8"))


def write_native_message(message):
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    packet = struct.pack("<I", len(payload)) + payload
    with stdout_lock:
        sys.stdout.buffer.write(packet)
        sys.stdout.buffer.flush()


def load_secret():
    BASE.mkdir(parents=True, exist_ok=True)
    if not SECRET_PATH.exists():
        SECRET_PATH.write_bytes(os.urandom(32))
    return hashlib.sha256(SECRET_PATH.read_bytes()).digest()
def pipe_client_pid(conn):
    pid = wintypes.DWORD()
    handle = wintypes.HANDLE(conn.fileno())
    if not kernel32.GetNamedPipeClientProcessId(handle, ctypes.byref(pid)):
        return None
    return int(pid.value)


def send_terminal(message):
    global terminal_conn
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    with terminal_lock:
        conn = terminal_conn
    if conn is None:
        return False
    try:
        conn.send_bytes(payload)
        return True
    except Exception:
        with terminal_lock:
            if terminal_conn is conn:
                terminal_conn = None
        return False


def recv_terminal(conn):
    raw = conn.recv_bytes(MAX_NATIVE)
    return json.loads(raw.decode("utf-8"))
def terminal_session(conn):
    global terminal_conn, terminal_pid
    pid = pipe_client_pid(conn)
    status = binding_status()
    if not status.get("ok") or pid != status.get("pid"):
        rejection = {"type": "bridge.rejected", "client_pid": pid, "binding": status}
        conn.send_bytes(json.dumps(rejection).encode("utf-8"))
        conn.close()
        return
    with terminal_lock:
        terminal_conn = conn
        terminal_pid = pid
    accepted = {"type": "bridge.accepted", "pid": pid, "binding": binding_status()}
    conn.send_bytes(json.dumps(accepted).encode("utf-8"))
    write_native_message({"type": "terminal.connected", "pid": pid})
    try:
        while True:
            message = recv_terminal(conn)
            if message.get("type") == "terminal.status":
                send_terminal({"type": "bridge.status", "binding": binding_status()})
            else:
                write_native_message(message)
    except (EOFError, OSError, ValueError, json.JSONDecodeError):
        pass
    finally:
        with terminal_lock:
            if terminal_conn is conn:
                terminal_conn = None
                terminal_pid = None
        try:
            conn.close()
        except Exception:
            pass
        write_native_message({"type": "terminal.disconnected", "pid": pid})


def pipe_server():
    authkey = load_secret()
    while True:
        listener = Listener(PIPE_NAME, family="AF_PIPE", authkey=authkey)
        try:
            conn = listener.accept()
            terminal_session(conn)
        except Exception as exc:
            try:
                write_native_message({"type": "bridge.error", "detail": str(exc)})
            except Exception:
                pass
        finally:
            listener.close()
def handle_native(message):
    msg_type = message.get("type")
    if msg_type == "rpc.request":
        request_id = message.get("request_id")
        method = message.get("method")
        if method in {"status", "extension_status"}:
            status = binding_status()
            if method == "extension_status":
                write_extension_seen(status)
                status = binding_status()
            write_native_message({"type": "rpc.result", "request_id": request_id, "result": status})
            return
        write_native_message({"type": "rpc.result", "request_id": request_id,
                              "error": f"Unsupported method: {method}"})
        return
    if msg_type == "extension.hello":
        status = binding_status()
        write_extension_seen(status)
        write_native_message({"type": "extension.hello.ack", "binding": binding_status()})
        return
    if msg_type == "assistant.reply":
        send_terminal({k: v for k, v in message.items() if k != "commands"})
        commands = message.get("commands") or []
        if commands:
            send_terminal({"type": "command.batch", "batch_id": message.get("batch_id"),
                           "conversation_id": message.get("conversation_id"), "commands": commands})
        return
    if msg_type in {"chat.ready", "chat.sent", "chat.error", "bridge.notice"}:
        send_terminal(message)
        return
    send_terminal({"type": "bridge.notice", "detail": f"Unhandled extension message: {msg_type}"})


def main():
    threading.Thread(target=pipe_server, name="cinder-pipe", daemon=True).start()
    while True:
        try:
            message = read_native_message()
        except Exception as exc:
            write_native_message({"type": "bridge.error", "detail": str(exc)})
            continue
        if message is None:
            break
        handle_native(message)


if __name__ == "__main__":
    main()
