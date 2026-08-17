Now I have enough information. Let me compile the final report.

```
### FINDING 1
axis: spec
file: scripts/report-migration-coverage.py:312, 333, 348
severity: high
confidence: verified
problem: JSON parse errors produce full Python tracebacks instead of a one-line error message
why: The spec requires "Unusable input must produce a clear one-line message on stderr and a non-zero exit, never a traceback." Calling `json.loads()` without a try/except means any malformed JSON file crashes with a traceback
evidence: `echo "not json" > /tmp/bad.json && python scripts/report-migration-coverage.py --registry /tmp/bad.json` produced a 12-line `JSONDecodeError` traceback and exit code 1

### FINDING 2
axis: spec
file: scripts/report-migration-coverage.py:119-124
severity: medium
confidence: verified
problem: Units with invalid dispositions are counted as undecided in the per-kind breakdown despite being counted as decided in the summary
why: `decided_ids` includes all registry units with any ledger decision, but the aggregate/kind loops skip invalid dispositions. This makes a unit with an invalid disposition show as `decided=0, undecided=1` in its kind row while the summary reports `total_decided=1` — a semantic inconsistency in the breakdown
evidence: Created a registry with one unit and a ledger with disposition `"retire"`. Summary showed `total_decided=1, total_undecided=0`, but the kind breakdown showed `decided_count=0, undecided_count=1` for that unit's kind

### FINDING 3
axis: standards
file: scripts/report-migration-coverage.py:20-24
severity: low
confidence: verified
problem: `LEGEND` constant is dead code — a dictionary that maps every disposition to itself and is never referenced
why: Speculative generality / dead code. The same values already exist in `PERMITTED_DISPOSITIONS` and `LEGEND` is never used anywhere in the module
evidence: `grep -n 'LEGEND' scripts/report-migration-coverage.py` returned only line 20 (the definition). No other file references it.

SUMMARY: spec=2 standards=1 tests=0 tooling=0 blocking=1
```