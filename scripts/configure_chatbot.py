"""Apply the reproducible Open WebUI Desktop boundary for this experiment."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


def desired_desktop_config(existing: dict[str, Any], install_dir: Path) -> dict[str, Any]:
    """Merge experiment-owned settings while preserving unrelated Desktop preferences."""
    result = dict(existing)
    result.update(
        {
            "version": 1,
            "defaultConnectionId": "local",
            "installDir": str(install_dir),
            "dataDir": str(install_dir / "data"),
            "localServer": {
                **existing.get("localServer", {}),
                "port": 8080,
                "serveOnLocalNetwork": False,
            },
            "openTerminal": {
                **existing.get("openTerminal", {}),
                "enabled": False,
            },
            "llamaCpp": {
                **existing.get("llamaCpp", {}),
                "enabled": False,
            },
            "envVars": {
                **existing.get("envVars", {}),
                "ENABLE_OPENAI_API": "True",
                "OPENAI_API_BASE_URLS": '["http://127.0.0.1:8000/v1"]',
                "OPENAI_API_KEYS": '["none"]',
                "ENABLE_WEB_SEARCH": "True",
                "WEB_SEARCH_ENGINE": "duckduckgo",
                "DDGS_BACKEND": "auto",
                "ENABLE_CODE_INTERPRETER": "False",
                "USER_PERMISSIONS_FEATURES_CODE_INTERPRETER": "False",
                "USER_PERMISSIONS_FEATURES_WEB_SEARCH": "True",
            },
        }
    )
    return result


def desired_backend_config(existing: dict[str, Any]) -> dict[str, Any]:
    """Return the narrow Open WebUI policy owned by this experiment."""
    permissions = dict(existing.get("user.permissions", {}))
    features = dict(permissions.get("features", {}))
    features.update({"web_search": True, "code_interpreter": False, "direct_tool_servers": False})
    permissions["features"] = features
    return {
        "openai.enable": True,
        "openai.api_base_urls": ["http://127.0.0.1:8000/v1"],
        "openai.api_keys": ["none"],
        "ollama.enable": False,
        "web.search.enable": True,
        "web.search.engine": "duckduckgo",
        "web.search.ddgs_backend": "auto",
        "code_interpreter.enable": False,
        "code_execution.enable": False,
        "subagents.enable": False,
        "subagents.background_enabled": False,
        "terminal_server.connections": [],
        "tool_server.connections": [],
        "user.permissions": permissions,
    }


def configure_backend_database(database: Path) -> None:
    """Update only policy keys in an initialized Open WebUI database."""
    if not database.exists():
        print(f"Backend database not initialized yet: {database}")
        return
    connection = sqlite3.connect(database)
    try:
        existing = {
            key: json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value
            for key, value in connection.execute("SELECT key, value FROM config")
        }
        timestamp = int(time.time())
        for key, value in desired_backend_config(existing).items():
            connection.execute(
                """
                INSERT INTO config(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, json.dumps(value), timestamp),
            )
        connection.commit()
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", type=Path, default=Path(r"D:\OpenWebUI"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ["APPDATA"]) / "open-webui" / "config.json",
    )
    args = parser.parse_args()

    existing: dict[str, Any] = {}
    if args.config.exists():
        existing = json.loads(args.config.read_text(encoding="utf-8"))
    for directory in (args.install_dir, args.install_dir / "data", args.install_dir / "tmp", args.install_dir / "uv-cache"):
        directory.mkdir(parents=True, exist_ok=True)
    args.config.parent.mkdir(parents=True, exist_ok=True)
    args.config.write_text(
        json.dumps(desired_desktop_config(existing, args.install_dir), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Configured Open WebUI Desktop at {args.config}")
    configure_backend_database(args.install_dir / "data" / "webui.db")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
