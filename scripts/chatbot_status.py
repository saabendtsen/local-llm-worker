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
    ui_listeners: list[str],
    serve_routes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate observable service state without mutating it."""
    problems: list[str] = []
    if "local-worker" not in llama_models:
        problems.append("local-worker model is unavailable")
    if not llama_listeners or any(address not in {"127.0.0.1", "::1"} for address in llama_listeners):
        problems.append("llama.cpp is not loopback-only")
    if not ui_healthy:
        problems.append("Open WebUI is unavailable")
    if not ui_listeners or any(address not in {"127.0.0.1", "::1"} for address in ui_listeners):
        problems.append("Open WebUI is not loopback-only")
    llama_routed = any(route.get("proxy") == "http://127.0.0.1:8000" for route in serve_routes)
    if llama_routed:
        problems.append("Tailscale exposes llama.cpp directly")
    ui_routed = any(
        route.get("https_port") == 443
        and str(route.get("host", "")).endswith(".ts.net")
        and route.get("proxy") == "http://127.0.0.1:8080"
        for route in serve_routes
    )
    if not ui_routed:
        problems.append("Open WebUI has no exact Tailscale HTTPS route")
    return {
        "healthy": not problems,
        "llama_models": llama_models,
        "llama_listeners": llama_listeners,
        "open_webui": ui_healthy,
        "ui_listeners": ui_listeners,
        "phone_route": "tailnet-only" if ui_routed and not llama_routed else "unsafe-or-missing",
        "serve_routes": serve_routes,
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


def _listeners(port: int) -> list[str]:
    command = (
        f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue "
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


def _llama_listeners() -> list[str]:
    return _listeners(8000)


def _ui_healthy() -> bool:
    try:
        payload = _get_json(OPEN_WEBUI_HEALTH_URL)
    except (OSError, URLError, ValueError):
        return False
    return payload.get("status") is True


def _serve_routes() -> list[dict[str, Any]]:
    proc = subprocess.run(
        ["tailscale.exe", "serve", "status", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode:
        return []
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        return []
    routes: list[dict[str, Any]] = []
    for endpoint, web_config in payload.get("Web", {}).items():
        host, separator, port_text = endpoint.rpartition(":")
        if not separator or not isinstance(web_config, dict):
            continue
        try:
            https_port = int(port_text)
        except ValueError:
            continue
        for handler in web_config.get("Handlers", {}).values():
            if isinstance(handler, dict) and isinstance(handler.get("Proxy"), str):
                routes.append({"host": host, "https_port": https_port, "proxy": handler["Proxy"]})
    return routes


def main() -> int:
    result = evaluate_status(
        llama_models=_llama_models(),
        llama_listeners=_llama_listeners(),
        ui_healthy=_ui_healthy(),
        ui_listeners=_listeners(8080),
        serve_routes=_serve_routes(),
    )
    print(json.dumps(result, indent=2))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
