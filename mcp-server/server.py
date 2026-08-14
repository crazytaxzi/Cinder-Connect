import json
import os
import struct
import subprocess
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

HOST = (
    Path(os.environ["LOCALAPPDATA"])
    / "CinderConnect"
    / "native-host"
    / "cinder_connect_host.bat"
)

mcp = MCPServer(
    "Cinder Connect",
    instructions=(
        "Read-only bridge to the exact Windows process identity "
        "verified by the Cinder Connect Firefox native host."
    ),
)
def query_native_host() -> dict:
    if not HOST.is_file():
        return {
            "ok": False,
            "state": "native_host_missing",
            "detail": f"Native host launcher not found: {HOST}",
        }

    message = json.dumps(
        {"command": "status"}, separators=(",", ":")
    ).encode("utf-8")
    packet = struct.pack("<I", len(message)) + message

    proc = subprocess.Popen(
        [str(HOST)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate(packet, timeout=10)

    if len(out) < 4:
        return {
            "ok": False,
            "state": "native_host_error",
            "detail": err.decode(errors="replace") or "No native reply.",
        }
    length = struct.unpack("<I", out[:4])[0]
    payload = out[4:4 + length]
    if len(payload) != length:
        return {
            "ok": False,
            "state": "native_host_error",
            "detail": "Native reply was truncated.",
        }

    return json.loads(payload.decode("utf-8"))


@mcp.tool(
    name="cinder_status",
    title="Cinder Connect Status",
    description=(
        "Read the exact process-binding status currently verified by "
        "the Cinder Connect Firefox native-messaging host."
    ),
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        destructiveHint=False,
        openWorldHint=False,
    ),
)
def cinder_status() -> dict:
    """Return the current exact PID/process binding status."""
    return query_native_host()

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8765,
        stateless_http=True,
        json_response=True,
    )
