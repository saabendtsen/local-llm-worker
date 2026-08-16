# Evaluation

The prototype is judged on one question:

> What percentage of execution work can reliably be delegated
> without creating more review and rework than it saves?

Not on whether the local model matches a frontier model. It will not, and that is not the point.

## The cycle

1. **Claude writes the task.** Copy [task-template.md](task-template.md) into `tasks/` and fill
   it in. The task is **bounded, not prescribed**: constraints and acceptance criteria, never a
   list of edits. If the plan already contains every change, the reasoning cost has been paid and
   the run measured nothing.
2. **The runner executes it.**

   ```cmd
   scripts\run-task.cmd evaluation\tasks\0001-example.md
   ```

   It refuses to start against a dirty tree, creates `worker/<id>`, runs Pi headless, then
   records `events.jsonl`, `diff.patch`, and `run.json` under `runs/<id>/` and returns to the
   original branch. Run directories are immutable — a repeated id is an error, not an overwrite.
3. **Claude scores it.** Read the diff — not just the exit code — and add a row to
   [results.md](results.md).

## Batches — one plan, N executions, one review

For work that decomposes into several atomic steps, `scripts/run_batch.py` runs them in sequence
on a single branch:

```cmd
scripts\run-batch.cmd --id refactor-01 evaluation\tasks\a.md evaluation\tasks\b.md
```

Claude plans all the steps up front and reviews once at the end; the worker executes each with a
fresh context. That is where the frontier-token saving comes from — one planning pass and one
review pass amortised over N executions.

**The batch halts on the first step that fails**, and treats "produced no changes" as a failure
too. Reviewing only at the end is fine; *continuing past a broken step* is not, because every
later step then builds on a broken base and the final review becomes an untangling exercise. The
gate is the worker's own acceptance command, so it costs nothing in frontier tokens.

Order steps to be as independent as you can, so a halt discards as little work as possible.
`--keep-going` overrides the breaker, but then expect to review a tangle.

## Read the diff, not the exit code

The worker edits files with `cat >>` and `sed -i` rather than structured edit tools
(see [../docs/harness-pi.md](../docs/harness-pi.md)). `sed` substitutes by pattern, so a pattern
that matches in more than one place changes all of them silently.

The expected failure mode is therefore **not** "refuses the task" but "changed the wrong line and
the tests still passed". A green verify command is necessary evidence, not sufficient. Scoring a
run from `verify.passed` alone would systematically miss exactly the failures that make
delegation unprofitable.

## What the runner records

`run.json` carries the mechanical metrics so scoring only has to supply judgement:

| Field | Meaning |
| --- | --- |
| `worker.elapsed_seconds` | Wall clock for the run |
| `worker.timed_out` | Whether it was killed at the timeout |
| `events.turns` | How many times the agent looped |
| `events.tool_calls` / `tools_used` | How much work it did, and with which tools |
| `diff.files_changed`, `lines_added`, `lines_removed` | Size of the change |
| `diff.untracked_files` | Reported honestly, unfiltered — read before assuming the worker created something odd |
| `verify.passed` | Exit code of the acceptance command |

## Outcome classes

Use these consistently; the distribution across them *is* the result.

- **Clean** — acceptance criteria met, diff would pass review unchanged.
- **Minor repair** — met, but needed adjusting afterwards. Still a net saving.
- **Major repair** — fixing it cost more than writing it would have. A loss.
- **Takeover** — output discarded.
- **Harness failure** — the model never got a fair attempt: tool-format loop, context exhaustion,
  runtime crash, timeout. Not a capability result; fix the harness and rerun under a new id.

Keeping *harness failure* separate matters. Counting configuration problems as model failures
would understate the model and send the prototype to the wrong conclusion.

## Reading the result

The prototype is promising if simple tasks are reliably **clean**, bounded medium tasks are at
least **minor repair**, and failures are *obvious* rather than subtly wrong. A worker that fails
loudly is usable; one that produces plausible-but-wrong diffs costs more review than it saves,
regardless of its success rate.
