```
### FINDING 1
axis: standards
file: scripts/report-migration-coverage.py:20-27
severity: low
confidence: verified
problem: Dead `LEGEND` constant defined but never referenced anywhere in the module.
why: The identity-mapping dict `LEGEND = {"migrate": "migrate", ...}` is defined at module scope but no other statement reads it. Dead code clutters the module.
evidence: `grep -n "LEGEND" scripts/report-migration-coverage.py` returns only line 20 (the definition itself). AST walk confirms `LEGEND` is defined as an assignment target but never appears as a Name load elsewhere.

### FINDING 2
axis: tests
file: tests/test_migration_coverage.py:147-148
severity: medium
confidence: verified
problem: Test `test_each_ledger_decision_count_matches` asserts nothing meaningful and never compares against actual ledger data despite its name.
why: The test body calls `self.assertGreaterEqual(lp["decision_count"], 0)` which is always true for any non-negative count, and `self.assertIsInstance(ledger, str)` which checks a string type, not the count. It claims to verify that the decision_count "matches" but performs no comparison against the real ledger file contents. A stub implementation returning `decision_count: 0` for every ledger would pass this test.
evidence: Reading lines 147-153 of `tests/test_migration_coverage.py` shows the full test body; the variable `ledger` is assigned `lp["path"]` (a string) and the only numeric assertion is `>= 0`.

### FINDING 3
axis: standards
file: tests/test_migration_coverage.py:118-120
severity: low
confidence: verified
problem: Dead variable `disp_sum` computed in `test_per_kind_disposition_sum` but never used in any assertion.
why: The comprehension result is stored in `disp_sum`, then a second, slightly different comprehension overwrites it conceptually by computing `actual_disp_sum`, but `disp_sum` itself is never referenced. This is a code-smell (dead assignment) that suggests either incomplete logic or a copy-paste error.
evidence: Reading lines 112-124 of `tests/test_migration_coverage.py` shows `disp_sum` is assigned but the subsequent `self.assertEqual` call uses `actual_disp_sum`, not `disp_sum`.

SUMMARY: spec=0 standards=2 tests=1 tooling=0 blocking=0
```