Now I have all the evidence. Let me compile the findings.

### FINDING 1
axis: error-paths
file: scripts/status_page.py:175
severity: high
confidence: verified
problem: Invalid --now argument produces a Python traceback
why: The call to `datetime.fromisoformat(args.now)` at line 175 raises `ValueError: Invalid isoformat string: 'not-a-date'` and the traceback propagates through `main()` to `__main__`, reaching the user. The spec requires exit 0 on valid flags; an invalid flag should produce a one-line error and exit non-zero.
repro: `python scripts/status_page.py status --runs C:/tmp --now not-a-date`
evidence: `ValueError: Invalid isoformat string: 'not-a-date'` with full traceback to line 337

### FINDING 2
axis: error-paths
file: scripts/status_page.py:285
severity: high
confidence: verified
problem: Negative port number produces a Python traceback
why: `ThreadingHTTPServer((host, port), handler)` at line 285 receives `port=-1` (accepted by argparse's `type=int`), but `socket.bind()` raises `OverflowError: bind(): port must be 0-65535`. The traceback escapes to the user instead of a clean error message.
repro: `python scripts/status_page.py serve --port -1`
evidence: `OverflowError: bind(): port must be 0-65535` with full traceback through `server_bind()` to line 337

### FINDING 3
axis: error-paths
file: scripts/status_page.py:135-136
severity: medium
confidence: verified
problem: Negative duration accepted silently
why: When `recorded_at` is earlier than `started_at` (e.g. a clock reset or corrupt data), `(recorded_dt - started_dt).total_seconds()` returns a negative number like `-600.0`. The code never validates `duration >= 0`, so a plausible-looking but wrong result is returned silently. This is worse than a crash because the user gets a misleading number.
repro: `python scripts/status_page.py status --runs <fixture-with-started-after-recorded> --now 2026-08-19T10:05:00+00:00`
evidence: `duration_seconds=-600.0` returned as a valid field; no validation, no warning, exit 0

---

SUMMARY: error-paths=3 blocking=2 cases-tested=6