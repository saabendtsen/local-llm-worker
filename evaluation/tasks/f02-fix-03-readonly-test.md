---
id: f02-fix-03-readonly-test
repo: C:\Dev\homelab
category: tests
complexity: small
verify: python -m ruff check scripts tests && python -m pytest -q
base: worker/f02-fix-02
branch: worker/f02-fix-03
---

# Task: pin the read-only constraint with a test

**Edit `tests/test_wayfinder_autopilot.py` only.**

**The implementation is already correct. Do not change it.** Every `mkdir` in the module lives in
the writer path; `list_runs` creates nothing. This task adds the test that holds that true.

## Current behavior

The specification says `history` is strictly read-only: it must not create the log directory, must
not acquire `RunLock`, and must not write anywhere.

The behaviour is correct but **nothing tests it**. A reviewer proved the gap by inserting
`runs_dir.mkdir(parents=True, exist_ok=True)` into `list_runs` — the existing tests still passed.

So the constraint holds today by accident of nobody having broken it, and one refactor would remove
it silently.

## Desired behavior

A test that fails if `history` creates anything on disk.

## Out of scope

- **Do not modify `scripts/wayfinder_autopilot.py` at all.** If you believe it needs changing, you
  have misread the task — the fix here is a test.
- Do not address any other review finding.
- Do not change existing tests except to add to the file.

## Cases the tests must cover

| Case | Source of truth for the assertion |
| --- | --- |
| `log_dir` does not exist at all; run `history` | afterwards the directory **still does not exist** — assert on the filesystem, not on the return value |
| `log_dir` exists but has no `runs/` subdirectory; run `history` | afterwards `runs/` **still does not exist**, and the result is the existing empty-listing shape |
| Either case | no `run.lock` file appears anywhere under the workspace |

The strongest form is to snapshot the set of paths under the workspace before and after, and assert
the two sets are equal. That catches any write, not only the ones anticipated here.

## Acceptance criteria

- [ ] The new test **fails** if `runs_dir.mkdir(parents=True, exist_ok=True)` is inserted into
      `list_runs`. Verify this yourself: insert it, watch the test fail, then remove it. Say in your
      summary that you did, and what the failure was.
- [ ] `git status` shows `scripts/wayfinder_autopilot.py` unmodified when you finish.
- [ ] `python -m ruff check scripts tests && python -m pytest -q` passes.
- [ ] Return a concise summary of what changed and anything left unresolved.

## Notes

- `AutopilotConfig` resolves a relative `log_dir` against `--workspace`, so a temporary workspace
  keeps the test hermetic and away from `%LOCALAPPDATA%`.
- Follow the existing test conventions: `unittest.TestCase`, fixtures built in `setUp` with
  `tempfile.TemporaryDirectory()`, torn down in `tearDown`.
