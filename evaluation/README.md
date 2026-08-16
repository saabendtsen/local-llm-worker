# Evaluation

The prototype is judged on one question:

> What percentage of Codex execution work can reliably be delegated
> without creating more review and rework than it saves?

Not on whether the local model matches Codex. It will not, and that is not the point.

## Method

Run 10–20 real tasks from this workspace's repositories through the local worker. For each one:

1. Write a task file from [task-template.md](task-template.md). Codex writes it; the task is
   **bounded, not prescribed** — constraints and acceptance criteria, never a list of edits. If
   Codex specifies every change, the reasoning cost has already been paid and the delegation
   measured nothing.
2. Run it in the harness against a clean working tree on its own branch.
3. Record the outcome in [results.md](results.md).

## What to record

| Field | Notes |
| --- | --- |
| Task category | boilerplate / tests / docs / small feature / refactor / bugfix / medium feature |
| Complexity | rough: files touched and whether the design was already known |
| Worker iterations | how many times the agent looped before stopping |
| Tests passed | did the acceptance criteria verify without help |
| Codex repair | did Codex have to fix the result, and how much |
| Codex takeover | did Codex have to redo it entirely |
| Inference time | wall clock for the worker run |
| Diff quality | subjective, one line — would this pass review as-is |

## Outcome classes

Use these consistently; the whole point is the distribution across them.

- **Clean** — acceptance criteria met, diff would pass review unchanged.
- **Minor repair** — met, but Codex adjusted the result. Still a net saving.
- **Major repair** — Codex spent more effort fixing than writing it would have cost. A loss.
- **Takeover** — worker output discarded.
- **Harness failure** — the model never got a fair attempt (tool-format loop, context exhaustion,
  runtime crash). Not a capability result; fix the harness and rerun.

Keeping *harness failure* separate matters. Counting configuration problems as model failures
would understate the model and send the prototype to the wrong conclusion.

## Reading the result

The prototype is promising if simple tasks are reliably **clean**, bounded medium tasks are at
least **minor repair**, and failures are *obvious* rather than subtly wrong. A worker that fails
loudly is usable; one that produces plausible-but-wrong diffs costs more review than it saves,
regardless of its success rate.
