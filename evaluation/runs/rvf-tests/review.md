Working tree is clean. Let me now compile the findings.

### FINDING 1
axis: test-strength
file: tests/test_migration_coverage.py:134-141
severity: high
confidence: verified
problem: The assertion `self.assertGreaterEqual(lp["decision_count"], 0)` can never fail for any plausible wrong value. The docstring promises "Ledger decision_count must equal number of decisions in ledger" but the body asserts nothing about correctness — only non-negativity. A ledger with 999 decisions when it has 3 would pass.
mutation: Changed `"decision_count": len(decisions)` to `"decision_count": 999` in build_report()
result: test_each_ledger_decision_count_matches PASSED (1 passed, 8 subtests passed)
why: The report would claim every ledger has exactly 999 decisions, completely misleading downstream consumers, yet the test passes

### FINDING 2
axis: test-strength
file: tests/test_migration_coverage.py:99-106
severity: high
confidence: verified
problem: The test checks `registry_count == decided_count + undecided_count` but both `decided_count` and `undecided_count` are computed from the same underlying expression (`sum(kind_dispositions[kind].values())`). This is a tautology — the equation is algebraically true by construction regardless of whether the disposition counts are correct.
mutation: Removed the disposition counting loop entirely (`aggregate_counts[first_disp] += 1` and `kind_dispositions[k][first_disp] += 1` deleted), so decided_count=0 and undecided_count=registry_count for every kind
result: test_per_kind_decided_plus_undecided PASSED (1 passed, 8 subtests passed) — all 8 kinds passed despite every disposition count being zero
why: If the disposition assignment logic were completely broken (e.g., no dispositions assigned), every unit would appear undecided, but the kind breakdown would still show `decided_count + undecided_count == registry_count`, silently hiding the bug

### FINDING 3
axis: test-strength
file: tests/test_migration_coverage.py:113-126
severity: medium
confidence: verified
problem: The test checks `decided_count == actual_disp_sum` where both values derive from the same `kind_dispositions[kind]` Counter. This is a structural consistency check, not a correctness check. The unused variable `disp_sum` (computed with `if kb.get(d, 0) > 0`) is dead code.
mutation: Same as Finding 2 — zeroed all disposition counting so both sides equal 0 for every kind
result: test_per_kind_disposition_sum PASSED (1 passed, 8 subtests passed)
why: If disposition assignment were broken, both `decided_count` and the sum of disposition counts would be 0, and the tautology would still hold

### FINDING 4
axis: test-strength
file: tests/test_migration_coverage.py:152-163
severity: low
confidence: verified
problem: The test `test_retain_in_place_round_trip` checks `assertIn("retain in place", restored)` after `json.loads(json.dumps(report["aggregate"]))`. This tests the json library, not the code. The code returns a dict — JSON serialization is not part of `build_report`. The assertion checks only key existence, not the count value.
mutation: Changed `aggregate_counts[first_disp] += 1` to `aggregate_counts[first_disp] += 0` so all values are zero but keys still exist
result: test_retain_in_place_round_trip PASSED (1 passed)
why: The report would contain all disposition keys with count 0, the test would pass, but the aggregate totals would be entirely wrong (the real-data `test_aggregate_totals` catches this, but only through a different assertion)

SUMMARY: test-strength=4 blocking=2 mutations-run=7 restored=yes