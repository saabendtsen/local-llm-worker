"""Public-seam tests for the phone-friendly chatbot entrypoints."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class StartChatbotTests(unittest.TestCase):
    def test_dry_run_starts_existing_runtime_and_open_webui_without_public_exposure(self):
        proc = subprocess.run(
            ["cmd.exe", "/d", "/c", str(SCRIPTS / "start-chatbot.cmd"), "--dry-run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        output = proc.stdout.lower()
        self.assertIn("start-worker.cmd", output)
        self.assertIn(r"programs\open-webui\open-webui.exe", output)
        self.assertNotIn("tailscale funnel", output)
        self.assertNotIn("0.0.0.0:8000", output)

    def test_setup_dry_run_is_reproducible_and_routes_only_the_ui(self):
        proc = subprocess.run(
            ["cmd.exe", "/d", "/c", str(SCRIPTS / "setup-chatbot.cmd"), "--dry-run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        output = proc.stdout.lower()
        self.assertIn("openwebui.openwebui", output)
        self.assertIn("configure_chatbot.py", output)
        self.assertIn("tailscale serve", output)
        self.assertIn("8080", output)
        self.assertNotIn("tailscale funnel", output)
        self.assertNotIn("serve --bg 8000", output)

    def test_desktop_config_disables_extra_tools_and_lan_listener(self):
        from configure_chatbot import desired_desktop_config

        existing = {"unrelated": "preserved", "openTerminal": {"enabled": True}}
        result = desired_desktop_config(existing, Path(r"D:\OpenWebUI"))

        self.assertEqual(result["unrelated"], "preserved")
        self.assertEqual(result["installDir"], r"D:\OpenWebUI")
        self.assertFalse(result["localServer"]["serveOnLocalNetwork"])
        self.assertFalse(result["openTerminal"]["enabled"])
        self.assertFalse(result["llamaCpp"]["enabled"])


class ChatbotStatusTests(unittest.TestCase):
    def test_healthy_requires_both_services_and_private_tailnet_ui_route(self):
        from chatbot_status import evaluate_status

        result = evaluate_status(
            llama_models=["local-worker"],
            llama_listeners=["127.0.0.1"],
            ui_healthy=True,
            ui_listeners=["127.0.0.1"],
            serve_routes=[
                {
                    "host": "desktop.example.ts.net",
                    "https_port": 443,
                    "proxy": "http://127.0.0.1:8080",
                }
            ],
        )

        self.assertTrue(result["healthy"])
        self.assertEqual(result["phone_route"], "tailnet-only")

    def test_public_or_direct_llama_route_is_rejected(self):
        from chatbot_status import evaluate_status

        result = evaluate_status(
            llama_models=["local-worker"],
            llama_listeners=["0.0.0.0"],
            ui_healthy=True,
            ui_listeners=["0.0.0.0"],
            serve_routes=[
                {
                    "host": "desktop.example.ts.net",
                    "https_port": 443,
                    "proxy": "http://127.0.0.1:8000",
                }
            ],
        )

        self.assertFalse(result["healthy"])
        self.assertIn("llama.cpp is not loopback-only", result["problems"])
        self.assertIn("Open WebUI is not loopback-only", result["problems"])
        self.assertIn("Tailscale exposes llama.cpp directly", result["problems"])

    def test_inexact_or_non_https_ui_route_is_rejected(self):
        from chatbot_status import evaluate_status

        result = evaluate_status(
            llama_models=["local-worker"],
            llama_listeners=["127.0.0.1"],
            ui_healthy=True,
            ui_listeners=["127.0.0.1"],
            serve_routes=[
                {
                    "host": "desktop.example.ts.net",
                    "https_port": 80,
                    "proxy": "http://0.0.0.0:8080",
                }
            ],
        )

        self.assertFalse(result["healthy"])
        self.assertIn("Open WebUI has no exact Tailscale HTTPS route", result["problems"])

    @patch("chatbot_status.subprocess.run")
    def test_malformed_listener_output_fails_closed(self, run):
        from chatbot_status import _llama_listeners

        run.return_value = subprocess.CompletedProcess([], 0, stdout="not-json", stderr="")

        self.assertEqual(_llama_listeners(), [])


if __name__ == "__main__":
    unittest.main()
