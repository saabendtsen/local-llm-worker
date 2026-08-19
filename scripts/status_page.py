"""Status page for the local worker — what it is doing right now.

Usage:
    python scripts/status_page.py status [--runs DIR] [--now ISO8601]
    python scripts/status_page.py serve  [--runs DIR] [--host HOST] [--port N]

The *status* sub-command prints a JSON object to stdout and exits 0.
The *serve* sub-command runs a loopback HTTP server with a refreshable
HTML page and a JSON API.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TERMINAL_FILES = ("run.json", "review.json", "triage.json")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_duration(seconds: float) -> str:
    """Format seconds as *m:ss*.  No hours prefix — 1 h 2 m 3 s → *62:03*."""
    total = int(seconds)
    minutes = total // 60
    secs = total % 60
    return f"{minutes}:{secs:02d}"


def _read_json_object(path: Path) -> dict[str, Any] | None:
    """Read *path*, decode JSON, return the value only if it is a ``dict``.

    Returns ``None`` when the file is missing, truncated, not valid JSON, or
    the top-level value is not an object (list, scalar, etc.).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Core function — the seam for every test
# ---------------------------------------------------------------------------

def collect_status(runs_dir: Path, now: datetime | None = None) -> dict[str, Any]:
    """Produce the status object for *runs_dir* at the given moment.

    This function is pure with respect to the filesystem except that it reads
    the directory.  The *now* parameter lets tests pin the clock without
    patching ``datetime.now``.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    running: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    unreadable: list[str] = []
    ignored = 0

    if not runs_dir.is_dir():
        return {
            "generated_at": now.isoformat(),
            "current": None,
            "running": [],
            "recent": [],
            "unreadable": [],
            "ignored": 0,
        }

    for entry in runs_dir.iterdir():
        if not entry.is_dir():
            continue

        started = _read_json_object(entry / "started.json")
        if started is None:
            if not (entry / "started.json").exists():
                ignored += 1
            else:
                unreadable.append(entry.name)
            continue

        # Find the terminal file for this run.
        terminal_file: Path | None = None
        terminal_data: dict[str, Any] | None = None
        for tf_name in TERMINAL_FILES:
            tf_path = entry / tf_name
            if tf_path.exists():
                data = _read_json_object(tf_path)
                if data is not None:
                    terminal_file = tf_path
                    terminal_data = data
                    break
                else:
                    # File exists but is not a valid JSON object → unreadable.
                    unreadable.append(entry.name)
                    break
        else:
            terminal_file = None
            terminal_data = None

        if terminal_file is not None:
            # Finished run — build the record and compute duration from the
            # data in the files, not from the live clock.
            try:
                started_dt = datetime.fromisoformat(started["started_at"])
                recorded_dt = datetime.fromisoformat(terminal_data["recorded_at"])
                duration = (recorded_dt - started_dt).total_seconds()
            except (KeyError, ValueError):
                unreadable.append(entry.name)
                continue

            record: dict[str, Any] = {
                "kind": started.get("kind"),
                "task_id": started.get("task_id"),
                "title": started.get("title"),
                "started_at": started["started_at"],
                "duration_seconds": duration,
                "finished_at": terminal_data["recorded_at"],
            }
            recent.append(record)
        else:
            # No terminal file — in-flight run.
            try:
                started_dt = datetime.fromisoformat(started["started_at"])
                duration = (now - started_dt).total_seconds()
            except (KeyError, ValueError):
                unreadable.append(entry.name)
                continue

            record = {
                "kind": started.get("kind"),
                "task_id": started.get("task_id"),
                "title": started.get("title"),
                "started_at": started["started_at"],
                "duration_seconds": duration,
            }
            running.append(record)

    # Sort: newest started first (descending by started_at).
    running.sort(key=lambda r: r["started_at"], reverse=True)
    recent.sort(key=lambda r: r["started_at"], reverse=True)

    current = running[0] if running else None

    return {
        "generated_at": now.isoformat(),
        "current": current,
        "running": running,
        "recent": recent[:10],
        "unreadable": unreadable,
        "ignored": ignored,
    }


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def _cmd_status(args: argparse.Namespace) -> int:
    runs_dir = args._runs if args._runs else Path(__file__).resolve().parent.parent / "evaluation" / "runs"
    now = datetime.fromisoformat(args.now) if args.now else None
    result = collect_status(runs_dir, now)
    print(json.dumps(result, indent=2))
    return 0


class _StatusHandler(BaseHTTPRequestHandler):
    """Serve the HTML page and the JSON status endpoint."""

    # Silence the default access log lines.
    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send(self, status: int, body: str, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/status.json":
            self._serve_json()
        elif self.path == "/":
            self._serve_html()
        else:
            self._send(404, "Not Found", "text/plain")

    def _serve_json(self) -> None:
        result = collect_status(self._runs_dir, self._now)
        self._send(200, json.dumps(result, indent=2), "application/json; charset=utf-8")

    def _serve_html(self) -> None:
        import html as _html

        result = collect_status(self._runs_dir, self._now)
        current = result["current"]

        if current:
            title = _html.escape(str(current.get("title", "")))
            kind = _html.escape(str(current.get("kind", "")))
            task_id = _html.escape(str(current.get("task_id", "")))
            duration = _format_duration(current["duration_seconds"])
        else:
            title = kind = task_id = duration = "idle"

        rows: list[str] = []
        for run in result["recent"]:
            r_title = _html.escape(str(run.get("title", "")))
            r_kind = _html.escape(str(run.get("kind", "")))
            r_id = _html.escape(str(run.get("task_id", "")))
            r_dur = _format_duration(run["duration_seconds"])
            rows.append(
                f"      <tr>"
                f"<td>{r_id}</td>"
                f"<td>{r_kind}</td>"
                f"<td>{r_title}</td>"
                f"<td>{r_dur}</td>"
                f"</tr>"
            )
        rows_html = "\n".join(rows) if rows else "      <tr><td colspan=\"4\">No recent runs</td></tr>"

        page = f"""\
