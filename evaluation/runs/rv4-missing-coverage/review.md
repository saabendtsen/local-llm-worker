Now I have all the evidence I need. Let me compile the findings.

### FINDING 1
axis: missing-coverage
file: scripts/status_page.py, collect_status — running run fields (`turns`, `tool_calls`, `last_activity_at`, `last_activity_seconds_ago`)
severity: high
confidence: verified
requirement: "Each entry in `running` (and therefore `current`) gains: `turns` — the number of lines in the run's `events.jsonl` whose JSON object has `"type": "turn_end"`; `tool_calls` — likewise for `"type": "tool_execution_end"`."
gap: The individual functions `_count_events_incremental` and `_last_activity_at` are tested in isolation, but no test verifies that `collect_status` actually includes these fields in the running run record. If `collect_status` silently dropped them, no test would catch it.
proof: Removed `turns`, `tool_calls`, `last_activity_at`, and `last_activity_seconds_ago` from `collect_status`'s running-run output; the full suite of 71 tests still passes.

### FINDING 2
axis: missing-coverage
file: scripts/status_page.py, _format_duration
severity: medium
confidence: verified
requirement: "``59.0 → "0:59"``, ``3599.0 → "59:59"``, ``3600.0 → "1:00:00"``, ``3725.0 → "1:02:05"``."
gap: Only 5.0, 0.0, 330.0, 3600.0, and 3723.0 are tested. The spec's boundary values 59.0, 3599.0, and 3725.0 have no test. An off-by-one in the boundary (< 3600 → < 3599) would cause 3599.0 to format as "0:59:59" instead of "59:59", and the existing suite would not detect it.
proof: Changed `< 3600` to `< 3599` in `_format_duration`. `3599.0 → "0:59:59"` (wrong). All 71 tests pass unchanged. `3600.0` and `3723.0` still pass because they take the `h:mm:ss` branch even with the broken boundary.

### FINDING 3
axis: missing-coverage
file: scripts/status_page.py, _detail_review
severity: medium
confidence: verified
requirement: "Review detail: `timed_out` (as above)" — the spec defines this as reading from `worker.timed_out` or `worker.idle_timed_out` when present, falling back to top-level keys.
gap: `_detail_review` has a branch for `isinstance(worker, dict)` that reads `timed_out` from the worker dict, and an else branch for top-level keys. No test provides `worker` as a dict in terminal_data for a review run. The existing `test_review_findings` test uses minimal terminal data (only `recorded_at`) and only asserts on `findings`.
proof: Made `_detail_review` always return `timed_out=True` regardless of input. All 71 tests pass unchanged because no review test asserts on `timed_out`.

### FINDING 4
axis: missing-coverage
file: scripts/status_page.py, _format_detail — HTML rendering for review and triage kinds
severity: low
confidence: verified
requirement: "Detail column rendered from `detail` — for tasks `✓`/`✗` plus `+added/−removed`, for reviews `<n> findings`, for triages `fix <n> · test <n> · defer <n> · drop <n>`."
gap: No test verifies the HTML output contains the rendered review detail ("`<n>` findings") or triage detail ("fix N · drop M"). The `test_verify_passed_false_show_x` test only exercises the task `✗` path. The `✓` for `verify_passed=True` is also untested in HTML.
proof: Made `_format_detail` return `""` for both review and triage kinds. All 71 tests pass unchanged because no test checks the HTML body for review or triage detail text.

SUMMARY: missing-coverage=4 blocking=2 requirements-listed=0 requirements-uncovered=4 restored=no