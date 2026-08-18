Source restored, working tree clean. Here's the report:

```
### FINDING 1
axis: test-strength
file: tests/test_wayfinder_autopilot.py:717-760
severity: low
confidence: verified
problem: test_list_runs_all_required_keys_present does not assert on duration_seconds value
mutation: Changed round((finish_dt - start_dt).total_seconds(), 3) to duration = 99999.0
result: 1 passed (the key-presence test itself passed; the two dedicated duration tests failed as expected)
why: This test validates that all required keys are present and checks run_id/state/dry_run/exit_code, but duration_seconds is only checked for key presence, not value. A broken duration calculation that still produces a non-None float would slip past this test. Other tests catch the bug, but this specific test provides no discrimination on duration.

### FINDING 2
axis: test-strength
file: tests/test_wayfinder_autopilot.py:570-584
severity: medium
confidence: verified
problem: test_list_runs_filters_by_state does not test limit+states interaction
mutation: Swapped the order of state filter and limit slice in list_runs (limit applied before state filter instead of after)
result: 42 passed
why: When --limit and --state are combined, applying limit before filtering produces wrong results. E.g., --limit 2 --state completed over 3 completed + 1 failed run gives 2 completed runs with correct order, but only 1 with swapped order. No test exercises both flags together.

### FINDING 3
axis: test-strength
file: tests/test_wayfinder_autopilot.py:586-606
severity: medium
confidence: verified
problem: test_list_runs_computes_duration_for_completed_run uses places=2 which is too lenient for the 3.501 assertion
mutation: Changed round((finish_dt - start_dt).total_seconds(), 3) to round(..., 2)
result: 42 passed
why: Rounding to 2dp gives 3.5 instead of 3.501. The assertAlmostEqual with places=2 accepts differences < 0.005, so 0.001 passes silently. The test should use places=3 to enforce the 3-decimal precision the spec requires.

### FINDING 4
axis: test-strength
file: scripts/wayfinder_autopilot.py:838
severity: medium
confidence: verified
problem: --state uses nargs="*" instead of action="append", breaking repeated --state flags
mutation: Changed history_parser.add_argument("--state", action="append", default=None) to nargs="*"
result: 42 passed
why: With action="append", --state A --state B produces ["A", "B"]. With nargs="*", it produces ["A", "--state", "B"]. The "--state" literal enters the filter list as noise. The spec says --state is repeatable. No test exercises repeated --state flags.
```

SUMMARY: test-strength=4 blocking=2 mutations-run=4 restored=yes