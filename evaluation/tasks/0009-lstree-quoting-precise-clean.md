---
id: 0009-lstree-quoting-precise-clean
repo: C:\Dev\homelab
category: bugfix
complexity: small
verify: python -m pytest -q
branch: worker/0009-lstree-quoting-precise-clean
base: experiment/74-local-llm-worker
---

<!--
FRAMING VARIANT 2 of 3 â€” PRECISE IMPERATIVE.
Names the files and states the target behaviour exactly, but gives no
implementation approach, no edge-case warning, and no test conventions.
-->

# Task: fix the HEAD-membership check in the credential inventory

**Edit `scripts/inventory-git-credential-exposure.py`.** Then **edit
`tests/test_inventory_git_credential_exposure.py`** to add a test covering the fix.

## The defect

The `inventory()` function classifies each candidate path with a `status` field of either
`current` (present in HEAD) or `history-only` (only reachable in history). The set it checks
membership against is built from a `git ls-tree` call whose output is subject to Git's C-style
path quoting. Candidate paths are decoded differently, so the two representations do not match
for any path Git chooses to quote â€” non-ASCII paths in particular.

The result: a file that *is* tracked in HEAD is reported as `history-only`.

## Acceptance criteria

- `status` is `current` exactly when the path is present in the HEAD tree, for every path Git can
  name, including non-ASCII ones.
- A path that was committed and later removed must still report `history-only`.
- A new test covers the non-ASCII case.
- `python -m pytest -q` passes â€” the whole suite, not only the new test.
- Return a concise summary of what changed and anything left unresolved.

## Constraints

- Do not change the detector regexes in `PATH_DETECTORS` or their behaviour.
- The tool must never emit credential values. Report paths and categories only.
- Change no files other than the two named above.
