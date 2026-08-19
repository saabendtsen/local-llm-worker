---
id: f03rep-fix-01-unreadable-terminal-not-running
repo: C:\Dev\homelab\experiments\local-llm-worker
category: bugfix
complexity: small
verify: python -m ruff check scripts tests && python -m pytest -q
base: worker/f03-status-page
branch: worker/f03rep-fix-01
---

# Task: a run whose terminal file is unreadable must go only to `unreadable`, never to `running`

**Edit `scripts/status_page.py` and `tests/test_status_page.py`. Nothing else.**

This is a single, bounded fix. Do not refactor, do not improve anything the task does not name, and do not address any other review finding.

## Current behavior

In `collect_status` (scripts/status_page.py:99-113), when one of `run.json` / `review.json` / `triage.json` exists but is not a JSON object, the code does:

```python
                else:
                    # File exists but is not a valid JSON object → unreadable.
                    unreadable.append(entry.name)
                    break
```

`break` leaves `terminal_file` at its initial `None` (:97), so the `if terminal_file is not None:` at :115 is false and the `else:` branch at :135-151 treats the directory as an in-flight run: it computes `now - started_at` and appends it to `running`. The same directory name ends up in **both** `unreadable` and `running`, and it becomes `current` when it is the newest started.

Repro: create `<fixture>/case-b/started.json` = `{"kind": "task", "task_id": "b", "title": "B", "started_at": "2026-08-19T09:00:00+00:00"}` and `<fixture>/case-b/run.json` = `[1, 2, 3]`, then run `python scripts/status_page.py status --runs <fixture> --now 2026-08-19T10:00:00+00:00`. Output has `"unreadable": ["case-b"]` **and** `"running": [{"task_id": "b", ... "duration_seconds": 3600.0}]` with `current` pointing at it.

## Desired behavior

A directory with a readable `started.json` whose terminal file exists but is missing, truncated, invalid JSON, or not an object appears **exactly once** in `unreadable`, and appears in neither `running` nor `recent`. It is never `current`. Every other directory is still listed exactly as before. Nothing raises. The existing behaviour for a terminal file that *is* an object but lacks a parseable `recorded_at` (:118-124, already goes to `unreadable` and `continue`s) must stay as it is.

The minimal fix is to `continue` to the next directory instead of `break`ing out of the inner loop after `unreadable.append(entry.name)` at :109-110, so that the running/finished branches below are skipped for that directory.

## Out of scope

- Do not change how a directory with no terminal file at all is classified (it stays `running`).
- Do not change the `unreadable` handling for a missing or bad `started.json` (:88-94).
- Do not change sorting, the `recent` cap, the HTTP handler, the HTML page, or argument parsing.
- Do not address any other review finding.

## Cases the tests must cover

| Case | Source of truth for the assertion |
| --- | --- |
| Readable `started.json` (started_at 2026-08-19T09:00:00+00:00) plus `run.json` containing `[1, 2, 3]`, `now` = 2026-08-19T10:00:00+00:00 | `result["unreadable"] == ["<dirname>"]` (appears once), `result["running"] == []`, `result["recent"] == []`, `result["current"] is None` — the spec says a run is running only when none of the terminal files exists, and run.json exists here |
| Readable `started.json` plus `run.json` containing the truncated text `{"recorded_at": ` | same as above: dirname in `unreadable` exactly once, not in `running`, not in `recent` |
| Readable `started.json` plus `review.json` containing `[1, 2, 3]` (no run.json) | same treatment as run.json — the loop at :99 handles all three names identically |
| The bad directory above alongside a good running run `g` (started 2026-08-19T09:30:00+00:00, no terminal file), `now` = 2026-08-19T10:00:00+00:00 | `result["running"]` has exactly one entry with task_id `g` and `duration_seconds == 1800.0`; `result["current"]["task_id"] == "g"`; bad dirname in `unreadable` and not in `running` — same arithmetic as `test_running_compute_duration` (tests/test_status_page.py:77-85) |
| The bad directory above alongside a good finished run `f` (started 10:00:00, run.json recorded_at 10:06:32) | `result["recent"]` has exactly one entry, task_id `f`, `duration_seconds == 392.0` — reuse the literal from `test_finished_task` (tests/test_status_page.py:110-121); bad dirname not in `recent` |

## Acceptance criteria

- [ ] Every case above passes as a new test (or tests) in `CollectStatusTests` in tests/test_status_page.py, built with the existing `_write_started` helper and writing the bad terminal file by hand.
- [ ] The repro command above now prints `"unreadable": ["case-b"]` with `"running": []` and `"current": null`.
- [ ] `python -m ruff check scripts tests && python -m pytest -q` passes — the whole suite, not only the new tests. Run the suite once before editing and note the passed count (main baseline is 71 passed + 6 subtests; this branch adds 27 tests in tests/test_status_page.py); the count after your change must be that number plus your new tests, with zero failures.
- [ ] The suite is green on `worker/f03-status-page`, so any failure you see is one you introduced.
- [ ] Return a concise summary of what was modified and anything left unresolved.

## Notes

- Copy the fixture style of `test_truncated_started_json` (tests/test_status_page.py:176-187): `(self.runs / name).mkdir()` then `write_text(...)` for the bad file, `_write_started(...)` for the good one.
- Assert `result["unreadable"].count(name) == 1` (or equality with the one-element list) so a double-append is caught too.
- After changing `break` to `continue`, the `for/else` `else:` clause at :111-113 becomes redundant but harmless; leaving it is fine. Do not restructure more than needed.
- Ruff runs with defaults: no unused imports or variables.
- Generated by triage from review finding(s) 2.
