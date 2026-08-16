---
id: 0000-short-slug
repo: C:\Dev\homelab\repos\some-repo
category: tests
complexity: small
verify: python -m pytest -q
branch: worker/0000-short-slug
---

<!--
Written by Claude, executed by the local worker, scored by Claude.

Everything below the frontmatter is sent to the worker verbatim as its prompt.
Describe the outcome and its boundaries. Do NOT list the edits to make -- the
worker determines those. Prescribing the changes defeats the purpose: if the
plan already contains every edit, the reasoning cost has been paid and the
delegation measured nothing.

Frontmatter fields:
  id         unique; also names the run directory under evaluation/runs/
  repo       absolute path to the target Git repository
  category   boilerplate | tests | docs | feature-small | feature-medium
             | refactor | bugfix
  complexity rough size: small | medium
  verify     the acceptance command; its exit code decides pass/fail
  branch     optional; defaults to worker/<id>
  base       optional but strongly recommended: the branch to start from.
             Without it the run branches from whatever is checked out, which
             has twice meant silently inheriting an earlier run's work and
             measuring nothing. Set it whenever the run is a measurement.
-->

# Task: <short title>

<One paragraph. What should be true when this is done.>

## Constraints

- <What must not change: public APIs, file formats, save compatibility, behaviour>
- <Scope boundaries: which directories are in play>

## Acceptance criteria

- <Verifiable statement>
- <Relevant tests are added>
- `<the verify command>` passes
- Return a concise summary of what was modified and anything left unresolved.

<!--
Two things learned from E6, where three independent implementations shared the
same two blind spots. Add them to the criteria whenever they apply.

1. NAME THE SOURCE OF TRUTH each assertion must be pinned to. "Cover the
   per-kind breakdown" produced self-consistency checks in all three arms --
   assertions that any internally coherent wrong answer satisfies. "Assert the
   per-kind counts equal registry["summary"]["by_kind"]" would have produced a
   real check. Tests written after working code verify that the code agrees
   with itself unless an external truth is named.

2. ASK FOR THE ENTRY POINT TO BE TESTED. All three arms put the logic in a
   clean pure function as asked, and none tested main(). All three then shipped
   error-path defects -- tracebacks on malformed input, in violation of a stated
   constraint. If the command line is a deliverable, say that its argument
   parsing, exit codes, and error messages must be covered.
-->


## Notes

<Anything already known that would otherwise cost the worker a long detour:
the pattern to follow, an existing design doc, a known gotcha. This is cheap to
supply and is the difference between a bounded task and an open-ended one.>
