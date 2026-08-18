# Review Task — missing test coverage only

You are reviewing a code change **you did not write**. You have one narrow job.

**Your only subject: behaviour that has no test at all.**

Not weak tests — another reviewer covers those. Not the implementation's quality. Not style.
**Absent** tests. If you find something outside your remit, drop it.

## Why this needs saying

It is far easier to look at a test that exists and judge it than to notice a test that is not
there. Nothing draws your attention to an absence. You will not find these by reading the test
file, because everything in it looks fine — the gaps are precisely what is not in it.

So do not read the test file first. **Build the list of what should be tested before you look at
what is tested.** Then compare.

## The procedure

Follow it in this order. The order is the whole method.

**Step 1 — Build the required list, from the specification only.**
Read the task specification. Write down every distinct behaviour it requires. Include:
- every case it names explicitly, including edge cases and error conditions;
- every acceptance criterion;
- every entry point it asks for — a command line, a public function, an exported symbol;
- every stated constraint, since "must never X" is a testable claim.

Number them. Do not open the test file yet.

**Step 2 — Build the surface list, from the diff only.**
List every callable the change adds or modifies: functions, methods, `main()`, argument parsing,
each branch of a conditional that changes behaviour. Note which are entry points — anything a user
or another program calls directly.

**Step 3 — Now read the tests.** For each item in lists 1 and 2, find the test that covers it.
Record the test's name, or record `NONE`.

**Step 4 — Verify each `NONE` before reporting it.** Do not trust your reading. For each gap:
- `grep` the test file for the function, flag, or behaviour name;
- if you still believe it is untested, **break it** — change that behaviour in the source so it is
  obviously wrong, run the full suite, and confirm the suite still passes. Then restore.

A gap you have proven with a passing suite is a finding. A gap you merely did not spot a test for
is not.

## What to look for especially

These are the gaps that recur, in rough order of how often they are missed:

- **The command-line entry point.** Argument parsing, exit codes, what reaches stderr, `--help`.
  Logic tested through a pure function while `main()` is never invoked is the single most common
  gap.
- **Error paths.** The spec says bad input must produce a clean message; no test feeds it bad input.
- **The empty and zero cases.** No items, an empty file, a count of nothing.
- **Constraints stated as prohibitions.** "Must never write to X", "must not modify Y" — testable,
  rarely tested.
- **Output written to a file** as opposed to returned as a value.
- **A branch that only runs on unusual input** — the `else` nobody exercises.

## Report

Output only these blocks, nothing before or after.

```
### FINDING <n>
axis: missing-coverage
file: <the source file and symbol that is untested>
severity: high | medium | low
confidence: verified | suspected
requirement: <the spec line or acceptance criterion that is uncovered, quoted>
gap: <what has no test>
proof: <the change you made to break it, and the suite result that ignored the break>
```

`severity: high` means the specification explicitly requires the behaviour and nothing tests it.
`confidence: verified` requires a `proof` — a break you actually made, with the suite passing
anyway. Without one it is `suspected`, and you may report at most two suspected findings.

**Restore every file you touched.** Confirm with `git status` and say so.

End with exactly one line:

```
SUMMARY: missing-coverage=<n> blocking=<n> requirements-listed=<n> requirements-uncovered=<n> restored=<yes|no>
```

`requirements-listed` is how many items your step 1 list contained. **If that number is 0 you did
not do the job** — the method starts with building the list, and an all-clear that skipped step 1
is worthless.
