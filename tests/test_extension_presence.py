import json
import os
import struct
import subprocess
from pathlib import Path

HOST = Path(os.environ["LOCALAPPDATA"]) / "CinderConnect" / "native-host" / "cinder_connect_host.bat"


def call(command):
    raw = json.dumps({"command": command}, separators=(",", ":")).encode()
    packet = struct.pack("<I", len(raw)) + raw
    proc = subprocess.Popen([str(HOST)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out, _ = proc.communicate(packet, timeout=10)
    size = struct.unpack("<I", out[:4])[0]
    return json.loads(out[4:4 + size])


extension_reply = call("extension_status")
backend_reply = call("status")
print(json.dumps({
    "extension_reply": extension_reply,
    "backend_reply": backend_reply,
}, indent=2))
assert backend_reply.get("extension_seen") is True
assert backend_reply.get("extension_last_seen_utc")
