---

### FINDING 1
axis: consistency
file: scripts/status_page.py:655-662
severity: high
confidence: verified
problem: Groups header counts (running/finished) include all runs from `all_runs`, but the HTML table iterates only `result["recent"]` which contains finished runs only (capped at 10). Running runs never appear in any table row despite the header declaring them.
why: `_serve_html` loops `for run in result["recent"]` (line ~655), but `result["recent"]` only holds finished runs — running runs are in `result["running"]`, never in `recent`. The group header (`Pipeline: f03 (1 running, 2 finished)`) is built from `all_runs` which correctly counts running runs, so the header says "1 running" while the table shows 0 running rows. On 12+ finished runs the gap is wider: the group lists 12 runs but the table can only show 10.
repro: Create 1 running run + 5 finished runs in pipeline "f03". Run: `python -c "exec(open('/tmp/check2.py').read())"` (standalone script in /tmp/check2.py)
evidence: groups["f03"]["running"] = 1, but HTML table iterates `result["recent"]` (5 finished runs) and finds 0 running rows. The running run "f03-run1" is present in `groups[...]["runs"]` and `result["running"]` but never rendered. With 12 finished runs: groups["f03"]["runs"] has 12 entries, recent is capped at 10, table shows 10 rows — 2 runs hidden.

### FINDING 2
axis: consistency
file: tests/test_status_page.py:910-912
severity: low
confidence: verified
problem: The test docstring says "two ### FINDING and one #### FINDING → findings==2" but the actual assertion is `findings == 3`, and the review.md content has three lines starting with "### FINDING" (one, two, four) and one line starting with "#### FINDING" (three). The assertion is correct; the docstring is misleading.
why: The docstring states 2 but the content has 3 matching lines. The code correctly counts all lines starting with "### FINDING", yielding 3. The test passes with `self.assertEqual(detail["findings"], 3)`. This is a documentation inconsistency, not a code bug.
repro: Read line 910-912 of tests/test_status_page.py — docstring says 2, assertion says 3, code produces 3.
evidence: review.md = "### FINDING one\n### FINDING two\n#### FINDING three\n### FINDING four\n". Lines starting with "### FINDING": 3. Test assertion: `findings == 3`. Docstring: "→ findings==2".

SUMMARY: consistency=2 blocking=1 relations-checked=5