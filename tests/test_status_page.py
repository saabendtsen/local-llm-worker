"""Tests for scripts/status_page.py — status page and HTTP server."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from status_page import collect_status  # noqa: E402

SCRIPT = ROOT / "scripts" / "status_page.py"

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_STARTED_TEMPLATE = (
    '{\n'
    '  "kind": "%(kind)s",\n'
    '  "task_id": "%(task_id)s",\n'
    '  "title": "%(title)s",\n'
    '  "started_at": "%(started_at)s"\n'
    '}\n'
)

_TERMINAL_TEMPLATE = (
    '{\n'
    '  "recorded_at": "%(recorded_at)s"\n'
    '}\n'
)


def _write_started(runs_dir: Path, task_id: str, kind: str, title: str, started_at: str,
                   **extra: object) -> Path:
    """Write a *started.json* under *runs_dir/<task_id>/*, returning the run dir."""
    run_dir = runs_dir / task_id
    run_dir.mkdir(parents=True, exist_ok=True)
    data = {"kind": kind, "task_id": task_id, "title": title, "started_at": started_at, **extra}
    (run_dir / "started.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return run_dir


def _write_terminal(run_dir: Path, name: str, recorded_at: str) -> Path:
    """Write a terminal file under *run_dir/*."""
    data = {"recorded_at": recorded_at}
    (run_dir / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return run_dir / name


# ---------------------------------------------------------------------------
# The pure function
# ---------------------------------------------------------------------------

class CollectStatusTests(unittest.TestCase):
    """Directly test *collect_status* over a hand-built temporary fixture."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmpdir.name) / "runs"
        self.runs.mkdir()
        self.now = datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    # -- running --

    def test_running_compute_duration(self) -> None:
        """started_at: 10:00, --now 10:05:30, no terminal file → 330.0."""
        now = datetime(2026, 8, 19, 10, 5, 30, tzinfo=timezone.utc)
        _write_started(self.runs, "r1", "task", "Running task",
                       "2026-08-19T10:00:00+00:00")
        result = collect_status(self.runs, now)
        self.assertEqual(result["current"]["task_id"], "r1")
        self.assertEqual(result["current"]["duration_seconds"], 330.0)
        self.assertEqual(result["running"], [result["current"]])

    def test_running_across_timezones(self) -> None:
        """started_at +02:00 12:00, now +00:00 10:00:05 → 5.0 seconds."""
        _write_started(self.runs, "tz", "task", "tz task",
                       "2026-08-19T12:00:00+02:00")
        now_utc = datetime(2026, 8, 19, 10, 0, 5, tzinfo=timezone.utc)
        result = collect_status(self.runs, now_utc)
        self.assertEqual(result["current"]["duration_seconds"], 5.0)

    def test_current_is_newest_of_two(self) -> None:
        """Two running runs; current is the one started last."""
        _write_started(self.runs, "a", "task", "old",
                       "2026-08-19T10:00:00+00:00")
        _write_started(self.runs, "b", "task", "new",
                       "2026-08-19T10:03:00+00:00")
        result = collect_status(self.runs, self.now)
        self.assertEqual(result["current"]["task_id"], "b")
        self.assertEqual(len(result["running"]), 2)
        # newest first
        self.assertEqual(result["running"][0]["task_id"], "b")
        self.assertEqual(result["running"][1]["task_id"], "a")

    # -- finished --

    def test_finished_task(self) -> None:
        """Started 10:00, run.json recorded 10:06:32 → 392.0s, in recent."""
        run_dir = _write_started(self.runs, "ft", "task", "Finished task",
                                 "2026-08-19T10:00:00+00:00")
        _write_terminal(run_dir, "run.json", "2026-08-19T10:06:32+00:00")
        result = collect_status(self.runs, self.now)
        self.assertIsNone(result["current"])
        self.assertEqual(result["recent"][0]["duration_seconds"], 392.0)
        self.assertEqual(result["recent"][0]["finished_at"],
                         "2026-08-19T10:06:32+00:00")
        self.assertEqual(result["recent"][0]["task_id"], "ft")
        self.assertEqual(result["running"], [])

    def test_finished_review(self) -> None:
        """review.json marks a review as finished."""
        run_dir = _write_started(self.runs, "fr", "review", "Review run",
                                 "2026-08-19T10:00:00+00:00")
        _write_terminal(run_dir, "review.json", "2026-08-19T10:01:00+00:00")
        result = collect_status(self.runs, self.now)
        self.assertEqual(result["recent"][0]["kind"], "review")
        self.assertEqual(result["running"], [])

    def test_finished_triage(self) -> None:
        """triage.json marks a triage as finished."""
        run_dir = _write_started(self.runs, "ftri", "triage", "Triage run",
                                 "2026-08-19T10:00:00+00:00")
        _write_terminal(run_dir, "triage.json", "2026-08-19T10:02:00+00:00")
        result = collect_status(self.runs, self.now)
        self.assertEqual(result["recent"][0]["kind"], "triage")
        self.assertEqual(result["running"], [])

    # -- nothing running --

    def test_nothing_running(self) -> None:
        """Two finished runs, nothing in flight → current is None."""
        run_dir_a = _write_started(self.runs, "a", "task", "A",
                                   "2026-08-19T10:00:00+00:00")
        _write_terminal(run_dir_a, "run.json", "2026-08-19T10:01:00+00:00")
        run_dir_b = _write_started(self.runs, "b", "task", "B",
                                   "2026-08-19T09:00:00+00:00")
        _write_terminal(run_dir_b, "run.json", "2026-08-19T09:02:00+00:00")
        result = collect_status(self.runs, self.now)
        self.assertIsNone(result["current"])
        self.assertEqual(len(result["recent"]), 2)
        # newest first by started_at
        self.assertEqual(result["recent"][0]["task_id"], "a")
        self.assertEqual(result["recent"][1]["task_id"], "b")

    # -- cap recent at 10 --

    def test_recent_capped_at_ten(self) -> None:
        """Twelve finished runs → recent has exactly 10."""
        for i in range(12):
            run_dir = _write_started(self.runs, f"f{i}", "task", f"Run {i}",
                                     f"2026-08-19T{10 + i:02d}:00:00+00:00")
            _write_terminal(run_dir, "run.json",
                            f"2026-08-19T{10 + i:02d}:01:00+00:00")
        result = collect_status(self.runs, self.now)
        self.assertEqual(len(result["recent"]), 10)
        # Oldest (f0) should not be present
        ids = [r["task_id"] for r in result["recent"]]
        self.assertNotIn("f0", ids)
        self.assertIn("f11", ids)

    # -- unreadable --

    def test_truncated_started_json(self) -> None:
        """Truncated started.json goes to unreadable; other runs still listed."""
        (self.runs / "bad-1").mkdir()
        (self.runs / "bad-1" / "started.json").write_text(
            '{"kind": "task", "title": ', encoding="utf-8")
        run_dir = _write_started(self.runs, "g", "task", "Good",
                                 "2026-08-19T10:00:00+00:00")
        _write_terminal(run_dir, "run.json",
                        "2026-08-19T10:01:00+00:00")
        result = collect_status(self.runs, self.now)
        self.assertIn("bad-1", result["unreadable"])
        self.assertEqual(len(result["recent"]), 1)

    def test_array_started_json(self) -> None:
        """started.json containing [1, 2, 3] → unreadable, no traceback."""
        (self.runs / "arr").mkdir()
        (self.runs / "arr" / "started.json").write_text(
            "[1, 2, 3]", encoding="utf-8")
        # Make the directory a real run subdirectory so we can verify other
        # runs are still listed alongside it.
        _write_started(self.runs, "dummy", "task", "Dummy", "2026-08-19T10:00:00+00:00")
        result = collect_status(self.runs, self.now)
        self.assertIn("arr", result["unreadable"])

    # -- unreadable terminal file --

    def test_unreadable_terminal_array(self) -> None:
        """started.json valid, run.json = [1,2,3] → unreadable only, not running."""
        _write_started(self.runs, "b", "task", "B", "2026-08-19T09:00:00+00:00")
        (self.runs / "b" / "run.json").write_text("[1, 2, 3]", encoding="utf-8")
        result = collect_status(self.runs, self.now)
        self.assertIn("b", result["unreadable"])
        self.assertEqual(result["unreadable"].count("b"), 1)
        self.assertEqual(result["running"], [])
        self.assertEqual(result["recent"], [])
        self.assertIsNone(result["current"])

    def test_unreadable_terminal_truncated(self) -> None:
        """started.json valid, run.json truncated → unreadable only."""
        _write_started(self.runs, "bt", "task", "B truncated", "2026-08-19T09:00:00+00:00")
        (self.runs / "bt" / "run.json").write_text('{"recorded_at": ', encoding="utf-8")
        result = collect_status(self.runs, self.now)
        self.assertIn("bt", result["unreadable"])
        self.assertEqual(result["unreadable"].count("bt"), 1)
        self.assertEqual(result["running"], [])
        self.assertEqual(result["recent"], [])
        self.assertIsNone(result["current"])

    def test_unreadable_terminal_next_to_running(self) -> None:
        """Unreadable-terminal dir next to a genuine running run → running works."""
        _write_started(self.runs, "u", "task", "Unreadable", "2026-08-19T09:00:00+00:00")
        (self.runs / "u" / "run.json").write_text("[1, 2, 3]", encoding="utf-8")
        _write_started(self.runs, "g", "task", "Good", "2026-08-19T10:00:00+00:00")
        now = datetime(2026, 8, 19, 10, 5, 30, tzinfo=timezone.utc)
        result = collect_status(self.runs, now)
        self.assertIn("u", result["unreadable"])
        self.assertEqual(result["current"]["task_id"], "g")
        self.assertEqual(result["current"]["duration_seconds"], 330.0)
        self.assertEqual(len(result["running"]), 1)

    def test_unreadable_terminal_next_to_finished(self) -> None:
        """Unreadable-terminal dir next to a finished run → finished works."""
        _write_started(self.runs, "u", "task", "Unreadable", "2026-08-19T09:00:00+00:00")
        (self.runs / "u" / "run.json").write_text("[1, 2, 3]", encoding="utf-8")
        run_dir = _write_started(self.runs, "ft", "task", "Finished task", "2026-08-19T10:00:00+00:00")
        _write_terminal(run_dir, "run.json", "2026-08-19T10:06:32+00:00")
        result = collect_status(self.runs, self.now)
        self.assertIn("u", result["unreadable"])
        self.assertEqual(len(result["recent"]), 1)
        self.assertEqual(result["recent"][0]["task_id"], "ft")
        self.assertEqual(result["recent"][0]["duration_seconds"], 392.0)
        self.assertIsNone(result["current"])

    # -- ignored --

    def test_no_started_json(self) -> None:
        """Directory with run.json but no started.json → ignored."""
        old = self.runs / "old"
        old.mkdir()
        (old / "run.json").write_text(
            json.dumps({"recorded_at": "2026-08-19T09:00:00+00:00"}, indent=2),
            encoding="utf-8")
        result = collect_status(self.runs, self.now)
        self.assertEqual(result["ignored"], 1)
        self.assertEqual(result["running"], [])
        self.assertEqual(result["recent"], [])

    def test_stray_file_ignored(self) -> None:
        """A stray file runs/notes.txt is not counted."""
        (self.runs / "notes.txt").write_text("noise", encoding="utf-8")
        result = collect_status(self.runs, self.now)
        self.assertEqual(result["ignored"], 0)

    # -- non-existent --runs --

    def test_non_existent_runs_dir(self) -> None:
        """Non-existent runs directory → empty result, exit 0, dir not created."""
        gone = Path("/tmp/homelab_does_not_exist_48291")
        self.assertFalse(gone.exists())
        result = collect_status(gone, self.now)
        self.assertIsNone(result["current"])
        self.assertEqual(result["running"], [])
        self.assertEqual(result["recent"], [])
        self.assertFalse(gone.exists())

    def test_naive_now_treated_as_utc(self) -> None:
        """Naive --now datetime (no tzinfo) with offset-aware started_at → no TypeError, correct duration."""
        naive_now = datetime(2026, 8, 19, 10, 5, 0)  # tzinfo is None
        _write_started(self.runs, "naive", "task", "Naive now task",
                       "2026-08-19T10:00:00+00:00")
        result = collect_status(self.runs, naive_now)
        self.assertEqual(result["current"]["duration_seconds"], 300.0)


# ---------------------------------------------------------------------------
# CLI through subprocess
# ---------------------------------------------------------------------------

def _run_cli(subcommand_args: list[str], runs_dir: Path) -> subprocess.CompletedProcess[str]:
    """Helper: run *scripts/status_page.py* against a fixture.

    *subcommand_args* is everything after the subcommand name (e.g. ``["status", "--now", ...]``).
    *runs_dir* is appended as the ``--runs`` flag so the script reads from the temporary fixture.
    """
    cmd = [sys.executable, str(SCRIPT), *subcommand_args, "--runs", str(runs_dir)]
    return subprocess.run(cmd, capture_output=True, text=True)


class CliTests(unittest.TestCase):
    """Test the *status* sub-command through the CLI."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmpdir.name) / "runs"
        self.runs.mkdir()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_status_exits_0_and_parses_json(self) -> None:
        """CLI status pins --now correctly and returns the fixture value-by-value."""
        # c1: finished run (started 10:00, recorded 10:01)
        run_dir = _write_started(self.runs, "c1", "task", "Cli task",
                                 "2026-08-19T10:00:00+00:00")
        _write_terminal(run_dir, "run.json", "2026-08-19T10:01:00+00:00")
        # c2: still running (started 10:00, no terminal file)
        _write_started(self.runs, "c2", "task", "Cli run",
                       "2026-08-19T10:00:00+00:00")
        proc = _run_cli(["status", "--now", "2026-08-19T10:02:00+00:00"], self.runs)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        # c2 is current (only running run; --now drives its duration)
        self.assertEqual(data["current"]["task_id"], "c2")
        self.assertEqual(data["current"]["duration_seconds"], 120.0)
        # exactly one running run
        self.assertEqual(len(data["running"]), 1)
        self.assertEqual(data["running"][0]["task_id"], "c2")
        # c1 is the most recent finished run
        self.assertEqual(data["recent"][0]["task_id"], "c1")
        self.assertEqual(data["recent"][0]["duration_seconds"], 60.0)
        self.assertEqual(data["recent"][0]["finished_at"],
                         "2026-08-19T10:01:00+00:00")
        # no ignored or unreadable
        self.assertEqual(data["ignored"], 0)
        self.assertEqual(data["unreadable"], [])

    def test_status_non_existent_runs(self) -> None:
        """Non-existent --runs → empty result, exit 0, dir not created."""
        gone = Path("/tmp/homelab_cli_gone_99281")
        self.assertFalse(gone.exists())
        proc = _run_cli(["status"], gone)  # --runs appended by helper
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertIsNone(data["current"])
        self.assertFalse(gone.exists())

    def test_no_command_prints_help(self) -> None:
        """No sub-command → help on stdout, exit 1.

        The runner must not use ``_run_cli`` here because that helper appends
        ``--runs``, which argparse rejects when no sub-command is present.
        """
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("usage:", proc.stdout.lower())

    def test_status_invalid_now(self) -> None:
        """Unparseable --now → exit 2, error on stderr naming --now, no traceback."""
        proc = _run_cli(
            ["status", "--now", "not-a-date"],
            self.runs,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--now", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("invalid", proc.stderr.lower())

    def test_status_naive_now(self) -> None:
        """Naive --now (no offset) treated as UTC → exit 0, correct duration."""
        _write_started(self.runs, "n", "task", "Naive now CLI",
                       "2026-08-19T10:00:00+00:00")
        proc = _run_cli(["status", "--now", "2026-08-19T10:05:00"], self.runs)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["current"]["duration_seconds"], 300.0)

    def test_status_aware_now(self) -> None:
        """Aware --now (+00:00) → exit 0, correct duration (unchanged path)."""
        _write_started(self.runs, "a", "task", "Aware now CLI",
                       "2026-08-19T10:00:00+00:00")
        proc = _run_cli(["status", "--now", "2026-08-19T10:05:00+00:00"], self.runs)
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["current"]["duration_seconds"], 300.0)

    # -- invalid port

    def test_serve_invalid_port_negative(self) -> None:
        """serve --port -1 → exit 2, error naming --port, no traceback."""
        proc = _run_cli(
            ["serve", "--port", "-1"],
            self.runs,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--port", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_serve_invalid_port_too_large(self) -> None:
        """serve --port 70000 → exit 2, error naming --port, no traceback."""
        proc = _run_cli(
            ["serve", "--port", "70000"],
            self.runs,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--port", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class HttpServerTests(unittest.TestCase):
    """Start the server on port 0 in a thread and exercise the endpoints."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmpdir.name) / "runs"
        self.runs.mkdir()
        self._populate_fixture()
        self._start_server()

    def _populate_fixture(self) -> None:
        _write_started(self.runs, "http-1", "task", "Current run <b>x</b>",
                       "2026-08-19T10:00:00+00:00")
        run_dir2 = _write_started(self.runs, "http-2", "task", "Finished run",
                                  "2026-08-19T09:00:00+00:00")
        _write_terminal(run_dir2, "run.json", "2026-08-19T09:05:00+00:00")

    def _start_server(self) -> None:
        from status_page import DEFAULT_HOST, ThreadingHTTPServer, _StatusHandler

        # Bind *_runs_dir* as a class attribute so every handler
        # instance can read it.  _now is no longer stored; each request
        # calls datetime.now(timezone.utc) at request time.
        self._handler_class = type(
            "_TestStatusHandler",
            (_StatusHandler,),
            {"_runs_dir": self.runs},
        )
        self.server = ThreadingHTTPServer((DEFAULT_HOST, 0), self._handler_class)
        self.port = self.server.server_address[1]
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.tmpdir.cleanup()

    def test_status_json_200(self) -> None:
        """GET /status.json → 200, correct Content-Type, valid JSON."""
        resp = urlopen(f"http://127.0.0.1:{self.port}/status.json")
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.headers.get("Content-Type", "").startswith("application/json"))
        data = json.loads(resp.read().decode())
        self.assertIn("current", data)
        self.assertIn("generated_at", data)

    def test_html_200_contains_current_title(self) -> None:
        """GET / → 200, Content-Type text/html, body contains the current run's title."""
        resp = urlopen(f"http://127.0.0.1:{self.port}/")
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.headers.get("Content-Type", "").startswith("text/html"))
        body = resp.read().decode()
        self.assertIn("Current run", body)

    def test_html_escapes_html_in_title(self) -> None:
        """Current title <b>x</b> → body contains &lt;b&gt;x&lt;/b&gt; not <b>x</b>."""
        resp = urlopen(f"http://127.0.0.1:{self.port}/")
        body = resp.read().decode()
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", body)
        self.assertNotIn("<b>x</b>", body)

    def test_404(self) -> None:
        """GET /nope → 404."""
        try:
            urlopen(f"http://127.0.0.1:{self.port}/nope")
            self.fail("Expected URLError")
        except Exception as exc:
            # urllib raises HTTPError for 4xx/5xx; check status code.
            self.assertTrue(hasattr(exc, "code") and exc.code == 404,
                            f"Unexpected error: {exc}")

    def test_status_json_consistent_with_pure_function(self) -> None:
        """HTTP /status.json body (minus generated_at) equals collect_status output."""
        resp = urlopen(f"http://127.0.0.1:{self.port}/status.json")
        data = json.loads(resp.read().decode())

        # Use the response's generated_at as the reference time.
        ref_now = datetime.fromisoformat(data["generated_at"])
        expected = collect_status(self.runs, ref_now)

        # generated_at is always different (computed at response time)
        expected.pop("generated_at")
        data.pop("generated_at")
        self.assertEqual(data, expected)

    def test_serve_and_status_never_write(self) -> None:
        """collect_status and HTTP requests must not create or modify any file."""

        def _snapshot() -> set[str]:
            paths = set()
            for p in self.runs.rglob("*"):
                if p.is_file():
                    paths.add(str(p))
            return paths

        before = _snapshot()

        # collect_status
        self._handler_class._now = datetime.now(timezone.utc)
        collect_status(self.runs, self._handler_class._now)

        # HTTP requests
        urlopen(f"http://127.0.0.1:{self.port}/status.json")
        urlopen(f"http://127.0.0.1:{self.port}/")
        urlopen(f"http://127.0.0.1:{self.port}/status.json")

        after = _snapshot()
        self.assertEqual(before, after,
                         f"Files changed: +{after - before} -{before - after}")

    def test_collect_status_does_not_create_directory(self) -> None:
        """collect_status must NOT create the runs directory if it does not exist.

        If ``runs_dir.mkdir(parents=True, exist_ok=True)`` is inserted at the top
        of *collect_status*, this test will fail.
        """
        gone = Path(tempfile.mkdtemp()) / "does_not_exist_38491"
        self.assertFalse(gone.exists())
        collect_status(gone)
        self.assertFalse(gone.exists(),
                         "collect_status created the runs directory")

    def test_generated_at_advances_between_requests(self) -> None:
        """Second GET /status.json must have a later generated_at than the first.

        This test fails if ``now`` is captured once at server start instead of
        per-request.
        """
        resp1 = urlopen(f"http://127.0.0.1:{self.port}/status.json")
        data1 = json.loads(resp1.read().decode())
        import time as _time
        _time.sleep(1.1)
        resp2 = urlopen(f"http://127.0.0.1:{self.port}/status.json")
        data2 = json.loads(resp2.read().decode())
        dt1 = datetime.fromisoformat(data1["generated_at"])
        dt2 = datetime.fromisoformat(data2["generated_at"])
        self.assertGreater(dt2, dt1)

    def test_run_started_after_server_has_non_negative_duration(self) -> None:
        """Write started.json with datetime.now() after server start → duration >= 0.

        Reproduces the observed defect: a run that starts after the server
        started must NOT have a negative duration_seconds.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        _write_started(self.runs, "post-start", "task", "Post-start run", now_str)
        resp = urlopen(f"http://127.0.0.1:{self.port}/status.json")
        data = json.loads(resp.read().decode())
        self.assertGreaterEqual(data["current"]["duration_seconds"], 0)

    def test_html_non_negative_elapsed_for_post_start_run(self) -> None:
        """GET / with a post-start run → elapsed cell does not show negative duration."""
        now_str = datetime.now(timezone.utc).isoformat()
        _write_started(self.runs, "post-start-html", "task", "Post-start HTML run", now_str)
        resp = urlopen(f"http://127.0.0.1:{self.port}/")
        self.assertEqual(resp.status, 200)
        body = resp.read().decode()
        # _format_duration of a non-negative value never contains "-0:" or "-1:"
        self.assertNotIn("-0:", body)
        self.assertNotIn("-1:", body)

    def test_status_now_untouched_for_running_run(self) -> None:
        """status --now 2026-08-19T10:05:00+00:00 against a running run started 10:00:00+00:00 → 300.0."""
        now_dir = Path(tempfile.mkdtemp()) / "runs"
        now_dir.mkdir()
        _write_started(now_dir, "nx", "task", "Now-untouched", "2026-08-19T10:00:00+00:00")
        proc = _run_cli(
            ["status", "--now", "2026-08-19T10:05:00+00:00"],
            now_dir,
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["current"]["duration_seconds"], 300.0)


# ---------------------------------------------------------------------------
# HTTP server — idle (no current run)
# ---------------------------------------------------------------------------

class HttpIdleServerTests(unittest.TestCase):
    """Start the server on port 0 with only finished runs and verify idle rendering."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.runs = Path(self.tmpdir.name) / "runs"
        self.runs.mkdir()
        self._populate_idle_fixture()
        self._start_server()

    def _populate_idle_fixture(self) -> None:
        """One finished run, nothing in-flight."""
        run_dir = _write_started(
            self.runs, "done-1", "task", "Finished only",
            "2026-08-19T09:00:00+00:00",
        )
        _write_terminal(run_dir, "run.json", "2026-08-19T09:05:00+00:00")

    def _start_server(self) -> None:
        from status_page import DEFAULT_HOST, ThreadingHTTPServer, _StatusHandler

        self._handler_class = type(
            "_IdleStatusHandler",
            (_StatusHandler,),
            {"_runs_dir": self.runs},
        )
        self.server = ThreadingHTTPServer((DEFAULT_HOST, 0), self._handler_class)
        self.port = self.server.server_address[1]
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.tmpdir.cleanup()

    def test_idle_html(self) -> None:
        """GET / when nothing is running → 200, text/html, idle + finished run in table."""
        resp = urlopen(f"http://127.0.0.1:{self.port}/")
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.headers.get("Content-Type", "").startswith("text/html"))
        body = resp.read().decode()
        # the idle sentinel
        self.assertIn("idle", body)
        # the finished run still shows in the recent table
        self.assertIn("Finished only", body)
        # _format_duration(300.0) → "5:00"
        self.assertIn("5:00", body)

    def test_idle_status_json(self) -> None:
        """GET /status.json when current is None → parsed JSON reflects idle state."""
        resp = urlopen(f"http://127.0.0.1:{self.port}/status.json")
        data = json.loads(resp.read().decode())
        self.assertIsNone(data["current"])
        self.assertEqual(len(data["recent"]), 1)


# ---------------------------------------------------------------------------
# Duration formatting edge cases
# ---------------------------------------------------------------------------

class DurationFormatTests(unittest.TestCase):
    """Test _format_duration for edge cases."""

    def test_round_minutes(self) -> None:
        from status_page import _format_duration
        self.assertEqual(_format_duration(330.0), "5:30")

    def test_single_second(self) -> None:
        from status_page import _format_duration
        self.assertEqual(_format_duration(5.0), "0:05")

    def test_exceeds_one_hour(self) -> None:
        """62 minutes → 62:00, not 1:02:00."""
        from status_page import _format_duration
        self.assertEqual(_format_duration(3723.0), "62:03")

    def test_zero(self) -> None:
        from status_page import _format_duration
        self.assertEqual(_format_duration(0.0), "0:00")


if __name__ == "__main__":
    unittest.main()
