"""Tests for the pieces of run_task.py that other scripts and the status page rely on."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_task import task_title, write_started  # noqa: E402


class TaskTitleTests(unittest.TestCase):
    def test_strips_task_prefix(self):
        self.assertEqual(task_title("# Task: add a `history` subcommand\n\nbody", "x"),
                         "add a `history` subcommand")

    def test_heading_without_prefix_is_kept(self):
        self.assertEqual(task_title("intro\n# Fix the thing\n", "x"), "Fix the thing")

    def test_no_heading_falls_back(self):
        self.assertEqual(task_title("no heading here", "fallback-id"), "fallback-id")


class WriteStartedTests(unittest.TestCase):
    def test_writes_marker_with_kind_title_and_extra(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_started(run_dir, "task", "f03", "Status page", branch="worker/f03")
            record = json.loads((run_dir / "started.json").read_text(encoding="utf-8"))
        self.assertEqual(record["kind"], "task")
        self.assertEqual(record["task_id"], "f03")
        self.assertEqual(record["title"], "Status page")
        self.assertEqual(record["branch"], "worker/f03")
        # ISO-8601 with an explicit offset, so a reader can subtract it from now.
        self.assertRegex(record["started_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")


if __name__ == "__main__":
    unittest.main()
