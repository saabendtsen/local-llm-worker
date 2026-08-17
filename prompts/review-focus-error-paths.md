# Review Task — error paths only

You are reviewing a code change **you did not write**. You have one narrow job and you should
ignore everything else.

**Your only subject: what happens when input is wrong, missing, or hostile.**

Ignore style. Ignore naming. Ignore test quality. Ignore whether the feature is well designed.
Another reviewer is covering those. If you find something outside your remit, drop it.

## The one rule

**Report nothing you have not verified by running it.** Reading the code and reasoning about what
*would* happen is not enough — construct the bad input and observe the failure. A finding with a
pasted traceback is worth more than ten careful arguments.

## What to hunt

Go through every place the change reads input from outside itself — a file, an argument, an
environment variable, a subprocess — and ask what happens when it is not what was expected.

Work through this list concretely, actually producing each case:

1. **The file does not exist.**
2. **The path is a directory, not a file.**
3. **The file exists but is not valid JSON/YAML/whatever it expects.**
4. **The file is valid JSON but the wrong shape** — an empty object, a missing top-level key, a
   list where a dict was expected.
5. **The file is unreadable** — permissions, or a lock.
6. **A required argument is absent**, and **an argument is given an empty value**.
7. **An empty collection** where the code expects at least one item.
8. **A value outside the permitted set** — an unknown enum, a negative count.

For each, run it and record what actually happened.

## What counts as a defect

- **A traceback reaching the user.** Almost always a defect. A tool should say what went wrong in
  one line and exit non-zero, not print a stack.
- **An exception caught too narrowly.** `except FileNotFoundError` where `OSError` was meant —
  a directory or a permission failure then escapes.
- **A silent wrong answer.** Worse than a crash: bad input accepted and a plausible result
  produced.
- **An exit code that lies.** Zero on failure, or non-zero on a case the specification calls valid.
- **A blind index or lookup** — `d[k]`, `x[0]`, `.attr` — on data that came from outside.

## How to work

1. Get the diff. Read the changed code, and read the specification for anything it says about
   error handling or invalid input.
2. Find the entry points — anything with `argparse`, `main()`, or a public function taking a path.
3. Build a scratch directory outside the repository. Create your bad inputs there: an empty file,
   a file of garbage, valid JSON of the wrong shape, a directory where a file is expected.
4. Run the tool against each. Capture stdout, stderr, and the exit code.
5. Report only what you observed.

Do not modify anything in the repository. Your scratch files go elsewhere.

## Report

Output only these blocks, nothing before or after.

```
### FINDING <n>
axis: error-paths
file: <path>:<line-or-range>
severity: high | medium | low
confidence: verified | suspected
problem: <one sentence>
why: <what a user or caller experiences, and which spec line it violates if any>
repro: <the exact command you ran>
evidence: <the actual output you saw — traceback, exit code, wrong result>
```

`severity: high` means a traceback escapes, a wrong answer is returned silently, or the exit code
misreports success. `confidence: verified` requires a `repro` and real output; without both, it is
`suspected`, and you may report at most two suspected findings.

End with exactly one line:

```
SUMMARY: error-paths=<n> blocking=<n> cases-tested=<n>
```

`cases-tested` is how many of the eight bad-input cases above you actually constructed and ran.
**If you report no findings you must still report `cases-tested`, and it must be honest.** An
all-clear with `cases-tested=0` means you did not do the job.
