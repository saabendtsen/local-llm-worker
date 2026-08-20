Here's my review report:

### FINDING 1
axis: error-paths
file: scripts/status_page.py:381
severity: high
confidence: verified
problem: TypeError escapes to user when `recorded_at` in `run.json` is not a string
why: When a finished run's `run.json` has `"recorded_at": 99999` (a number instead of an ISO-8601 string), `datetime.fromisoformat(99999)` raises `TypeError`. The surrounding `except (KeyError, ValueError)` does not catch `TypeError`, so the traceback reaches the caller. This affects both `GET /` and `GET /status.json` through the HTTP handler.
repro: python -c "import tempfile,json; from pathlib import Path; d=tempfile.mkdtemp(); (Path(d)/'started.json').write_text(json.dumps({'kind':'task','task_id':'t','title':'T','started_at':'2026-08-19T10:00:00+00:00'})); (Path(d)/'run.json').write_text(json.dumps({'recorded_at':99999})))" then call collect_status
evidence: `TypeError: fromisoformat: argument must be str` — traceback printed to server stderr; HTTP client receives `RemoteDisconnected`

### FINDING 2
axis: error-paths
file: scripts/status_page.py:406-407
severity: high
confidence: verified
problem: TypeError escapes when `started_at` is a non-string (e.g. number) or a naive ISO-8601 string (no tzinfo)
why: Two distinct code paths both hit this: (a) `datetime.fromisoformat(12345)` raises `TypeError` — same root cause as Finding 1 but for the running-run path; (b) `datetime.fromisoformat('2026-08-19T10:00:00')` returns a naive datetime, then `now - started_dt` (where `now` is UTC-aware) raises `TypeError: can't subtract offset-naive and offset-aware datetimes`. Neither is caught by `except (KeyError, ValueError)`. A host that writes `started.json` without timezone info will silently crash the status page.
repro: python -c "import tempfile,json; from pathlib import Path; d=tempfile.mkdtemp(); (Path(d)/'started.json').write_text(json.dumps({'kind':'task','task_id':'t','title':'T','started_at':'2026-08-19T10:00:00'})))" then call collect_status
evidence: `TypeError: can't subtract offset-naive and offset-aware datetimes` — traceback to stderr; `RemoteDisconnected` on HTTP clients

### FINDING 3
axis: error-paths
file: scripts/status_page.py:61
severity: medium
confidence: verified
problem: `_format_duration` raises `ValueError` on NaN and `OverflowError` on infinity
why: `int(seconds)` raises `ValueError` for `float('nan')` and `OverflowError` for `float('inf')`. In normal flow `duration_seconds` comes from `total_seconds()` on datetime arithmetic so these values are impossible. However the function is public, imported by tests, and callable directly — an external caller can trigger crashes.
repro: python -c "from status_page import _format_duration; _format_duration(float('nan'))"
evidence: `ValueError: cannot convert float NaN to integer` / `OverflowError: cannot convert float infinity to integer`

---

### Additional observations (not defect-level)

- **`_detail_triage` accepts any iterable for `attempts`**: `len(terminal_data.get("attempts", []))` on a string like `"not-a-list"` returns 10. This is technically wrong but low risk — `valid` must be `True` for this code path, meaning a real triage JSON would have a list.
- **Pipeline values of non-string type**: `pipeline: 0` or `pipeline: ""` pass through to the groups map as distinct keys. The spec says pipeline is "the first dash-separated token" — a non-string would be unusual but not broken.

---

### Summary of testing

| Case | Tested? | How |
|---|---|---|
| 1. File does not exist | Yes | runs_dir non-existent, events.jsonl missing, review.md missing |
| 2. Path is a directory | Yes | started.json as dir, events.jsonl as dir, review.md as dir |
| 3. Not valid JSON | Yes | Garbage bytes, BOM, null bytes in review.md, binary events.jsonl |
| 4. Valid JSON wrong shape | Yes | Array, scalar, empty object as started.json; non-dict JSON per events.jsonl line |
| 5. Unreadable / permissions | Partial | Directory-as-file covers the principle; actual permission-denied not testable on Windows |
| 6. Required arg absent / empty | Yes | No subcommand (exit 1), bad port (exit 2), empty port, empty datetime |
| 7. Empty collection | Yes | Empty runs dir, empty attempts, empty tasks, empty events file |
| 8. Value outside permitted set | Yes | NaN, infinity, negative duration, unknown kind, pipeline as int/empty string, 12 runs exceeding `recent` cap |

SUMMARY: error-paths=3 blocking=2 cases-tested=8