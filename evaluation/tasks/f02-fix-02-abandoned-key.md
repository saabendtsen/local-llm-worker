---
id: f02-fix-02-abandoned-key
repo: C:\Dev\homelab
category: bugfix
complexity: small
verify: python -m ruff check scripts tests && python -m pytest -q
base: worker/f02-fix-01
branch: worker/f02-fix-02
---

# Task: give unreadable-run entries the same keys as normal ones

**Edit `scripts/wayfinder_autopilot.py` and `tests/test_wayfinder_autopilot.py`. Nothing else.**

A single bounded fix. Do not refactor, do not improve anything the task does not name, and do not
touch any other finding.

## Current behavior

`list_runs` emits two different entry shapes. A normal run carries an `abandoned` key; an entry
built in the unreadable-run handler does not.

So a consumer iterating the `runs` list cannot index `entry["abandoned"]` uniformly — it works for
every normal run and raises `KeyError` on the first unreadable one.

## Desired behavior

Every entry in `runs` carries the same keys, whether the run was readable or not. An unreadable run
has no timestamps to judge, so its `abandoned` value should be whatever honestly represents "not
determinable" in the shape already in use — pick one and be consistent.

## Out of scope

- Do not change how `abandoned` is computed for normal runs.
- Do not change the sentinel state used for unreadable runs, the sort order, `--limit`, `--state`,
  or any other behaviour.
- Do not address any other review finding.

## Cases the tests must cover

| Case | Source of truth for the assertion |
| --- | --- |
| A directory containing one normal run and one unreadable run | **the key sets are equal** — assert `set(entry_a) == set(entry_b)` rather than listing keys by hand, so the test keeps holding if the schema grows |
| The unreadable entry specifically | `"abandoned"` is present, and its value is the not-determinable value you chose |
| A normal run | its `abandoned` value is unchanged from the current behaviour — read the existing test for it and pin the same literal |

## Acceptance criteria

- [ ] Every case above passes.
- [ ] `python -m ruff check scripts tests && python -m pytest -q` passes. Baseline on this branch is
      whatever the previous fix left green, so any failure is a regression.
- [ ] Return a concise summary of what changed and anything left unresolved.

## Notes

- The key-set equality assertion is deliberate. Listing expected keys by hand produces a test that
  passes while the two shapes drift apart again; comparing the sets directly cannot.
- Follow the module's existing conventions.
