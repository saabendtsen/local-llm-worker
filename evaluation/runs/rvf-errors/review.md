Now I have comprehensive evidence. Let me compile the report.

### FINDING 1
axis: error-paths
file: scripts/report-migration-coverage.py:312
severity: high
confidence: verified
problem: Invalid JSON in registry file produces a traceback to the user instead of a one-line error message.
why: The spec requires "never a traceback" — `json.loads` raises `JSONDecodeError` uncaught. The exit code is 1 (default), but the user sees a full stack.
repro: echo "garbage data" > /tmp/ep-test/bad-json.json && python scripts/report-migration-coverage.py --registry /tmp/ep-test/bad-json.json --ledger inventories/service-dispositions-2026-08-10.json 2>&1
evidence: `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` followed by a 7-line traceback to `main()`.

### FINDING 2
axis: error-paths
file: scripts/report-migration-coverage.py:333
severity: high
confidence: verified
problem: Invalid JSON in a ledger file produces a traceback to the user.
why: Same spec violation as Finding 1 — `json.loads` for ledger files is unguarded. User sees a full stack instead of a one-line error.
repro: echo "not json" > /tmp/ep-test/bad-ledger.json && python scripts/report-migration-coverage.py --registry inventories/migration-unit-registry-2026-08-08.json --ledger /tmp/ep-test/bad-ledger.json 2>&1
evidence: `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` with a 7-line traceback.

### FINDING 3
axis: error-paths
file: scripts/report-migration-coverage.py:49
severity: high
confidence: verified
problem: Registry with `migration_units: null` (valid JSON but wrong shape) raises a `TypeError` traceback.
why: `registry.get("migration_units", [])` returns `None` (not the default), and `{u["id"] for u in units}` fails on `None`. The spec says "never a traceback" for unusable input.
repro: echo '{"migration_units": null}' > /tmp/ep-test/null-units.json && python scripts/report-migration-coverage.py --registry /tmp/ep-test/null-units.json --ledger inventories/service-dispositions-2026-08-10.json 2>&1
evidence: `TypeError: 'NoneType' object is not iterable` in a traceback reaching `main()`.

### FINDING 4
axis: error-paths
file: scripts/report-migration-coverage.py:49,51
severity: high
confidence: verified
problem: Registry with `migration_units` as a string (wrong shape) raises a `TypeError` traceback inside `build_report`.
why: `registry.get("migration_units", [])` returns `"not-a-list"`, then `{u["id"] for u in units}` iterates over characters. The `u["id"]` then raises `TypeError: string indices must be integers, not 'str'`. No validation on the structure before use.
repro: echo '{"migration_units": "not-a-list"}' > /tmp/ep-test/wrong-shape.json && python scripts/report-migration-coverage.py --registry /tmp/ep-test/wrong-shape.json --ledger inventories/service-dispositions-2026-08-10.json 2>&1
evidence: `TypeError: string indices must be integers, not 'str'` in traceback.

### FINDING 5
axis: error-paths
file: scripts/report-migration-coverage.py:68
severity: high
confidence: verified
problem: Ledger with `decisions` as a string (wrong shape) raises an `AttributeError` traceback inside `build_report`.
why: `data.get("decisions", [])` returns `"not-a-list"`. The loop `for dec in decisions` iterates over characters, then `dec.get("id", ...)` fails because a character has no `.get()`.
repro: echo '{"decisions": "not-a-list"}' > /tmp/ep-test/bad-ledger-shape.json && python scripts/report-migration-coverage.py --registry inventories/migration-unit-registry-2026-08-08.json --ledger /tmp/ep-test/bad-ledger-shape.json 2>&1
evidence: `AttributeError: 'str' object has no attribute 'get'` in traceback.

### FINDING 6
axis: error-paths
file: scripts/report-migration-coverage.py:367
severity: medium
confidence: verified
problem: `--output` path with a non-existent parent directory produces a `FileNotFoundError` traceback.
why: `args.output.write_text()` does not create parent directories. No try/except wraps it.
repro: python scripts/report-migration-coverage.py --registry inventories/migration-unit-registry-2026-08-08.json --ledger inventories/service-dispositions-2026-08-10.json --output /tmp/ep-test/no-such-dir/output.json 2>&1
evidence: `FileNotFoundError: [Errno 2] No such file or directory: '...\no-such-dir\output.json'` in traceback.

### FINDING 7
axis: error-paths
file: scripts/report-migration-coverage.py:49
severity: medium
confidence: verified
problem: Registry unit dict missing the `id` key raises a `KeyError` traceback.
why: The set comprehension `{u["id"] for u in units}` uses a blind index with no fallback. If a unit object omits `id`, the tool crashes instead of reporting the issue.
repro: python3 -c "import sys; sys.path.insert(0, 'scripts'); import importlib.util; spec = importlib.util.spec_from_file_location('report_mc', 'scripts/report-migration-coverage.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod.build_report({'migration_units': [{'kind': 'skill', 'name': 'no-id'}]}, [])"
evidence: `KeyError: 'id'` in traceback.

### FINDING 8
axis: error-paths
file: scripts/report-migration-coverage.py:51
severity: medium
confidence: verified
problem: Registry unit dict missing the `kind` key raises a `KeyError` traceback.
why: The generator `u["kind"] for u in units` uses a blind index. A unit without `kind` causes a crash before any report can be produced.
repro: python3 -c "import sys; sys.path.insert(0, 'scripts'); import importlib.util; spec = importlib.util.spec_from_file_location('report_mc', 'scripts/report-migration-coverage.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod.build_report({'migration_units': [{'id': 'u1'}]}, [])"
evidence: `KeyError: 'kind'` in traceback.

### FINDING 9
axis: error-paths
file: scripts/report-migration-coverage.py:210
severity: medium
confidence: verified
problem: `_render_text` raises a `KeyError` when given a report missing expected keys (e.g., `"summary"`).
why: `s = report["summary"]` is a blind lookup with no validation. A caller (or a future modification) that passes an incomplete report gets a traceback, not a handled error.
repro: python3 -c "import sys; sys.path.insert(0, 'scripts'); import importlib.util; spec = importlib.util.spec_from_file_location('report_mc', 'scripts/report-migration-coverage.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod._render_text({'foo': 'bar'})"
evidence: `KeyError: 'summary'`.

### FINDING 10
axis: error-paths
file: scripts/report-migration-coverage.py:142-145
severity: medium
confidence: verified
problem: A decision with an empty `disposition` string is silently counted as "decided" but contributes 0 to aggregate totals.
why: `id_to_dispositions[uid].append("")` adds the empty string. The unit enters `decided_ids`. In aggregate, `""` is not in `PERMITTED_DISPOSITIONS`, so it is skipped. The unit appears decided with no disposition counted — a silent wrong answer.
repro: python3 -c "import sys; sys.path.insert(0, 'scripts'); import importlib.util; spec = importlib.util.spec_from_file_location('report_mc', 'scripts/report-migration-coverage.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod.build_report({'migration_units': [{'id': 'u1', 'kind': 'skill'}]}, [('/dev/null', {'decisions': [{'id': 'u1'}]})])"
evidence: `{'total_decided': 1, 'total_undecided': 0, 'coverage_complete': True}` with `aggregate: {}`.

SUMMARY: error-paths=10 blocking=5 cases-tested=15