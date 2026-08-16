---
id: 0004-lstree-quoting-terse
repo: C:\Dev\homelab
category: bugfix
complexity: small
verify: python -m pytest -q
branch: worker/0004-lstree-quoting-terse
---

<!--
FRAMING VARIANT 1 of 3 — MINIMAL.
Outcome only. No file named, no approach, no edge cases, no conventions.
Compare against 0005 (precise) and 0006 (fully scaffolded). The underlying
defect is identical in all three; only the description changes.
-->

# Task

The credential-exposure inventory misreports tracked files as `history-only` when their path
contains non-ASCII characters, even though those files are present in HEAD. Fix it, and add a
test.

`python -m pytest -q` must pass.
