Source files are clean. Here are my findings:

---

### FINDING 1
axis: test-strength
file: tests/test_status_page.py:232-241
severity: medium
confidence: suspected
problem: test_status_exits_0_and_parses_json checks only key existence ("current", "recent", "ignored"), not values. The test fixture creates a finished run (duration 60 s), but the test would pass even if `collect_status` returned `{"current": null, "running": [], "recent": [], "ignored": 0}` — empty data with the right keys.
mutation: insert `return {"generated_at": "...", "current": None, "running": [], "recent": [], "unreadable": [], "ignored": 0}` at the top of `collect_status`
result: (suspected — the fixture's finished run would be silently invisible; `recent` would be empty, `current` null)
why: a broken implementation that returns default/empty data passes the test because no actual values are asserted

---

### FINDING 2
axis: test-strength
file: tests/test_status_page.py:107-121
severity: low
confidence: verified
problem: `test_finished_review` and `test_finished_triage` individually do not verify that the running/finished distinction works. They only assert `recent[0]["kind"] == "review"` (from the fixture's `started.json`) and `running == []`. If the code always appended every run to `recent` regardless of terminal file presence, these two tests pass.
mutation: removed the `if terminal_file is not None` / `else` branch; always computed duration and appended to `recent`
result: 2 passed (the review and triage tests passed with the broken code)
why: all runs would appear as finished/recent; in-flight runs would be silently misclassified
note: `test_current_is_newest_of_two` does catch this mutation, so the suite as a whole is safe, but these individual tests are weak on their own

---

### FINDING 3
axis: test-strength
file: tests/test_status_page.py:285-293
severity: medium
confidence: verified
problem: `test_status_json_200` checks only HTTP status 200, Content-Type, and that the JSON body contains keys `"current"` and `"generated_at"`. It does not assert that `current` has the expected task data. If `_serve_json` returned constant empty data, the test would pass.
mutation: replaced `_serve_json` body with a hardcoded `{"current": None, "running": [], "recent": [], "unreadable": [], "ignored": 0}` object
result: 1 passed (the test passed with completely empty data instead of the fixture's running + finished runs)
why: the fixture contains a running run (`http-1`) and a finished run (`http-2`); empty data is invisible to the assertion

---

SUMMARY: test-strength=3 blocking=0 mutations-run=14 restored=yes