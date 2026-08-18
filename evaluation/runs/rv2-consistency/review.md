Both duration values match the spec exactly. The only inconsistency found is the missing `abandoned` key. Here's the report:

### FINDING 1
axis: consistency
file: scripts/wayfinder_autopilot.py:498-509
severity: high
confidence: verified
problem: unreadable-run entries omit the `"abandoned"` key that every normal entry includes
why: The normal entry dict (line ~525) sets `"abandoned": is_abandoned`. The unreadable-entry dict (line ~498-509), built inside the `except (json.JSONDecodeError, OSError)` handler, has no `"abandoned"` key. A consumer iterating over `result["runs"]` that contains both valid and unreadable entries cannot safely access `entry["abandoned"]` without a `KeyError` guard. The test `test_list_runs_all_required_keys_present` asserts `abandoned` is a required key but only exercises the valid-entry path, so the gap goes uncaught.
repro: Place a truncated `run.json` (e.g. `{"run_id": "x", "state": "run`) in a `runs/` directory and call `list_runs()`. The resulting entry dict will lack the `"abandoned"` key while all other entries contain it.
evidence: Normal entry keys include `"abandoned"`; unreadable entry keys do not. Verified by extracting both dicts from the source and computing set difference: `{'abandoned'}`.

### FINDING 2
axis: consistency
file: scripts/wayfinder_autopilot.py:472
severity: low
confidence: suspected
problem: `duration_seconds` rounding to 3 decimal places produces variable JSON decimal precision (3.501 vs 3605.0)
why: The code uses `round(value, 3)`. When the rounded value is exact (e.g. 3605.0), Python serialises it as `3605.0` (one decimal) rather than `3605.000` (three decimals). Consumers expecting a consistent decimal width in the JSON output would see an unexpected format. This is not a logic error—the values themselves are correct—but it breaks the implicit contract that rounding to N places yields N decimals.
repro: Run `list_runs()` on a fixture with `started_at: "2026-10-25T02:30:00+02:00"`, `finished_at: "2026-10-25T02:30:05+01:00"`. The JSON output will contain `"duration_seconds": 3605.0` instead of `3605.000`.
evidence: `json.dumps(round(3.500825, 3))` → `"3.501"`; `json.dumps(round(3605.0, 3))` → `"3605.0"`.

SUMMARY: consistency=2 blocking=0 relations-checked=6