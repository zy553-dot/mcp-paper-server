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
        sys.exit(f"找不到虚拟环境: {python_path}\n先运行 uv venv 并安装依赖。")

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
        sys.exit(f"找不到 Claude Desktop 配置文件:\n{CONFIG_PATH}\n请先至少启动一次 Claude Desktop。")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    backup = CONFIG_PATH.with_suffix(
        f".backup-{datetime.now():%Y%m%d-%H%M%S}.json"
    )
    shutil.copy2(CONFIG_PATH, backup)
    print(f"已备份原配置到:\n  {backup}\n")

    servers = config.setdefault("mcpServers", {})
    entry = build_entry()
    action = "更新" if SERVER_NAME in servers else "新增"
    servers[SERVER_NAME] = entry

    CONFIG_PATH.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"已{action} MCP 服务器 '{SERVER_NAME}':")
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    print(f"\n配置文件里现有的服务器: {', '.join(servers) or '(无)'}")
    print("\n下一步: 完全退出 Claude Desktop（Command+Q，不是关窗口）再重新打开。")


if __name__ == "__main__":
    main()
