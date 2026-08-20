Confirmed clean and 71 passing. Here is my report:

### FINDING 1
axis: test-strength
file: scripts/status_page.py:291-293
severity: high
confidence: verified
problem: `_format_detail` renders task detail in the HTML. Both `verify_passed=True` and `verify_passed=False` produce "✗". There is no test that checks for "✓" when `verify_passed=True`. The only HTML test for this area (`test_verify_passed_false_show_x`) only asserts "✗" with `verify_passed=False`, which is satisfied by either branch of the mutation.
mutation: Changed `_format_detail` task branch: `if vp is True: parts.append("✗")` and `elif vp is False: parts.append("✗")` — both pass/fail render as "✗"
result: 71 passed
why: A successfully verified task would display "✗" in the detail column, making it indistinguishable from a failed task. Users would see false negatives.

### FINDING 2
axis: test-strength
file: scripts/status_page.py:571-578
severity: high
confidence: verified
problem: The `if current` / `elif result["recent"]` chain determines whether the page header says "RUNNING: …" or "idle — last run finished …". Swapping the conditions means a page with both a running run and finished runs would incorrectly show "idle" instead of "RUNNING". No HTML test creates a fixture with both kinds of runs and verifies the status text; the fixture with a running run (`test_running_status_line`) has no finished runs, so `result["recent"]` is empty and the `elif current` branch fires.
mutation: Replaced `if current:` / `elif result["recent"]:` with `if result["recent"]:` / `elif current:` — checks for finished runs before checking for a running run
result: 71 passed
why: When a pipeline is executing a new run while older runs are visible in the table, the page header would say "idle" and a user would not know something is running.

### FINDING 3
axis: test-strength
file: scripts/status_page.py:583-595
severity: medium
confidence: verified
problem: The current-run panel renders title, kind, id, pipeline, elapsed, turns, and tool calls from the `current` dict. No test verifies any of these individual values in the panel. `test_html_200_contains_current_title` only checks that the string "Current run" (the `<h2>` heading) is present. `test_running_status_line` and `test_html_escapes_html_in_title` check the status_text (which uses `current.get('title', '')` but is separate from the panel). If all panel values were empty strings, every test would pass.
mutation: Replaced all `c_title`, `c_kind`, `c_id`, `c_pipeline`, `c_duration`, `c_turns`, `c_tool_calls` assignments with hardcoded empty/zero values instead of reading from `current`
result: 71 passed
why: The current-run panel would display blank fields (Title: , Kind: , ID: , etc.) even while a run is in progress. The status bar would show the title, but the detailed panel below would be empty.

### FINDING 4
axis: test-strength
file: scripts/status_page.py:711-712
severity: low
confidence: suspected
problem: The spec says the status line should be "the first element of `<body>`". No test verifies this ordering. `test_html_title_matches_status_line` checks that the title text appears somewhere in the body, but not at the top. The status line could appear after the current panel and all tests would pass.
mutation: Swapped `{status_text}` and `{current_panel}` in the HTML `<body>` template
result: 71 passed
why: The status line would not be the first element of `<body>` as the spec requires. Users seeing the page from top to bottom would encounter the current-run panel before the overall status (RUNNING / IDLE).

SUMMARY: test-strength=4 blocking=2 mutations-run=15 restored=yes