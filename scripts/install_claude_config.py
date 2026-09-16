"""Merge this server's entry into the local Claude Desktop config.

Claude Desktop keeps one config file holding both its own preferences and every
MCP server it launches. Overwriting that file would wipe the user's settings, so
this script reads it, adds one key, and writes it back - after taking a backup.

Run from the project root:
    python scripts/install_claude_config.py

macOS config location documented at:
https://modelcontextprotocol.io/quickstart/user
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_NAME = "paper-server"

CONFIG_PATH = (
    Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
)


def build_entry() -> dict:
    """Absolute paths, resolved from where this project actually sits.

    Claude Desktop launches the server as a child process with a minimal
    environment and an unpredictable working directory, so nothing here can be
    relative and nothing can rely on a virtualenv being "activated".
    """
    python_path = PROJECT_ROOT / ".venv" / "bin" / "python"
    if not python_path.exists():
        sys.exit(
            f"Virtual environment not found at {python_path}\n"
            "Run 'uv venv' and install requirements.txt first."
        )

    return {
        "command": str(python_path),
        "args": ["-m", "paper_server.server"],
        "cwd": str(PROJECT_ROOT),
        # PYTHONPATH is the belt to cwd's braces: "python -m paper_server.server"
        # needs the project root importable, and not every client honours cwd.
        "env": {"PYTHONPATH": str(PROJECT_ROOT)},
    }


def main() -> None:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"Claude Desktop config not found at:\n{CONFIG_PATH}\n"
            "Launch Claude Desktop at least once, then run this again."
        )

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    backup = CONFIG_PATH.with_suffix(
        f".backup-{datetime.now():%Y%m%d-%H%M%S}.json"
    )
    shutil.copy2(CONFIG_PATH, backup)
    print(f"Backed up the existing config to:\n  {backup}\n")

    servers = config.setdefault("mcpServers", {})
    entry = build_entry()
    action = "Updated" if SERVER_NAME in servers else "Added"
    servers[SERVER_NAME] = entry

    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"{action} MCP server '{SERVER_NAME}':")
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"\nServers now configured: {', '.join(servers) or '(none)'}")
    print("\nNext: quit Claude Desktop completely (Cmd+Q, not just the window), then reopen it.")


if __name__ == "__main__":
    main()
