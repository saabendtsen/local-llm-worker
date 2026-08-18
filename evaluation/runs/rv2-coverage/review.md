### FINDING 1
axis: missing-coverage
file: scripts/wayfinder_autopilot.py, `main()` history branch (`sorted(args.state)`) and `list_runs()` filter+limit ordering
severity: medium
confidence: verified
requirement: "--state filters by run state and is repeatable; it applies before --limit."
gap: No test exercises `--state` and `--limit` together. The spec requires state filtering to happen before the limit slice, but the only tests pass each flag in isolation. When I swapped the order (limit before filter) and ran `--state failed --limit 1` against 4 runs (2 completed, 2 failed), the broken code returned 0 runs instead of the newest failed run (`20260819T...`). The suite still passed because no single-flag test depends on ordering.
proof: Replaced `if states: ...; if limit is not None: ...` with `if limit is not None: ...; if states: ...` in `list_runs`. Ran `--state failed --limit 1` against a workspace with 3 completed + 1 failed run → stdout returned `{"state":"ok","runs":[]}` (zero entries after limit consumed a non-failed run, then filter removed it). Restored original order.

### FINDING 2
axis: missing-coverage
file: scripts/wayfinder_autopilot.py, `list_runs()` read-only behaviour
severity: high
confidence: verified
requirement: "history is strictly read-only: it must not create the log directory, must not acquire RunLock, and must not write anywhere."
gap: The test `test_cli_history_no_runs_directory` verifies `{"state": "ok", "runs": []}` and exit 0, but does not assert that no filesystem state was created. I injected `runs_dir.mkdir(parents=True, exist_ok=True)` into `list_runs`. The test still passed because it only checks the JSON payload, not the filesystem. This means any accidental write in `list_runs` would silently pass the suite.
proof: Added `runs_dir.mkdir(parents=True, exist_ok=True)` before the `is_dir()` guard in `list_runs`. Ran `test_cli_history_no_runs_directory` — test passed. Ran `test_list_runs_returns_empty_when_no_runs_dir` — also passed. Both tests check only the returned dict, never the filesystem. Restored original function.

### FINDING 3
axis: missing-coverage
file: scripts/wayfinder_autopilot.py, `list_runs()` abandoned-run branch
severity: low
confidence: suspected
requirement: "whether a long-running run is flagged as abandoned using the module's existing `timeout_seconds` and `SCHEDULER_CLEANUP_GRACE_SECONDS`" (deliberately left to implementor, but code implements it)
gap: The `abandoned` flag is computed in `list_runs` when a run's state is `"running"` and elapsed time exceeds `SCHEDULER_CLEANUP_GRACE_SECONDS` (300s). No test uses a `started_at` timestamp more than 300 seconds in the past with `state: "running"`. The existing `test_list_runs_running_run_has_none_duration` uses a future timestamp, so `is_abandoned` is always `False` in tests and the `abandoned: True` branch is untested.
proof: Not broken (abandoned check depends on real wall-clock time; a break would require mocking `datetime.now`).

```
SUMMARY: missing-coverage=3 blocking=0 requirements-listed=19 requirements-uncovered=3 restored=yes
```