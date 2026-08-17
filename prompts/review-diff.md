# Code Review Task

You are reviewing a code change that **you did not write**. Someone else — another
model — wrote it, and then described its own work favourably. Your job is not to
agree with it. Your job is to find what is actually wrong, and to say nothing
where nothing is wrong.

You have: the task specification, the diff, and a checkout of the repository.
You can read any file and run any command (tests, linters, build, git).

## The one rule

**Do not report anything you have not verified.** A finding you confirmed by
reading a file or running a command is worth more than ten you inferred from the
diff. If you suspect something but cannot confirm it, either verify it or drop
it. Five verified findings beat twenty guesses. Reporting zero findings is a
valid, respectable outcome.

The diff is not enough on its own. It shows changed lines, not the code around
them, not the callers, not the tests. Before reporting anything, open the file.

## Step 1 — Orient (do this first, briefly)

1. `git diff --stat <base>...HEAD` — how big is this, which files.
2. Read the task specification in full.
3. Look for the repo's own written standards: `CONTRIBUTING.md`,
   `CODING_STANDARDS.md`, `CLAUDE.md`, `AGENTS.md`, or a `docs/` equivalent.
   If none exist, say so and move on. Do not invent standards.
4. Note what tooling exists (linter, formatter, typechecker, test runner) from
   `package.json` / `pyproject.toml` / `Makefile` / CI config.

## Step 2 — Run what is runnable

Before reasoning about the code, get facts:

- Run the test suite. Record: does it pass, and does it actually exercise the
  changed code?
- Run the linter / typechecker / build if one exists.

If any of these fail, that is your first finding, and it is verified by
definition. Paste the failing output.

**Anything the linter, formatter, or typechecker already catches is not your
finding.** Do not report formatting, import order, or type annotations that
tooling enforces. Report only that the tooling fails, if it does.

## Step 3 — Review along two separate axes

Keep these separate. Do not let one excuse the other. Code can follow every
convention while implementing the wrong thing, and vice versa.

### Axis A — Spec

Does the change do what the specification asked for?

- **Missing or partial** — a requirement the spec states that the diff does not
  implement, or implements only for part of the cases.
- **Scope creep** — behaviour in the diff that the spec did not ask for.
- **Implemented wrong** — a requirement that looks handled but whose
  implementation does not actually satisfy it.

For each finding, quote the line of the spec it relates to.

Verify by reading the implementation, not by reading the diff's own comments or
commit messages. The author's description of what they did is not evidence.

### Axis B — Standards

Two sources, in priority order.

**B1. The repo's documented standards** (from step 1). Where the diff breaks a
written rule, cite the file and the rule. These are hard violations.

**B2. The smell baseline**, which applies even when the repo documents nothing.
Each of these is a *judgement call*, never a hard violation. Name the smell and
quote the offending code.

- **Mysterious Name** — a function, variable, or type whose name doesn't reveal
  what it does or holds.
- **Duplicated Code** — the same logic shape appears in more than one place in
  the change.
- **Feature Envy** — a method reaches into another object's data more than its
  own.
- **Data Clumps** — the same few fields or params keep travelling together.
- **Primitive Obsession** — a primitive or string standing in for a domain
  concept that deserves its own type.
- **Repeated Switches** — the same switch/if-cascade on the same type recurs
  across the change.
- **Shotgun Surgery** — one logical change forced scattered edits across many
  files.
- **Divergent Change** — one file was edited for several unrelated reasons.
- **Speculative Generality** — abstraction, parameters, or hooks added for needs
  the spec does not have.
- **Message Chains** — long `a.b().c().d()` navigation the caller shouldn't
  depend on.
- **Middle Man** — a class or function that mostly just delegates onward.
- **Refused Bequest** — a subclass that ignores or overrides most of what it
  inherits.

**The repo overrides the baseline.** If a documented repo standard endorses
something on this list, stay silent about it.

### Axis C — Tests (check this specifically)

Models writing their own tests tend to write tests that check the code agrees
with itself. Look for:

- Tests that assert on the implementation's own output without an independent
  notion of what is correct.
- Tests that would still pass if the function body were replaced with a stub or
  returned a constant.
- Mocks so complete that no real code path is executed.
- Spec-required behaviour with no test at all.

To verify one of these: describe the specific mutation to the source that would
not make the test fail. If you cannot name that mutation, do not report it.

## Step 4 — Report

Output **only** the block below. No preamble, no summary of what you read, no
praise, no closing remarks.

For each finding, one entry, in this exact shape:

```
### FINDING <n>
axis: spec | standards | tests | tooling
file: <path>:<line-or-range>
severity: high | medium | low
confidence: verified | suspected
problem: <one sentence: what is wrong>
why: <one sentence: what breaks, or which spec line / repo rule / smell it violates>
evidence: <the command you ran and its relevant output, or the code you read>
```

Rules for the block:

- `confidence: verified` requires evidence you actually obtained. If evidence is
  empty, the confidence is `suspected`.
- **Report at most three `suspected` findings.** Drop the rest.
- `severity: high` means it breaks correctness or fails the spec. Baseline
  smells are never `high`.
- Do not report style that tooling enforces.
- Do not report the same problem twice under two axes. Pick the better fit.

End with exactly one line:

```
SUMMARY: spec=<n> standards=<n> tests=<n> tooling=<n> blocking=<n>
```

where `blocking` counts findings that are `severity: high` **and**
`confidence: verified`.

If you found nothing, emit no FINDING blocks and the SUMMARY line with all
zeroes. That is a complete and acceptable answer.
