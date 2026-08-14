import ctypes
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from multiprocessing.connection import Client
from pathlib import Path

ROOT = Path(r"C:\Projects\Cinder-Connect")
HOST = ROOT / "native-host" / "native_host.py"
PIPE = rf"\\.\pipe\CinderConnectTest{os.getpid()}"

class FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

def current_start_filetime():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.GetProcessTimes.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME)
    ]
    handle = k32.OpenProcess(0x1000, False, os.getpid())
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        created = FILETIME(); exited = FILETIME(); kernel = FILETIME(); user = FILETIME()
        if not k32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            raise ctypes.WinError(ctypes.get_last_error())
        return (int(created.high) << 32) | int(created.low)
    finally:
        k32.CloseHandle(handle)
def recv_json(conn):
    return json.loads(conn.recv_bytes().decode("utf-8"))


def connect_with_retry(authkey):
    last = None
    for _ in range(50):
        try:
            return Client(PIPE, family="AF_PIPE", authkey=authkey)
        except OSError as exc:
            last = exc
            time.sleep(0.05)
    raise last


def main():
    with tempfile.TemporaryDirectory(prefix="cinder-test-") as temp:
        temp = Path(temp)
        binding = temp / "binding.json"
        secret = temp / "secret.bin"
        seen = temp / "seen.json"
        binding.write_text(json.dumps({
            "version": 2,
            "pid": os.getpid(),
            "exe_path": sys.executable,
            "start_filetime_utc": current_start_filetime(),
            "binding_id": "pipe-test",
            "bound_utc": "test"
        }), encoding="utf-8")
        env = os.environ.copy()
        env.update({
            "CINDER_BINDING_PATH": str(binding),
            "CINDER_SECRET_PATH": str(secret),
            "CINDER_SEEN_PATH": str(seen),
            "CINDER_PIPE_NAME": PIPE,
        })
        host = subprocess.Popen(
            [sys.executable, "-u", str(HOST)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        try:
            for _ in range(50):
                if secret.exists():
                    break
                time.sleep(0.05)
            if not secret.exists():
                raise RuntimeError("Native host did not create bridge secret")
            auth = hashlib.sha256(secret.read_bytes()).digest()

            conn = connect_with_retry(auth)
            accepted = recv_json(conn)
            print(json.dumps(accepted, indent=2))
            assert accepted["type"] == "bridge.accepted"
            assert accepted["pid"] == os.getpid()
            conn.send_bytes(json.dumps({"type": "terminal.status"}).encode("utf-8"))
            status = recv_json(conn)
            print(json.dumps(status, indent=2))
            assert status["type"] == "bridge.status"
            assert status["binding"]["ok"] is True
            assert status["binding"]["terminal_pid"] == os.getpid()
            conn.close()

            child_code = (
                "import hashlib,json,os; from multiprocessing.connection import Client; "
                "from pathlib import Path; "
                "a=hashlib.sha256(Path(os.environ['CINDER_SECRET_PATH']).read_bytes()).digest(); "
                "c=Client(os.environ['CINDER_PIPE_NAME'],family='AF_PIPE',authkey=a); "
                "print(c.recv_bytes().decode())"
            )
            child = subprocess.run([sys.executable, "-c", child_code], env=env,
                                   capture_output=True, text=True, timeout=10)
            print(child.stdout.strip())
            rejected = json.loads(child.stdout.strip())
            assert rejected["type"] == "bridge.rejected"
            assert rejected["client_pid"] != os.getpid()
            print("PIPE_BRIDGE_OK")
        finally:
            host.terminate()
            try:
                host.wait(timeout=5)
            except subprocess.TimeoutExpired:
                host.kill()

if __name__ == "__main__":
    main()
