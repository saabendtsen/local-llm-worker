---
id: b01-02-staging-cleanup
repo: C:\Dev\homelab
category: bugfix
complexity: small
verify: python -m pytest -q tests/test_codex_task_bridge.py
---

# Task: remove the staging directory when a submit fails

**Edit `scripts/codex_task_server.py`.** Then **edit `tests/test_codex_task_bridge.py`** to add a
test covering the fix.

## The defect

`Bridge.submit` creates a staging directory `.{task_id}.tmp` before validating anything, and moves
it into place with `os.replace(staging, task_dir)` only on success. Nothing anywhere in the module
ever removes it on failure.

So every rejected submit — bad input name, duplicate name, malformed base64, `max_input_bytes`
exceeded, working directory outside the allowlist — leaks a staging directory permanently.
`queued_tasks()` skips dot-prefixed directories, so the garbage is invisible and unbounded. The
existing test suite leaks one on every run.

## Acceptance criteria

- After any failed `submit`, no `.{task_id}.tmp` directory remains in `tasks_dir`.
- The original exception still propagates unchanged, with its type and message intact. Existing
  tests assert on those, and they must keep passing.
- A successful submit is unaffected: `tasks_dir` ends up containing exactly the real `{task_id}`
  directory and nothing else.
- A new test asserts the absence of leftovers after a failure — asserting on
  `sorted(p.name for p in bridge.tasks_dir.iterdir())` is the cleanest way.
- `python -m pytest -q tests/test_codex_task_bridge.py` passes.
- Return a concise summary of what changed and anything left unresolved.

## Constraints

- Do not change the atomicity design: build in `.{task_id}.tmp`, then `os.replace` into place.
- Do not change the validation rules or any error message.
- Change no files other than the two named above.

## Notes

- A blanket `finally: shutil.rmtree(staging)` is wrong: on the happy path the staging directory has
  already been renamed away, so it would raise `FileNotFoundError`. Pointing the cleanup at
  `task_dir` instead would delete the task that was just accepted.
- The cleanup must not swallow the exception. A bare `except Exception: cleanup; return None` makes
  `test_rejects_unsafe_input_name` and `test_rejects_working_directory_outside_allowlist` fail.
- `base64.b64decode(..., validate=True)` raises `binascii.Error`, which subclasses `ValueError` —
  the cleanup needs to cover that path too.
- `shutil` is not currently imported. Adding it is expected.
- Test conventions are as in the previous step: plain `unittest.TestCase`, temp-directory fixtures,
  `assertRaisesRegex` for error cases.
