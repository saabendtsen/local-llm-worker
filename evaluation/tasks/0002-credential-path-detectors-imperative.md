---
id: 0002-credential-path-detectors-imperative
repo: C:\Dev\homelab
category: feature-small
complexity: small
verify: python -m pytest -q
branch: worker/0002-credential-path-detectors-imperative
---

<!--
Controlled rerun of task 0001. The substance, constraints, and acceptance
criteria are deliberately identical; only the framing changes, so the two runs
isolate one variable.

0001 opened by describing an outcome ("detect well-known credential-bearing
config filenames") and the worker audited the repository for credentials
instead of editing any code. This version opens with an imperative naming the
file to modify in the first sentence, and states the deliverable before any
background.
-->

# Task: add a detector category to PATH_DETECTORS

**Edit the file `scripts/inventory-git-credential-exposure.py`.** Add one new entry to its
`PATH_DETECTORS` dictionary. Then **edit `tests/test_inventory_git_credential_exposure.py`** to
add tests covering it.

This is a code change. Do not audit the repository for credentials; do not produce a report.
The deliverable is a diff in those two files.

## Background

`PATH_DETECTORS` maps a category name to a compiled regex matched against a repository-relative
path. It currently has three entries: `environment-file`, `credential-name`, and
`private-key-name`.

None of them match a family of well-known config files that routinely carry credentials —
`.netrc`, `.npmrc`, `.pypirc`, and `kubeconfig`. A repository that committed one of these would
not be flagged. The new entry closes that gap.

## Constraints

- **The tool must never emit credential values.** This is the module's core invariant, enforced
  by `FORBIDDEN_PAYLOAD_FIELDS` and `assert_value_free`. Report paths and categories only. Do not
  add any field that could carry file contents, matched text, or a line excerpt.
- Do not change the three existing detector categories, their names, or their behaviour.
  Repositories already inventoried must keep classifying the same way.
- Do not change the output schema beyond what a new category naturally requires.
- Change no files other than the two named above.

## Acceptance criteria

- A committed `.netrc`, `.npmrc`, `.pypirc`, or `kubeconfig` is reported under the new category.
- A longer, unrelated filename that merely contains one of those words as a substring is not
  falsely flagged.
- New tests cover both the positive and the negative case, following the existing style in
  `tests/test_inventory_git_credential_exposure.py`.
- `python -m pytest -q` passes — the whole suite, not only the new tests.
- Return a concise summary of what changed and anything left unresolved.

## Notes

- The regex is matched against the path, so it must handle both a bare filename and one nested in
  a directory. The three existing entries show the anchoring convention.
- The test module builds real temporary Git repositories and runs the script over them; follow
  that approach rather than mocking.
- The suite was green at 154 passed / 11 subtests before this task, so any other failure is a
  regression introduced here.
