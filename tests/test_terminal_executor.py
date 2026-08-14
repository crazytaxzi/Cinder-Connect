import importlib.util
import tempfile
from pathlib import Path

MODULE = Path(r"C:\Projects\Cinder-Connect\terminal\cinder_terminal.py")
spec = importlib.util.spec_from_file_location("cinder_terminal", MODULE)
term = importlib.util.module_from_spec(spec)
spec.loader.exec_module(term)

with tempfile.TemporaryDirectory(prefix="cinder-exec-") as temp:
    root = Path(temp)
    target = root / "sample.txt"

    wrote = term.execute_command({
        "id": "write-1", "action": "file.write",
        "path": str(target), "content": "hello bridge"
    })
    assert wrote["ok"] is True and target.exists()

    read = term.execute_command({
        "id": "read-1", "action": "file.read", "path": str(target)
    })
    assert read["ok"] is True and read["content"] == "hello bridge"
    listed = term.execute_command({
        "id": "list-1", "action": "file.list", "path": str(root)
    })
    assert listed["ok"] is True
    assert any(item["name"] == "sample.txt" for item in listed["entries"])

    shell = term.execute_command({
        "id": "shell-1", "action": "shell.run",
        "command": "Write-Output 'bridge-shell-ok'"
    })
    assert shell["ok"] is True
    assert "bridge-shell-ok" in shell["stdout"]

    blocked = term.execute_command({
        "id": "danger-1", "action": "shell.run",
        "command": "git reset --hard", "risk": "high"
    })
    assert blocked["ok"] is False and blocked.get("blocked") is True

print("TERMINAL_EXECUTOR_OK")
