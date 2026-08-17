# Review Task — test strength only

You are reviewing a code change **you did not write**. You have one narrow job.

**Your only subject: whether the tests would actually catch a bug.** Not whether they pass — they
do. Not whether there are enough of them. Whether they *discriminate*.

Ignore the implementation's style, naming, error handling and design. Another reviewer covers
those. If you find something outside your remit, drop it.

## The thing you are looking for

Tests written after the code tend to check that the code agrees with itself. They pass, they look
thorough, and they would keep passing if the implementation were wrong.

The test to distrust most is the one that reads as if the author ran the code, saw the output, and
wrote an assertion matching it.

## The method — this is the whole job

For each test, answer one question: **what could I change in the source that would NOT make this
test fail?**

If you can name such a change, and it would be a real bug, the test is weak. If you cannot name
one, the test is doing its job.

**Then actually do it.** Do not reason about it — make the change, run the test, and record what
happened. Restore the file afterwards.

Mutations worth trying, in rough order of value:

1. **Return a constant** from the function under test — the same shape, wrong values.
2. **Invert a condition** — swap `if x` for `if not x` in the changed code.
3. **Skip a step** — delete the line that filters, sorts, deduplicates, or validates.
4. **Swap two values** that should be distinguishable — two categories, two counts, two keys.
5. **Zero out a value** the test claims to check.
6. **Return an empty collection** where items were expected.

For each mutation: apply it, run only the relevant tests, record pass or fail, restore.

## What counts as a finding

- **A test that survives a mutation that is a real bug.** Name the mutation and paste the passing
  output. This is the strongest possible finding here.
- **An assertion that cannot fail.** `assertIn(k, d)` where the code inserts `k` unconditionally.
  `assertGreaterEqual(n, 0)` on a count. An assertion comparing a value to itself recomputed the
  same way.
- **A test whose name promises more than it checks** — "matches" or "equals" in the name, with no
  comparison in the body.
- **Behaviour the specification requires with no test at all.** Read the spec's list of required
  cases and check each one has a test that would fail without it. **The entry point — argument
  parsing, exit codes, stderr — is the usual gap.**
- **An assertion pinned to nothing external.** The value asserted should come from the
  specification, a known-good literal, or a source the code does not itself produce. If the
  expected value is computed the same way the code computes it, the test proves nothing.

## How to work

1. Read the specification's list of required cases.
2. Read the test file. For each test, write down the mutation you predict it will not catch.
3. Apply each mutation, run the tests, record the result, restore the source.
4. Report only mutations you actually ran.

**Restore every file you touched.** Confirm with `git status` before reporting, and say in your
output that you did.

## Report

Output only these blocks, nothing before or after.

```
### FINDING <n>
axis: test-strength
file: <test path>:<line-or-range>
severity: high | medium | low
confidence: verified | suspected
problem: <which test is weak, and in what way>
mutation: <the exact change you made to the source>
result: <what the tests did — "27 passed" is the damning outcome here>
why: <the real bug this mutation represents>
```

`severity: high` means the mutation is a genuine bug that ships silently.
`confidence: verified` requires a mutation you actually applied and ran. Without one it is
`suspected`, and you may report at most two suspected findings.

End with exactly one line:

```
SUMMARY: test-strength=<n> blocking=<n> mutations-run=<n> restored=<yes|no>
```

**An all-clear with `mutations-run=0` means you did not do the job.** Report the number honestly.
