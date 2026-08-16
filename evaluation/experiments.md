# Experiment log

Designed experiments, each with a hypothesis stated *before* the result. Per-task scoring lives in
[results.md](results.md); this file records what question was being asked and what was learned.

Write the hypothesis down first. It is the only defence against reading whatever happened as
confirmation of whatever was expected — and this project has already published one confident
conclusion that turned out to be a harness bug.

---

## E1 — Does task framing change output quality?

**Status:** running (2026-08-16)

**Question.** Søren's hypothesis: *"I assume the task needs to be very well defined."* Plausible,
and the literature supports it, but this project has no evidence yet — the run intended to test it
(0002) was invalidated by a truncated prompt.

**Method.** One identical underlying defect, described three ways. Only the description varies.

The defect: in `scripts/inventory-git-credential-exposure.py`, `head_paths` is built from a
`git ls-tree` call without `-z`, so Git's C-style quoting makes non-ASCII tracked paths compare
unequal and be misreported as `history-only` when they are present in HEAD.

| Run | Framing | What the task supplies |
| --- | --- | --- |
| 0004 | **Minimal** | Outcome only. No file named, no approach, no edge cases, no conventions. |
| 0005 | **Precise imperative** | Files named, target behaviour stated exactly, constraints. No approach, no edge-case warning, no conventions. |
| 0006 | **Fully scaffolded** | All of 0005, plus the offending line, the `-z` approach, the `exists()` trap called out, and the test module's conventions. |

**What is measured.** Turns, tool calls, wall clock, whether the acceptance command passes, and —
the part that actually matters — whether the diff is *correct*, judged by reading it. Each run is
reviewed by a separate subagent with a fresh context, blind to which framing produced it, so the
rating is not primed by knowing how much help the worker was given.

**The discriminator.** A careless fix is `(repository / path).exists()`. It passes a naive
non-ASCII test and is wrong twice over: an untracked leftover file reports `current`, and a path
deleted in HEAD but still on disk reports `current` too. Only 0006 warns about this. If 0004 or
0005 falls into it, that is direct evidence that scaffolding buys correctness rather than just
speed.

**Predictions, recorded in advance.**
1. Turn count falls as scaffolding rises — the minimal variant spends turns rediscovering what the
   scaffolded one was told.
2. All three may pass `verify`, because the suite is green either way and a weak test proves little.
   Pass rate is expected to be the *least* informative signal here.
3. The interesting outcome is if 0004 produces a plausible-but-wrong fix. That would be the
   quiet-failure mode, and would make scaffolding a correctness requirement rather than a nicety.

**Result.**

Three runs with a verified-clean base (`ae957ca`) and verified prompt delivery:

| Run | Framing | Wall clock | Turns | Diff | Verify | Review verdict |
| --- | --- | --- | --- | --- | --- | --- |
| 0004 | Minimal | 617.6 s | 26 | 2 files, +20/−1 | passed | **CLEAN** |
| 0009 | Precise | 1377.9 s | 2 | **0 files** | passed(!) | **FAILED — reasoning runaway** |
| 0008 | Scaffolded | 210.3 s | 8 | 2 files, +40/−1 | passed | **CLEAN** |

