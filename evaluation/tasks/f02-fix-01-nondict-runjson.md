---
id: f02-fix-01-nondict-runjson
repo: C:\Dev\homelab
category: bugfix
complexity: small
verify: python -m ruff check scripts tests && python -m pytest -q
base: worker/f02-wayfinder-history
branch: worker/f02-fix-01
---

# Task: handle a `run.json` that is valid JSON but not an object

**Edit `scripts/wayfinder_autopilot.py` and `tests/test_wayfinder_autopilot.py`. Nothing else.**

This is a single, bounded fix. Do not refactor, do not improve anything the task does not name, and
do not touch any other finding.

## Current behavior

`list_runs` raises an unhandled `AttributeError` when a run directory contains a `run.json` whose
contents parse as JSON but are not a dictionary.

Reproduce it:

```
# with <workspace>/logs/runs/20260816T120000-000000/run.json containing:  [1, 2, 3]
python scripts/wayfinder_autopilot.py --workspace <workspace> history
```

The existing handler catches `json.JSONDecodeError` and `OSError`, which covers a *truncated* file
but not a *well-formed* one of the wrong type. A JSON list, string, or number reaches the code that
expects a mapping.

## Desired behavior

Such a run is reported as unreadable, exactly as a truncated `run.json` already is — same entry
shape, same sentinel state. No traceback, exit code 0.

## Out of scope

- Do not change how a *truncated* `run.json` is handled; it already works.
- Do not change the entry schema, the sort order, `--limit`, `--state`, or any other behaviour.
- Do not address any other review finding, however tempting.

## Cases the tests must cover

| Case | Source of truth for the assertion |
| --- | --- |
| `run.json` containing `[1, 2, 3]` | the run appears with the **same sentinel state** the existing truncated-JSON test asserts — read that test and use its literal, do not invent a new one |
| `run.json` containing `"a string"` | same |
| `run.json` containing `42` | same |
| A valid run beside a non-dict one | the valid run is still listed, with its own `run_id` and `state` intact |
| The command line, end to end | process exit code **0**, and stdout parses as JSON. Note `main()` returns 2 when it catches `json.JSONDecodeError`, so asserting "no traceback" is not enough — assert the exit code is 0 |

## Acceptance criteria

- [ ] Every case above passes.
- [ ] `python -m ruff check scripts tests && python -m pytest -q` passes. Baseline on this branch is
      **172 passed, 11 subtests passed** with ruff clean, so any other failure is a regression.
- [ ] Return a concise summary of what changed and anything left unresolved.

## Notes

- The narrowest correct change is to widen what the existing handler tolerates, or to validate the
  parsed object's type before use. Both are fine; pick one and keep it small.
- Follow the module's conventions already in place: `from __future__ import annotations`, plain
  `dict` returns, private helpers prefixed `_`, `pathlib` only.
- Ruff runs before pytest in the acceptance command, so an unused import fails the whole thing.
