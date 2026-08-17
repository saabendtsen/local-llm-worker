---
id: 0000-short-slug
repo: C:\Dev\homelab
category: tests
complexity: small
verify: python -m pytest -q
base: experiment/74-local-llm-worker
branch: worker/0000-short-slug
---

<!--
Written by Claude, executed by the local worker, scored by Claude.

Everything below the frontmatter is sent to the worker verbatim as its prompt.

STRUCTURE borrowed from the Matt Pocock `triage` skill's AGENT-BRIEF template
(Current behavior / Desired behavior / Key interfaces / Out of scope) and from
`to-spec` step 2 (declare the seams under test). Its own justification fits this
setup exactly: "The original body and discussion are context — the agent brief
is the contract."

ONE PRINCIPLE OF THAT TEMPLATE IS DELIBERATELY REJECTED. It insists on avoiding
file paths and line numbers because a brief "may sit in ready-for-agent for days
or weeks" and they go stale. Our tasks are written and executed minutes apart,
and E1 measured the opposite: naming the file and the offending line cut effort
to a third for the same correctness. Name them.

Frontmatter fields:
  id         unique; also names the run directory under evaluation/runs/
  repo       absolute path to the target Git repository
  category   boilerplate | tests | docs | feature-small | feature-medium
             | refactor | bugfix
  complexity rough size: small | medium
  verify     the acceptance command; its exit code decides pass/fail
  base       strongly recommended: the branch to start from. Without it the run
             branches from whatever is checked out, which has twice meant
             silently inheriting an earlier run's work and measuring nothing.
  branch     optional; defaults to worker/<id>
-->

# Task: <short title>

**<One sentence: what should be true when this is done.>**

## Current behavior

<What happens now. Quote the offending code with its path and line if it is short —
see the note above about deliberately naming paths.>

## Desired behavior

<What should happen instead, including edge cases and error conditions. Behavioural,
not procedural: describe the outcome, not the sequence of edits.>

## Key interfaces

<Named types, function signatures, config shapes and invariants the worker should
know about. This is the cheap scaffolding that E1 showed buys speed for free — it
saves the worker rediscovering what you already know.>

- `<name>` — <shape, or the invariant it must preserve>

## Seams under test

<REQUIRED. Borrowed from `to-spec`: name the layers a test must exercise, highest
seam first, and mark any that are mandatory.

This exists because of E6: three independent implementations all put the logic in
a clean pure function as asked, all left the command-line entry point untested,
and all three shipped the same error-path defect as a result. A reminder in a
comment did not prevent it; a declared field does.>

- `<entry point>` — <argv parsing, exit codes, stderr on bad input>  [REQUIRED]
- `<pure function>` — <the happy path and its edge cases>

## Cases the tests must cover

<REQUIRED, and the highest-value section here. No external skill supplies it.

Enumerate the cases. E2 versus E1 showed that listing the exact inputs a test must
handle produces tests that discriminate, while warning about a mistake to avoid
produces an implementation that dodges the mistake and a test that misses it.

Name the SOURCE OF TRUTH for each assertion. E6 showed all three implementations
writing self-consistency checks — assertions any internally coherent wrong answer
satisfies — when the task did not say what to pin them to. The truth must come
from outside the code: a known-good literal, a worked example, a value the
codebase already publishes.>

| Case | Source of truth for the assertion |
| --- | --- |
| <concrete input> | <the literal, file, or published value it must equal> |

## Out of scope

- <What must not change: public APIs, file formats, behaviour, other files>

## Acceptance criteria

- [ ] <Verifiable statement>
- [ ] `<the verify command>` passes — the whole suite, not only the new tests
- [ ] Return a concise summary of what was modified and anything left unresolved.

## Notes

<Anything already known that would otherwise cost a long detour: the pattern to
follow, an existing design doc, a known gotcha, the test module's fixture style.>
