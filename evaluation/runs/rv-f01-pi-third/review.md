Now I have enough verified evidence. Here is the report:

### FINDING 1
axis: spec
file: scripts/report-migration-coverage.py:312-313
severity: high
confidence: verified
problem: Invalid JSON in registry file produces a traceback instead of a one-line error message
why: Spec requires "Unusable input must produce a clear one-line message on stderr and a non-zero exit, never a traceback" — `json.loads` is called without a try/except wrapper
evidence: `echo "invalid json{{{" > /tmp/bad.json && python scripts/report-migration-coverage.py --registry /tmp/bad.json` produced `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` with full traceback

### FINDING 2
axis: spec
file: scripts/report-migration-coverage.py:333-334
severity: high
confidence: verified
problem: Invalid JSON in any ledger file produces a traceback with the same unhandled `json.JSONDecodeError`
why: Same spec violation as Finding 1 — `json.loads` at line 333 is not wrapped in try/except, so a malformed ledger file crashes the program
evidence: `echo "not json" > /tmp/bad_ledger.json && python scripts/report-migration-coverage.py --registry inventories/migration-unit-registry-2026-08-08.json --ledger /tmp/bad_ledger.json` produced `json.decoder.JSONDecodeError` with full traceback

### FINDING 3
axis: tests
file: tests/test_migration_coverage.py:134-142
severity: medium
confidence: verified
problem: `test_each_ledger_decision_count_matches` is a stub — the assertion always passes regardless of correctness
why: The docstring says "must equal number of decisions in ledger" but the test only asserts `decision_count >= 0`, which is trivially true for any non-negative integer. Replacing every `decision_count` with `999` would not make the test fail.
evidence: Test body:
```python
def test_each_ledger_decision_count_matches(self):
    """Ledger decision_count must equal number of decisions in ledger."""
    for lp in self.report["ledger_provenance"]:
        with self.subTest(path=lp["path"]):
            ledger = lp["path"]
            self.assertIsInstance(ledger, str)
            self.assertGreaterEqual(lp["decision_count"], 0,)
```

### FINDING 4
axis: standards
file: scripts/report-migration-coverage.py:20-25
severity: low
confidence: verified
problem: `LEGEND` constant is dead code — maps every disposition to itself and is never referenced
why: Baseline smell of speculative generality / dead code. The dict at line 20 is defined but `grep -n "LEGEND"` shows it only appears in that one line. No function reads it.
evidence: `grep -n "LEGEND" scripts/report-migration-coverage.py` returns only line 20 where it is defined.

### FINDING 5
axis: tests
file: tests/test_migration_coverage.py:112-113
severity: low
confidence: verified
problem: `test_per_kind_disposition_sum` contains an unused variable `disp_sum` whose existence misleads readers
why: The variable computes a sum that is never used in the assertion; `actual_disp_sum` is what's actually compared. The comment "Only count dispositions that actually have a count" suggests the author intended `disp_sum` and `actual_disp_sum` to differ, but they compute identical values.
evidence: Lines 112-113: `disp_sum = sum(kb.get(d, 0) for d in PERMITTED if kb.get(d, 0) > 0)` — computed but never referenced.

SUMMARY: spec=2 standards=1 tests=2 tooling=0 blocking=2