---
id: f02-wayfinder-history
repo: C:\Dev\homelab
category: feature-medium
complexity: medium
verify: python -m ruff check scripts tests && python -m pytest -q
base: experiment/74-local-llm-worker
branch: worker/f02-wayfinder-history
---

# Task: add a `history` subcommand to the Wayfinder autopilot

**Edit `scripts/wayfinder_autopilot.py`.** Then **edit `tests/test_wayfinder_autopilot.py`**.

## Current behavior

The autopilot writes structured metadata for every run to `<log_dir>/runs/<run-id>/run.json`,
alongside `events.jsonl`, `stderr.log` and `final.md`. It is written twice — once at start, once on
completion (lines 698-705 and 739-744):

```python
metadata = {
    "run_id": run_id,
    "state": "running",
    "dry_run": dry_run,
    "started_at": datetime.now().astimezone().isoformat(),
    "workspace": str(config.workspace),
}
...
metadata.update(state=state, exit_code=exit_code,
                finished_at=datetime.now().astimezone().isoformat())
```

**Nothing reads it back.** The `status` subcommand reports the Windows scheduled task and echoes
the log directory path; it says nothing about what any run did. So the documented recovery
procedure for an unattended coordinator is to open JSON files by hand under `%LOCALAPPDATA%`.

## Desired behavior

A `history` subcommand that lists past runs, newest first, as JSON on stdout.

```
python scripts/wayfinder_autopilot.py [--workspace DIR] [--config FILE] history [--limit N] [--state STATE ...]
```

The top-level object must carry a `state` key, because `main()` indexes `result["state"]` and maps
it to the exit code. Each listed run reports at least: `run_id`, `state`, `dry_run`, `started_at`,
`finished_at`, `duration_seconds`, `exit_code`, and the paths of its artifacts.

`--state` filters by run state and is repeatable; it applies before `--limit`.

## Key interfaces

- `AutopilotConfig` — already resolves a relative `log_dir` against `--workspace` (lines 54-56), so
  a test can point it at a temporary directory and never touch `%LOCALAPPDATA%`.
- `build_parser()` (line 821) — where the subparser attaches, beside `run`, `dry-run`, `install`,
  `status`, `uninstall`.
- `main()` (lines 846-854) — prints `json.dumps(result, indent=2)` and returns
  `0 if result["state"] not in {"failed", "timed_out"} else 1`. Its `except` clause catches
  `json.JSONDecodeError` and returns 2.
- `run_once` — the writer whose schema this reads. It creates `events.jsonl` only after the run
  starts, so a run that fails early has a `run.json` and nothing else.

## Seams under test

- **`main()` through the command line** — argparse wiring, JSON on stdout, exit code. Invoke it as a
  subprocess against a temporary workspace. `tests/test_dev_pc_ci.py` lines 15-21 show the `run_cli`
  helper shape to copy.  **[REQUIRED]**
- **The pure listing function** over a fixture `runs/` tree built by hand.  **[REQUIRED]**
- **Round trip with the writer** — call `run_once` with the fake codex stub as
  `tests/test_wayfinder_autopilot.py` lines 392-424 already do, then list, and assert the run it
  just wrote appears with matching `run_id` and `state`.  **[REQUIRED]** This is the seam that
  catches a reader written against an imagined schema rather than the real one.

## Cases the tests must cover

| Case | Source of truth for the assertion |
| --- | --- |
| A crashed run: `state: "running"`, no `finished_at` | `duration_seconds` is `None`, and the state is the writer's own literal `"running"` from line 700 |
| Duration across a UTC-offset change: started `2026-10-25T02:30:00+02:00`, finished `2026-10-25T02:30:05+01:00` | **`3605.0`** — verified by `datetime.fromisoformat` subtraction, not `5.0` |
| An ordinary duration: `15:55:03.540718+02:00` to `15:55:07.041543+02:00` | **`3.501`** |
| A truncated `run.json`, e.g. `{"run_id": "x", "state": "run` | process **exit code 0**, stdout parses as JSON, and that run is visible as unreadable. Contrast with the failure codes `main()` itself returns: 1 and 2 |
| `log_dir` exists but has no `runs/` directory | `{"state": "ok", ..., "runs": []}`, exit 0 |
| A stray `runs/notes.txt` beside two valid run directories | exactly the two runs listed, no entry for the file |
| Ordering with `--limit 1` over run ids `20260816T...`, `20260817T...`, `20260818T...` | exactly the `20260818T...` run — assert against a hand-written ascending literal list, reversed |
| Round trip | the writer's own keys: `run_id`, `state`, `dry_run`, `started_at`, `workspace`, `exit_code`, `finished_at`; and `run_id` matching `^\d{8}T\d{6}-\d+$`, the `strftime("%Y%m%dT%H%M%S-%f")` format at line 690 |

## Out of scope

- Do not change `run_once`, the metadata it writes, or any existing subcommand.
- `history` is strictly read-only: it must not create the log directory, must not acquire
  `RunLock`, and must not write anywhere.
- Change no files other than the two named above.

## Acceptance criteria

- [ ] `history` lists runs newest first, with the fields above.
- [ ] Every case in the table behaves as its source of truth requires.
- [ ] No filesystem state above causes a traceback or a non-zero exit.
- [ ] `python -m ruff check scripts tests && python -m pytest -q` passes. Baseline is
      **154 passed, 11 subtests passed**, and ruff currently reports **All checks passed** — so any
      other failure is a regression introduced here.
- [ ] Return a concise summary of what you built, the design choices you made and why, and anything
      left unresolved.

## Deliberately left to you

More than one answer is defensible; none will be marked wrong for its own sake:

- whether the top-level `state` is always `"ok"`, or reflects the newest run — note that `main()`
  maps it to the exit code, so this choice is load-bearing;
- whether unreadable runs appear inline with a sentinel state or in a separate list;
- the sort key — `run_id` is fixed-width and therefore chronological, but `started_at` is more
  explicit;
- whether to read `final.md` for a one-line summary, or report metadata only;
- whether absent artifacts are omitted or reported as `null`;
- whether a long-running run is flagged as abandoned using the module's existing `timeout_seconds`
  and `SCHEDULER_CLEANUP_GRACE_SECONDS`.

## Notes

- Parse timestamps with `datetime.fromisoformat`. `strptime` with a fixed format string mishandles
  the offset, and string slicing silently gets the DST case wrong.
- The `except` clause in `main()` catches `json.JSONDecodeError` and returns 2 — so a corrupt
  `run.json` that escapes will not crash visibly, it will exit 2 and look like an ordinary error.
  The test must assert exit **0** and the entry's presence, not merely "no traceback".
- Module conventions: `from __future__ import annotations`, `SCREAMING_CASE` module constants,
  functions returning plain `dict`, private helpers prefixed `_`, `pathlib` only, no third-party
  imports.
- Test conventions: `unittest.TestCase`, `sys.path.insert(0, str(ROOT / "scripts"))` then a flat
  `from wayfinder_autopilot import (...)  # noqa: E402` — add the new symbol to that import list.
  Fixtures in `setUp` with `tempfile.TemporaryDirectory()`, torn down in `tearDown`. The file ends
  `if __name__ == "__main__": unittest.main()`.
- Ruff runs with defaults, so an unused import in either file fails the acceptance command.