Voided runs, kept for the record: 0005 (clean base, but a review agent mutated the tree mid-run),
0006 and 0007 (branched from 0004's commit, so they began with the defect already fixed).

**Detail buys speed, not correctness.** Both the minimal and the fully scaffolded framing produced
correct, mergeable fixes that avoided the `exists()` trap and passed mutation testing. The
scaffolded run got there in **8 turns and 210 s** against **26 turns and 617 s** — roughly a third
of the effort for the same outcome. The minimal variant spent its extra turns writing standalone
repro scripts to rediscover what the scaffolded task simply stated.

**The scaffolding did not transfer to test design.** This is the sharpest finding. The scaffolded
task explicitly warned about the `exists()` trap and explained why it is wrong. The worker duly
avoided it *in the implementation* — and then wrote tests that do not catch it. The reviewer
substituted the wrong fix and ran 0008's own tests against it: **6 passed**. Its removed-path test
unlinks the file from disk as well as from the index, so it cannot distinguish tree membership
from filesystem existence. One extra line — recreating the file on disk after the removal commit —
would have made it trap-proof.

So a warning in the task shapes what the worker *does* but not what it *defends against*. If a
test must discriminate against a specific wrong implementation, say so explicitly; do not assume
that explaining the trap produces a test for it.

**0009 is not a framing result.** It failed for an unrelated reason: it spent its entire
32,000-token output budget reasoning, stopped mid-sentence with `stop: "length"`, and took no
action in 23 minutes. Prompt delivery was verified intact (1602 chars sent and received), so this
was the model, not the harness.

**Variance swamps the framing effect.** Run 0005 used the same precise framing on a clean base and
produced a working fix in 519 s / 12 turns; run 0009 produced nothing in 1378 s. Same task, same
wording, opposite outcomes. That spread is wider than the difference between minimal and scaffolded
framing, which means **n=1 per cell cannot support a framing conclusion** — and the reasoning-budget
fix has since changed the system under test, so these numbers are not directly comparable to future
ones.

**Learning.**

1. Write scaffolded tasks — not because the worker cannot cope without them, but because they cost
   about a third of the wall clock for the same result. On a worker running at 25 tok/s that is the
   difference between a 3-minute and a 10-minute task.
2. State test requirements as explicitly as implementation requirements. Warning about a trap does
   not produce a test for the trap.
3. The dominant risk is not task wording, it is variance — and specifically the possibility of the
   worker disappearing into its own reasoning and returning nothing. `THINK_MAX` now bounds that.
4. `verify: passed` appeared on a 23-minute no-op. Third occurrence today of the same shape. The
   rule stands: score from the diff.

**0004, the minimal framing, came back clean.** Given only the symptom — no file named, no
approach, no edge cases, no conventions — it found the right line, applied the right fix (`-z`
plus `surrogateescape`, matching how the module already reads trees fifteen lines above), and
avoided the `exists()` trap. The reviewer confirmed that by execution rather than reading: a path
`git rm`-ed and then recreated on disk still correctly reports `history-only`, where a filesystem
check would have said `current`.

Its test survived mutation testing — reverting the script makes it fail with exactly
`'history-only' != 'current'`, so it pins the real defect. Scope was clean, no scratch files
survived, suite green at 155.

Prediction 2 held: `verify` passed and told us almost nothing. Prediction 3 did not happen — the
minimal framing produced no quiet failure. Prediction 1 is so far consistent: 26 turns and 617 s
is a lot of work for a 3-line fix, and much of it was rediscovering what the scaffolded variant is
simply told.

**Methodology error, recorded so it is not repeated.** The 0004 review was launched while run 0005
was still executing *in the same working tree*. The reviewer checked out branches, reverted files,
and ran tests concurrently with the worker editing that tree, then restored it — destroying the
worker's in-progress uncommitted changes. Run 0005 is therefore void, not a result.

Two agents sharing one filesystem is not parallelism, and being careful is not a fix. Reviews must
run in an isolated `git worktree`, or strictly after the executions they review. Until that
isolation exists, serialise.

**Learning.** _Pending the reruns._

---

## E2 — Does batched delegation with a circuit breaker work?

**Status:** designed, not yet run

**Question.** Søren's proposed shape, to minimise frontier-model usage: Claude plans N atomic
tasks up front, the worker executes all of them, Claude reviews once at the end — rather than
reviewing every step.

**The concern with reviewing only at the end** is not the review, it is *continuing past a broken
step*. If step 3 of 8 goes wrong, steps 4–8 build on a broken base and the final review becomes an
untangling exercise, which costs more than reviewing each step would have.

**The design under test.** `scripts/run_batch.py`: steps share one branch and commit individually,
each carries its own acceptance command, and the batch **halts on the first failure**. A step that
produces no changes counts as a failure too, since a later step would then build on an assumption
never met. The gate is the worker's own test run, so it costs nothing in frontier tokens.

**Method.** A genuinely two-step task in `scripts/codex_task_server.py`, where step 2 depends on
step 1 having landed:

1. `Bridge.submit` accepts the input names `""` and `".."` — both escape the
   `Path(name).name != name` guard on Python 3.14 — and fail as `PermissionError` instead of the
   contract's `ValueError`.
2. Every failed submit leaves an orphaned `.{task_id}.tmp` staging directory behind forever;
   nothing ever removes it, and `queued_tasks()` skips dot-prefixed directories so the garbage is
   invisible.

**What is measured.** Whether the batch completes, whether the breaker fires when it should, and
whether step 2's diff is coherent given step 1's. Also: does per-step context reset actually
prevent the drift that a single long session would accumulate?

**Predictions, recorded in advance.**
1. Step 1 is the harder of the two — `os.path.basename` looks like a correct fix and still accepts
   `".."`. Expect this to be where a careless implementation lands.
2. Step 2 has its own trap: a naive `finally: shutil.rmtree(staging)` breaks the happy path, where
   the staging directory has already been renamed away.
3. If both steps pass, the batch shape is viable and the next question is how many steps it
   survives before drift appears.

**Result.** _Pending._

**Learning.** _Pending._

---

## E3 — Can the worker maintain an accurate progress log?

**Status:** proposed

**Question.** For a Ralph-style loop, something has to carry state across context resets. Søren
asked whether the local model could maintain and deepen its own task description. The judgement
half of that — deciding what to do next — should stay with Claude, because spec drift compounds
with no restoring force. But the *factual* half — recording what was actually changed — is a much
easier task, and if it is reliable the loop needs far less frontier involvement.

**Method.** Ride along on runs that are happening anyway. Compare the worker's own summary of what
it did against the actual `diff.patch`. Score for: claims of changes that were not made, changes
made but not mentioned, and mischaracterised intent.

**Prior evidence, unfavourable.** In run 0001 the worker returned a confident, well-formatted
report — *"no secrets found, the workspace is clean"* — having done nothing of value. Its
self-report was plausible, professional, and useless. That was under a truncated prompt, so it is
not damning, but it is the failure mode to watch for.

**Decision rule.** If self-reports prove reliable, the progress log can be worker-maintained. If
not, Claude derives progress from the diff and ignores the model's summary entirely — which is
strictly safer and only slightly more expensive.

**Result.** _Pending._

---

## E4 — Test-first loop with deterministic gates

**Status:** designed, not yet built

**The idea.** Invert the order: the worker writes the *test* first, the pipeline proves the test
actually fails, and only then does the worker write the implementation. Every check between steps
is deterministic and owned by the harness, not by the model.

**Why, in one sentence.** E1 showed that a worker which already has working code writes tests that
pass rather than tests that discriminate — so make the test exist before the code does, and prove
it fails.

**The evidence this comes from.** In run 0008 the task *explicitly* warned about the
`(repository / path).exists()` trap and explained why it is wrong. The worker avoided it in the
implementation, then wrote a test that does not catch it: substituting the wrong fix leaves its
own tests passing (6 passed). Its removed-path test unlinks the file from disk as well as from the
index, so it cannot distinguish tree membership from filesystem existence. The warning shaped what
the worker *did*, not what it *defended against*. Writing the test after the code is what allows a
test to be written to pass.

**The loop.**

| Step | Actor | Gate |
| --- | --- | --- |
| 1 | Worker writes the test only | Pipeline runs it — **must FAIL**. A passing test here proves nothing; reject and retry. |
| 2 | Worker writes the implementation | Pipeline runs the new test — **must PASS**. |
| 3 | — | Pipeline runs the full suite — **must PASS**, catching regressions. |

Step 1's must-fail gate *is* the mutation test, moved from a manual review pass into the harness
and applied before any code exists. It is the single cheapest quality gate available here: it
costs one test run and catches decorative tests at the moment they are written, rather than hours
later in review.

**Why the worker should have no shell for this.** If the pipeline runs the tests, the worker does
not need `bash` (`--no-shell`, see `scripts/run_task.py`). Three benefits at once:

- **Safety.** No shell means no command can reach anything, inside the repository or outside it.
- **Focus.** The worker stops spending turns deciding whether it is finished, working out how to
  invoke pytest, and interpreting output. In run 0004 that consumed a large share of 26 turns, and
  none of it is judgement.
- **Determinism.** The pipeline reports pass/fail identically every time; the model's reading of
  test output does not.

**What is measured.**
1. How often step 1 produces a test that wrongly passes — i.e. how often the must-fail gate fires.
   This is the direct measure of whether test-first fixes the E1 finding.
2. Whether implementations improve when a discriminating test already exists.
3. Turn count against the shell-enabled baseline, which should drop sharply if the theory about
   wasted turns is right.
4. Whether removing the shell hurts anything not anticipated.

**Predictions, recorded in advance.**
1. The must-fail gate will fire regularly. On the E1 evidence, tests written without a failing-first
   requirement are often non-discriminating.
2. Turn counts will fall substantially without a shell, because a large fraction of observed tool
   calls are test-running and self-checking rather than editing.
3. The risk is the worker writing a test that fails for the *wrong reason* — a syntax error or a
   bad import also fails. The gate must distinguish "fails because the behaviour is absent" from
   "fails because the test is broken", probably by requiring a specific assertion failure rather
   than any non-zero exit.

**Result.** _Not yet run._

---

## Settled questions

- **Is the MoE genuinely sparse at runtime?** Yes, proven by a memory-bandwidth argument — a dense
  read would need 9.1× more bandwidth than the hardware can physically deliver. See
  [../docs/moe-verification.md](../docs/moe-verification.md). Not proven: that *different* experts
  are chosen per token.
- **Is `--load-mode none` better than `mmap+mlock` with CPU tensor overrides,** as llama.cpp's
  startup warning advises? No, measurably worse here on both axes. See
  [../docs/runtime.md](../docs/runtime.md).
- **Can the local model do agentic tool work at all?** Yes. It completed a real two-file change
  with a passing test suite unattended, and used structured edit tools when the change was
  non-trivial. See [results.md](results.md).
