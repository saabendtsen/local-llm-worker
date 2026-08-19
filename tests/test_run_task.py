"""Tests for the pieces of run_task.py that other scripts and the status page rely on."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_task import (  # noqa: E402
    RUNS_DIR,
    is_runner_artifact,
    pipeline_of,
    task_title,
    write_started,
)


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


class RunnerArtifactTests(unittest.TestCase):
    """Files the harness makes must not be staged as the worker's work (f03)."""

    def test_run_directory_files_are_artifacts(self):
        repo = RUNS_DIR.parent.parent
        self.assertTrue(is_runner_artifact(repo, "evaluation/runs/f03/prompt.txt"))

    def test_pycache_is_an_artifact_anywhere(self):
        self.assertTrue(is_runner_artifact(Path("C:/elsewhere"), "scripts/__pycache__/x.pyc"))

    def test_ordinary_source_is_not(self):
        repo = RUNS_DIR.parent.parent
        self.assertFalse(is_runner_artifact(repo, "scripts/status_page.py"))
        self.assertFalse(is_runner_artifact(Path("C:/elsewhere"), "evaluation/runs/x/prompt.txt"))


class PipelineOfTests(unittest.TestCase):
    def test_feature_fix_and_review_share_a_pipeline(self):
        self.assertEqual(pipeline_of("f03-status-page"), "f03")
        self.assertEqual(pipeline_of("f03-fix-02-invalid-now-clean-error"), "f03")

    def test_id_without_dash_is_its_own_pipeline(self):
        self.assertEqual(pipeline_of("0003"), "0003")


if __name__ == "__main__":
    unittest.main()
