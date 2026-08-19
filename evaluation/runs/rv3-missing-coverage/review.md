All tests pass. Here is my report:

### FINDING 1
axis: missing-coverage
file: scripts/status_page.py, `_StatusHandler._serve_html`
severity: high
confidence: verified
requirement: "the current run's title, kind, id and elapsed time as m:ss (or "idle" when current is null)"
gap: The HTML page renders "idle" when no run is current, but no test asserts the word "idle" appears in the HTML body when `current` is null. The only "nothing running" test (`test_nothing_running`) checks the JSON output (`current is None`) — the HTML path is untested.
proof: Replaced `title = kind = task_id = duration = "idle"` with `"SHOULD_NOT_APPEAR_IN_HTML"` in the source. Started the server against a fixture with only finished runs. Fetched `/`. The body contained `SHOULD_NOT_APPEAR_IN_HTML` and not `idle`. The existing test suite passed (no assertion on idle text) — the break was silently ignored.

### FINDING 2
axis: missing-coverage
file: scripts/status_page.py, `main`
severity: medium
confidence: verified
requirement: "If no command is given, print help and return exit code 1" (implicit from CLI contract — `main()` returns 1 when `args.command` is falsy)
gap: When no subcommand is provided, `main()` returns 1 (prints help). No test calls `main()` or invokes the script with zero arguments and asserts the exit code is 1. The CLI tests always provide `status`.
proof: Changed the guard to `return 0` instead of `return 1`. Ran `python scripts/status_page.py` with no arguments. Exit code was 0 instead of 1. The existing test suite passed — no test exercises the no-command path.

### FINDING 3
axis: missing-coverage
file: scripts/status_page.py, `_StatusHandler._serve_html`
severity: low
confidence: verified
requirement: 'refreshes itself with `<meta http-equiv="refresh" content="10">`'
gap: The HTML page includes the auto-refresh meta tag with `content="10"`, but no test asserts this value (or the tag's presence). The only HTML body assertion checks for the current run's title string.
proof: Changed `content="10"` to `content="999"`. Fetched `/` via HTTP. The body contained `content="999"` and not `content="10"`. The test suite passed — no assertion on the meta refresh content.

```
SUMMARY: missing-coverage=3 blocking=0 requirements-listed=34 requirements-uncovered=3 restored=yes
```