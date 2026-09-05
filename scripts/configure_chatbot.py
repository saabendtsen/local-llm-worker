"""Apply the reproducible Open WebUI Desktop boundary for this experiment."""

from __future__ import annotations

import argparse
import json
import os
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
        }
    )
    return result


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
