"""Check the local chatbot stack and its network boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

LLAMA_MODELS_URL = "http://127.0.0.1:8000/v1/models"
OPEN_WEBUI_HEALTH_URL = "http://127.0.0.1:8080/health"


def evaluate_status(
    *,
    llama_models: list[str],
    llama_listeners: list[str],
    ui_healthy: bool,
    serve_targets: list[str],
) -> dict[str, Any]:
    """Evaluate observable service state without mutating it."""
    problems: list[str] = []
    if "local-worker" not in llama_models:
        problems.append("local-worker model is unavailable")
    if not llama_listeners or any(address not in {"127.0.0.1", "::1"} for address in llama_listeners):
        problems.append("llama.cpp is not loopback-only")
    if not ui_healthy:
        problems.append("Open WebUI is unavailable")
    if any(":8000" in target for target in serve_targets):
        problems.append("Tailscale exposes llama.cpp directly")
    ui_routed = any(":8080" in target for target in serve_targets)
    if not ui_routed:
        problems.append("Open WebUI has no Tailscale Serve route")
    return {
        "healthy": not problems,
        "llama_models": llama_models,
        "llama_listeners": llama_listeners,
        "open_webui": ui_healthy,
        "phone_route": "tailnet-only" if ui_routed and not any(":8000" in x for x in serve_targets) else "unsafe-or-missing",
        "serve_targets": serve_targets,
        "problems": problems,
    }


def _get_json(url: str) -> Any:
    with urlopen(url, timeout=5) as response:
        return json.load(response)


def _llama_models() -> list[str]:
    try:
        payload = _get_json(LLAMA_MODELS_URL)
    except (OSError, URLError, ValueError):
        return []
    return [str(item.get("id")) for item in payload.get("data", []) if isinstance(item, dict)]


def _llama_listeners() -> list[str]:
    command = (
        "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue "
        "| Select-Object -ExpandProperty LocalAddress | ConvertTo-Json -Compress"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode or not proc.stdout.strip():
        return []
    try:
        parsed = json.loads(proc.stdout)
    except ValueError:
        return []
    return [str(parsed)] if isinstance(parsed, str) else [str(value) for value in parsed]


def _ui_healthy() -> bool:
    try:
        payload = _get_json(OPEN_WEBUI_HEALTH_URL)
    except (OSError, URLError, ValueError):
        return False
    return payload.get("status") is True


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    return []


def _serve_targets() -> list[str]:
    proc = subprocess.run(
        ["tailscale.exe", "serve", "status", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode:
        return []
    try:
        return [value for value in _strings(json.loads(proc.stdout)) if value.startswith("http")]
    except ValueError:
        return []


def main() -> int:
    result = evaluate_status(
        llama_models=_llama_models(),
        llama_listeners=_llama_listeners(),
        ui_healthy=_ui_healthy(),
        serve_targets=_serve_targets(),
    )
    print(json.dumps(result, indent=2))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
