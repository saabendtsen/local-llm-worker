---
id: 0003-credential-path-detectors-rerun
repo: C:\Dev\homelab
category: feature-small
complexity: small
verify: python -m pytest -q
branch: worker/0003-credential-path-detectors-rerun
---

# Task: detect well-known credential-bearing config filenames

`scripts/inventory-git-credential-exposure.py` inventories credential-bearing paths in Git
history. Its `PATH_DETECTORS` currently recognises environment files, credential-shaped names,
and private-key names.

It does not recognise a family of well-known config files that routinely carry credentials and
whose names match none of the existing patterns — for example `.netrc`, `.npmrc`, `.pypirc`, and
`kubeconfig`. A repository that committed one of these would not be flagged.

Add detection for that family.

## Constraints

- **The tool must never emit credential values.** This is the module's core invariant, enforced
  by `FORBIDDEN_PAYLOAD_FIELDS` and `assert_value_free`. Detection reports *paths and categories*
  only. Do not add any field that could carry file contents, matched text, or a line excerpt.
- Do not change the existing detector categories, their names, or their behaviour. Repositories
  already inventoried must keep classifying the same way.
- Do not change the output schema beyond what a new category naturally requires.
- Stay inside `scripts/inventory-git-credential-exposure.py` and
  `tests/test_inventory_git_credential_exposure.py`.

## Acceptance criteria

- A committed `.netrc`, `.npmrc`, `.pypirc`, or `kubeconfig` is reported with a detector category
  distinguishing it from the existing three.
- A path that merely *contains* one of those words as a substring of a longer, unrelated filename
  is not falsely flagged.
- New tests cover both the positive and the negative case, following the existing style in
  `tests/test_inventory_git_credential_exposure.py`.
- `python -m pytest -q` passes — the whole suite, not only the new tests.
- Return a concise summary of what changed and anything left unresolved.

## Notes

- `PATH_DETECTORS` maps a category name to a compiled regex matched against the repository-
  relative path, so the pattern needs to handle both a bare filename and one nested in a
  directory. The existing entries show the anchoring convention.
- The test module builds real temporary Git repositories and runs the script over them; follow
  that approach rather than mocking.
- The whole suite was green at 154 passed / 11 subtests before this task, so any other failure is
  a regression introduced here.
