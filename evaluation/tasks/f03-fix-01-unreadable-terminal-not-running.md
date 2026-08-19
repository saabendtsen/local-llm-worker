---
id: f03-fix-01-unreadable-terminal-not-running
repo: C:\Dev\homelab\experiments\local-llm-worker
category: bugfix
complexity: small
verify: python -m ruff check scripts tests && python -m pytest -q
base: worker/f03-status-page
branch: worker/f03-fix-01
---

# Task: a run whose terminal file is unreadable must go to `unreadable` only, never to `running`

**Edit `scripts/status_page.py` and `tests/test_status_page.py`. Nothing else.**

This is a single, bounded fix. Do not refactor, do not improve anything the task does not name, and do not address any other review finding.

## Current behavior

In `collect_status` (`scripts/status_page.py:99-113`) the loop over `TERMINAL_FILES` handles an existing-but-unreadable terminal file like this:

```python
                else:
                    # File exists but is not a valid JSON object → unreadable.
                    unreadable.append(entry.name)
                    break
```

`break` leaves `terminal_file` at its initial `None` (line 97), so the check at line 115 `if terminal_file is not None:` fails and execution falls into the `else:` branch at line 135, which treats the directory as an **in-flight** run and appends it to `running` (line 151). The same directory name therefore appears in both `unreadable` and `running`, and — being a running entry — can become `current`.

Repro: create `<fixture>/case-b/started.json` = `{"kind":"task","task_id":"b","title":"B","started_at":"2026-08-19T09:00:00+00:00"}` and `<fixture>/case-b/run.json` = `[1, 2, 3]`, then run

```
python scripts/status_page.py status --runs <fixture> --now 2026-08-19T10:00:00+00:00
```

Output has `"unreadable": ["case-b"]` **and** `"running": [{"task_id": "b", ... "duration_seconds": 3600.0}]` with `current` pointing at it.

## Desired behavior

A directory with a valid `started.json` whose first existing terminal file (checked in `TERMINAL_FILES` order: `run.json`, `review.json`, `triage.json`) exists but is not a JSON object — truncated, invalid JSON, a list, a scalar — is appended to `unreadable` **exactly once** and contributes nothing to `running` or `recent`. It can never be `current`. Every other directory is still processed normally. Nothing raises.

The spec rule: a run is running only when `started.json` exists **and none of** `run.json`, `review.json`, `triage.json` exists. If one exists, the run is not running regardless of whether it is readable.

A clean way to get there: first find the terminal path (`next((entry / n for n in TERMINAL_FILES if (entry / n).exists()), None)`), then, if it is not `None`, read it; if the read returns `None`, append the name to `unreadable` and `continue` the **outer** `for entry` loop. Any equivalent restructuring is fine as long as the cases below hold.

## Out of scope

- Do not change how a missing `started.json` (ignored) or an unreadable `started.json` (unreadable) is handled — lines 88-94 stay as they are.
- Do not change the KeyError/ValueError handling for a missing or malformed `recorded_at` / `started_at` (lines 118-124, 137-142) beyond what is needed to keep it working after your restructuring.
- Do not change sorting, the `recent[:10]` cap, the JSON shape, the CLI, or the HTTP handler.
- Do not address any other review finding.

## Cases the tests must cover

| Case | Source of truth for the assertion |
| --- | --- |
| `started.json` valid (`kind: task`, `task_id: b`, `started_at: 2026-08-19T09:00:00+00:00`), `run.json` containing `[1, 2, 3]`, now `2026-08-19T10:00:00+00:00` | `"b"`'s directory name is in `unreadable` exactly once (`unreadable.count(name) == 1`); `"b"` is not in `[r["task_id"] for r in running]` nor in `recent`; `current is None` when it is the only directory — the spec's definition of running ("none of run.json, review.json, triage.json exists") |
| same as above but `run.json` containing the truncated text `{"recorded_at": ` | identical assertions — the spec groups truncated and not-an-object together under unreadable |
| the unreadable-terminal directory next to a genuinely running run `g` started `2026-08-19T10:00:00+00:00`, now `2026-08-19T10:05:30+00:00` | `current["task_id"] == "g"`, `current["duration_seconds"] == 330.0`, `len(running) == 1` — the 330.0 literal is the spec's first table row and is already asserted by `test_running_compute_duration` (tests/test_status_page.py:77-85) |
| the unreadable-terminal directory next to a finished run `ft` (started `10:00:00`, `run.json` recorded `10:06:32`) | `len(recent) == 1`, `recent[0]["task_id"] == "ft"`, `recent[0]["duration_seconds"] == 392.0` — same literal as `test_finished_task` (tests/test_status_page.py:110-121) |
| all existing tests in `tests/test_status_page.py` | they keep passing unchanged — in particular `test_truncated_started_json`, `test_array_started_json`, `test_no_started_json` |

## Acceptance criteria

- [ ] Every case above passes, as new test methods in `CollectStatusTests` in `tests/test_status_page.py`.
- [ ] The finding's repro command prints JSON in which the bad directory appears only in `unreadable` and `current` is `null`.
- [ ] `python -m ruff check scripts tests && python -m pytest -q` passes — the whole suite, not only the new tests. Run it once before editing and record the count; on this branch it is expected to be 98 passed (71 on `main` plus 27 in `tests/test_status_page.py`), 6 subtests passed, ruff clean. Any failure outside the tests you add is a regression you introduced.
- [ ] The suite is green on `worker/f03-status-page`, so any failure you see is one you introduced.
- [ ] Return a concise summary of what was modified and anything left unresolved.

## Notes

- Build fixtures with the module-level helpers `_write_started(runs_dir, task_id, kind, title, started_at)` and `_write_terminal(run_dir, name, recorded_at)` at tests/test_status_page.py:42-56; for the bad terminal file write the raw text with `(run_dir / "run.json").write_text("[1, 2, 3]", encoding="utf-8")` exactly as `test_array_started_json` does for started.json.
- Gotcha: a `continue` placed inside the inner `for tf_name in TERMINAL_FILES` loop continues the *inner* loop, not the outer `for entry` loop. Either restructure so the terminal-file lookup is not a loop (see desired_behavior) or use a flag checked after the inner loop.
- Conventions: `from __future__ import annotations`, private helpers prefixed `_`, `pathlib` only, plain `dict` returns. Ruff runs with defaults — no unused imports or variables.
- Generated by triage from review finding(s) 2.
