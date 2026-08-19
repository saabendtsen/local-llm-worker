I have verified the contradictions through computation. Let me write the final report.

### FINDING 1
axis: consistency
file: scripts/status_page.py:101-103
severity: high
confidence: verified
problem: Directory with an unreadable terminal file (valid started.json but run.json contains a list, not a dict) appears in BOTH the `unreadable` list AND the `running` list
why: The `for/else` loop over `TERMINAL_FILES` has two code paths that both result in `terminal_file` being `None`: (1) no terminal files exist → `else` clause explicitly sets `terminal_file = None` (correct), and (2) a terminal file exists but is not a valid dict → `break` exits without reaching `else`, leaving `terminal_file` at its initial `None` value (bug). Both paths then fall into the `if terminal_file is not None` → `else` branch which treats the directory as a running run. The spec says a run is "running" only when "none of run.json, review.json, triage.json does" — but here `run.json` does exist, so the run is NOT running per the spec
repro: Create a directory with `started.json` = `{"kind":"task","started_at":"2026-08-19T09:00:00+00:00"}` and `run.json` = `[1, 2, 3]`, then run `python scripts/status_page.py status --runs <fixture_dir> --now 2026-08-19T10:00:00+00:00`
evidence: `unreadable = ['case-b']` and `running = [{'task_id': 'b', ...}]` — the same directory (task_id='b') is in both lists; `current` incorrectly references it with `duration_seconds=1800.0`

### FINDING 2
axis: consistency
file: scripts/status_page.py:35
severity: low
confidence: suspected
problem: `_format_duration` produces `"-1:55"` for negative input (`-5.0`), which violates the `m:ss` convention
why: Python floor division (`-5 // 60 = -1`) and modulo (`-5 % 60 = 55`) yield `"-1:55"` instead of something meaningful. The spec defines `duration_seconds = now − started_at` for running runs — if `started_at` happens to be after `now`, the result is negative. The `m:ss` format in the spec implies non-negative minutes and seconds, but the implementation produces a nonsensical string for negative durations
repro: `_format_duration(-5.0)` → returns `"-1:55"`
evidence: `_format_duration(5.0)` → `"0:05"`, `_format_duration(-5.0)` → `"-1:55"` (minutes is `-1`, not a valid display)

```
SUMMARY: consistency=2 blocking=1 relations-checked=7
```

**Relations checked (7):**
1. **unreadable ∩ running = ∅** — violated (Finding 1): a directory with an unreadable terminal file lands in both lists
2. **current ∈ running ∪ {null}** — violated (Finding 1): `current` points to a directory that has a terminal file (just unreadable), contradicting the spec's definition of "running"
3. **total_dirs = running + recent + unreadable + ignored** — violated (Finding 1): sum overcounts because the unreadable-terminal directory is counted in both `running` and `unreadable`
4. **running = {dirs with valid started.json AND no terminal file}** — violated (Finding 1): the set includes dirs where a terminal file exists but is invalid
5. **duration_seconds for running = now - started_at** — satisfied (verified via cross-timezone test: 5.0s correct)
6. **duration_seconds for finished = recorded_at - started_at** — satisfied (verified: 392.0s correct)
7. **current = running[0] (newest)** — satisfied when running is non-empty