<!DOCTYPE html>
<html>
<head>
<title>Local Worker Status</title>
<meta http-equiv="refresh" content="10">
<style>
  body {{ font-family: sans-serif; margin: 2em; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: left; }}
  th {{ background: #f4f4f4; }}
</style>
</head>
<body>
<h1>Local Worker Status</h1>
<p>Generated at: {_html.escape(result["generated_at"])}</p>
<h2>Current</h2>
<p>
  <strong>Title:</strong> {title} &nbsp;
  <strong>Kind:</strong> {kind} &nbsp;
  <strong>ID:</strong> {task_id} &nbsp;
  <strong>Elapsed:</strong> {duration}
</p>
<h2>Recent runs</h2>
<table>
<thead>
  <tr><th>ID</th><th>Kind</th><th>Title</th><th>Duration</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>
"""
        self._send(200, page, "text/html; charset=utf-8")


def _cmd_serve(args: argparse.Namespace) -> int:
    runs_dir = args._runs if args._runs else Path(__file__).resolve().parent.parent / "evaluation" / "runs"
    host = args.host or DEFAULT_HOST
    port = args.port or DEFAULT_PORT

    handler: type[_StatusHandler] = type(
        "_StatusHandler",
        (_StatusHandler,),
        {"_runs_dir": runs_dir, "_now": datetime.now(timezone.utc)},
    )

    server = ThreadingHTTPServer((host, port), handler)
    print(f"Serving on http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.strip())
    sub = parser.add_subparsers(dest="command")

    st = sub.add_parser("status", help="print the current status as JSON to stdout")
    st.add_argument(
        "--runs",
        type=Path,
        default=None,
        dest="_runs",
        help="path to the evaluation/runs directory (defaults to evaluation/runs next to this script)",
    )
    st.add_argument("--now", help="pin the current time as ISO-8601 (for tests)")
    st.set_defaults(func=_cmd_status)

    sv = sub.add_parser("serve", help="run a loopback HTTP server")
    sv.add_argument(
        "--runs",
        type=Path,
        default=None,
        dest="_runs",
        help="path to the evaluation/runs directory (defaults to evaluation/runs next to this script)",
    )
    sv.add_argument("--host", default=DEFAULT_HOST, help="bind address (default: loopback only)")
    sv.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to listen on")
    sv.set_defaults(func=_cmd_serve)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
