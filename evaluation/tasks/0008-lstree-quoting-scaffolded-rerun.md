---
id: 0008-lstree-quoting-scaffolded-rerun
repo: C:\Dev\homelab
category: bugfix
complexity: small
verify: python -m pytest -q
branch: worker/0008-lstree-quoting-scaffolded-rerun
base: experiment/74-local-llm-worker
---

<!--
FRAMING VARIANT 3 of 3 â€” FULLY SCAFFOLDED.
Same defect as 0004 and 0005, plus: the exact line, the approach to take, the
careless-fix trap called out explicitly, and the test module's conventions.
This is the "notes are cheap, supply them" end of the gradient.
-->

# Task: fix the HEAD-membership check in the credential inventory

**Edit `scripts/inventory-git-credential-exposure.py`.** Then **edit
`tests/test_inventory_git_credential_exposure.py`** to add a test covering the fix.

## The defect

In `inventory()`, the set of paths present in HEAD is built like this:

```python
head_paths = set(str(git(repository, "ls-tree", "-r", "--name-only", "HEAD")).splitlines())
```

That call omits `-z`, so Git applies C-style quoting to any path it considers unusual â€” a
non-ASCII filename comes back as `"hemmelig-v\303\246rdi.env"` rather than
`hemmelig-vÃ¦rdi.env`. Candidate paths elsewhere in the module are read with `-z` and decoded with
`surrogateescape`, so the two representations never match and a tracked file is misreported as
`history-only`.

## Acceptance criteria

- `status` is `current` exactly when the path is present in the HEAD tree, for every path Git can
  name, including non-ASCII ones.
- A path that was committed and later removed must still report `history-only`.
- New tests cover the non-ASCII case and the removed-path case.
- `python -m pytest -q` passes â€” the whole suite, not only the new tests.
- Return a concise summary of what changed and anything left unresolved.

## Constraints

- Do not change the detector regexes in `PATH_DETECTORS` or their behaviour.
- The tool must never emit credential values. Report paths and categories only.
- Change no files other than the two named above.

## Notes

- **Read the HEAD tree the same way the module already reads trees.** Around line 92 there is an
  existing `-z` call whose result is wrapped as `bytes(...)`, decoded with
  `.decode("utf-8", errors="surrogateescape")`, and split on `"\0"`. Follow that shape:
  `git(repository, "ls-tree", "-r", "--name-only", "-z", "HEAD", text=False)`. Note `-z` output
  ends with a trailing NUL, so drop empty fields â€” the module's own loop shows the
  `if not path: continue` convention.
- **Do not fix this with a filesystem check.** `(repository / path).exists()` looks equivalent and
  is wrong twice: an untracked leftover file on disk would report `current`, and a path deleted in
  HEAD but still present in the worktree would too. The check must be against the HEAD tree.
- `git()` returns `str` or `bytes` depending on `text`; the codebase casts explicitly
  (`bytes(git(...))`, `str(git(...))`) to keep type checkers quiet. Follow that.
- **Test conventions.** The module loads the hyphenated script via
  `importlib.util.spec_from_file_location` under the name `scanner`. Tests are plain
  `unittest.TestCase` with a `self.git(repository, *args)` helper. Fixtures are real Git
  repositories built inside `with tempfile.TemporaryDirectory() as directory:`, always
  `init -b main` plus `config user.name` and `config user.email test@example.invalid`, files
  written with `write_text(..., encoding="utf-8")`, then `add .` and `commit -m`. Assertions run
  against `scanner.inventory(repository)` using a `by_path = {item["path"]: item ...}` dict.
- The suite was green at 154 passed / 11 subtests before this task, so any other failure is a
  regression introduced here.
