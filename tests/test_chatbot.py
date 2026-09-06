"""Public-seam tests for the phone-friendly chatbot entrypoints."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
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

    def test_desktop_and_backend_policy(self):
        from configure_chatbot import desired_backend_config, desired_desktop_config

        result = desired_desktop_config(
            {"unrelated": "preserved", "openTerminal": {"enabled": True}},
            Path(r"D:\OpenWebUI"),
        )
        self.assertEqual(result["unrelated"], "preserved")
        self.assertFalse(result["localServer"]["serveOnLocalNetwork"])
        self.assertFalse(result["openTerminal"]["enabled"])
        self.assertFalse(result["llamaCpp"]["enabled"])
        self.assertEqual(result["envVars"]["ENABLE_WEB_SEARCH"], "True")
        self.assertEqual(result["envVars"]["WEB_SEARCH_ENGINE"], "duckduckgo")
        self.assertEqual(result["envVars"]["ENABLE_SUBAGENTS"], "True")
        self.assertEqual(result["envVars"]["SUBAGENTS_BACKGROUND_ENABLED"], "False")
        self.assertEqual(result["envVars"]["SUBAGENTS_MAX_CONCURRENT"], "1")
        self.assertEqual(result["envVars"]["ENABLE_CODE_INTERPRETER"], "False")

        backend = desired_backend_config(
            {
                "models.default_metadata": {
                    "capabilities": {"vision": True},
                    "prompt_suggestions": [{"title": "Keep me"}],
                },
                "models.default_params": {"temperature": 0.4},
                "ui.default_interface_settings": {"theme": "dark"},
                "user.permissions": {"features": {"notes": True, "code_interpreter": True}},
            }
        )
        self.assertEqual(backend["openai.api_base_urls"], ["http://127.0.0.1:8000/v1"])
        self.assertTrue(backend["web.search.enable"])
        self.assertFalse(backend["code_interpreter.enable"])
        self.assertFalse(backend["code_execution.enable"])
        self.assertTrue(backend["subagents.enable"])
        self.assertFalse(backend["subagents.background_enabled"])
        self.assertEqual(backend["subagents.max_concurrent"], 1)
        self.assertEqual(backend["subagents.max_async"], 1)
        self.assertEqual(backend["subagents.max_iterations"], 8)
        self.assertEqual(backend["subagents.max_output"], 12000)
        self.assertTrue(backend["models.default_metadata"]["capabilities"]["web_search"])
        self.assertTrue(backend["models.default_metadata"]["capabilities"]["vision"])
        self.assertEqual(backend["models.default_metadata"]["defaultFeatureIds"], ["web_search"])
        self.assertEqual(backend["models.default_metadata"]["prompt_suggestions"], [{"title": "Keep me"}])
        self.assertEqual(backend["models.default_params"], {"temperature": 0.4, "function_calling": "native"})
        self.assertEqual(backend["ui.default_interface_settings"], {"theme": "dark", "webSearch": "always"})
        self.assertFalse(backend["user.permissions"]["features"]["code_interpreter"])
        self.assertTrue(backend["user.permissions"]["features"]["web_search"])
        self.assertTrue(backend["user.permissions"]["features"]["notes"])

    def test_backend_config_accepts_native_sqlite_json_scalars(self):
        from configure_chatbot import configure_backend_database

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "webui.db"
            connection = sqlite3.connect(database)
            try:
                connection.execute(
                    "CREATE TABLE config(key TEXT PRIMARY KEY, value JSON NOT NULL, updated_at BIGINT)"
                )
                connection.execute("INSERT INTO config VALUES ('numeric.setting', 40, 0)")
                connection.execute(
                    "INSERT INTO config VALUES ('user.permissions', ?, 0)",
                    ('{"features":{"notes":true,"code_interpreter":true}}',),
                )
                connection.commit()
            finally:
                connection.close()
            configure_backend_database(database)
            connection = sqlite3.connect(database)
            try:
                values = dict(connection.execute("SELECT key, value FROM config"))
            finally:
                connection.close()
            self.assertEqual(values["openai.api_base_urls"], '["http://127.0.0.1:8000/v1"]')
            self.assertEqual(values["code_interpreter.enable"], "false")
            self.assertEqual(values["subagents.enable"], "true")
            self.assertEqual(values["subagents.max_concurrent"], 1)
            self.assertEqual(json.loads(values["models.default_metadata"]), {"capabilities": {"web_search": True}, "defaultFeatureIds": ["web_search"]})
            self.assertEqual(json.loads(values["models.default_params"]), {"function_calling": "native"})
            self.assertEqual(json.loads(values["ui.default_interface_settings"]), {"webSearch": "always"})


class ChatbotStatusTests(unittest.TestCase):
    def _healthy_routes(self):
        return [{"host": "desktop.example.ts.net", "https_port": 443, "https": True, "funnel": False, "proxy": "http://127.0.0.1:8080"}]

    def test_healthy_requires_both_services_and_private_tailnet_ui_route(self):
        from chatbot_status import evaluate_status

        result = evaluate_status(llama_models=["local-worker"], llama_listeners=["127.0.0.1"], ui_healthy=True, ui_listeners=["127.0.0.1"], serve_routes=self._healthy_routes())
        self.assertTrue(result["healthy"])
        self.assertEqual(result["phone_route"], "tailnet-only")

    def test_public_or_direct_llama_route_is_rejected(self):
        from chatbot_status import evaluate_status

        routes = [{"host": "desktop.example.ts.net", "https_port": 443, "https": True, "funnel": False, "proxy": "http://127.0.0.1:8000"}]
        result = evaluate_status(llama_models=["local-worker"], llama_listeners=["0.0.0.0"], ui_healthy=True, ui_listeners=["0.0.0.0"], serve_routes=routes)
        self.assertFalse(result["healthy"])
        self.assertIn("llama.cpp is not loopback-only", result["problems"])
        self.assertIn("Open WebUI is not loopback-only", result["problems"])
        self.assertIn("Tailscale exposes llama.cpp directly", result["problems"])

    def test_inexact_or_non_https_ui_route_is_rejected(self):
        from chatbot_status import evaluate_status

        routes = [{"host": "desktop.example.ts.net", "https_port": 80, "https": False, "funnel": False, "proxy": "http://0.0.0.0:8080"}]
        result = evaluate_status(llama_models=["local-worker"], llama_listeners=["127.0.0.1"], ui_healthy=True, ui_listeners=["127.0.0.1"], serve_routes=routes)
        self.assertFalse(result["healthy"])
        self.assertIn("Open WebUI has no exact Tailscale HTTPS route", result["problems"])

    def test_funnel_or_alternate_llama_proxy_is_rejected(self):
        from chatbot_status import evaluate_status

        routes = [
            {"host": "desktop.example.ts.net", "https_port": 443, "https": True, "funnel": True, "proxy": "http://127.0.0.1:8080"},
            {"host": "desktop.example.ts.net", "https_port": 8443, "https": True, "funnel": False, "proxy": "http://localhost:8000"},
        ]
        result = evaluate_status(llama_models=["local-worker"], llama_listeners=["127.0.0.1"], ui_healthy=True, ui_listeners=["127.0.0.1"], serve_routes=routes)
        self.assertFalse(result["healthy"])
        self.assertIn("Tailscale exposes llama.cpp directly", result["problems"])
        self.assertIn("Open WebUI has no exact Tailscale HTTPS route", result["problems"])

    @patch("chatbot_status.subprocess.run")
    def test_malformed_listener_output_fails_closed(self, run):
        from chatbot_status import _llama_listeners

        run.return_value = subprocess.CompletedProcess([], 0, stdout="not-json", stderr="")
        self.assertEqual(_llama_listeners(), [])


if __name__ == "__main__":
    unittest.main()
