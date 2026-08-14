import json
import os
import struct
import subprocess
from pathlib import Path

host = Path(os.environ["LOCALAPPDATA"]) / "CinderConnect" / "native-host" / "cinder_connect_host.bat"
message = json.dumps({"command": "status"}, separators=(",", ":")).encode("utf-8")
packet = struct.pack("<I", len(message)) + message

proc = subprocess.Popen(
    [str(host)],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
out, err = proc.communicate(packet, timeout=10)
if len(out) < 4:
    raise SystemExit(f"No native reply. stderr={err.decode(errors='replace')}")
length = struct.unpack("<I", out[:4])[0]
reply = json.loads(out[4:4 + length].decode("utf-8"))
print(json.dumps(reply, indent=2))
