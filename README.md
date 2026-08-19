# Local LLM worker

A prototype for delegating token-heavy execution work to a locally hosted model, so a frontier
agent spends its budget on planning and review instead of implementation loops.

Tracked by [homelab-workspace#74](https://github.com/saabendtsen/homelab-workspace/issues/74).

## The loop

```text
frontier (Claude today; pluggable)        local worker (Pi + Qwen3.6 35B A3B)        mechanical
  │
  ├── writes a bounded task ─────────────►  implements on a throwaway branch
  │                                         runs ruff + tests, iterates             run_task.py
  │                                                    │
  │                                         four fresh-context reviewers, one      run_review.py ×4
  │                                         axis each, in isolated worktrees
  │                                                    │
  │                                                    ▼
  │                                         findings ── union, dedupe, order ──►   aggregate_findings.py
  │                                                    │
  ◄──── triage: verify each finding against source, ──┘                            run_triage.py
  │     defect vs test gap, merge, emit chained fix tasks
  │
  └──► one bounded fix task per finding ──►  fix on a branch off the last fix       run_task.py ×N
```

Judgement stays with the frontier model — writing the specification and triaging findings. The
worker does the token-heavy parts: implementing, reviewing a diff it did not write, fixing one
finding at a time. The runners between them gather evidence and make no judgement about quality.
The pipeline owns every prompt, including the triage prompt, and calls the frontier model by CLI
(`--frontier claude|codex|cmd:`), so the frontier model is a flag rather than a dependency.

## What this is

Three pieces, deliberately decoupled:

1. **The runtime** — `llama-server` serving an OpenAI-compatible endpoint on
   `http://127.0.0.1:8000/v1`. Any tool can use it. See [docs/runtime.md](docs/runtime.md).
2. **The harness** — [Pi](https://github.com/earendil-works/pi), run headless with a JSON event
   stream. See [docs/harness-pi.md](docs/harness-pi.md).
3. **The evaluation** — task specs, run records, and the scoring log. See
   [evaluation/README.md](evaluation/README.md).

The question the prototype answers is narrow:

> What percentage of execution work can reliably be delegated
> without creating more review and rework than it saves?

## Quick start

Start the runtime and leave it running in its own window:

```cmd
scripts\start-worker.cmd
scripts\check-worker.cmd
```

Then run a task:

```cmd
scripts\run-task.cmd evaluation\tasks\0001-example.md
```

## Layout

| Path | Purpose |
| --- | --- |
| `scripts/start-worker.cmd` | Launch the runtime |
| `scripts/check-worker.cmd` | Health, model list, and a real completion |
| `scripts/bench-worker.cmd` | Throughput baseline |
| `scripts/run_task.py` | Execute one delegated task on a branch and record the evidence |
| `scripts/run_batch.py` | Several atomic tasks on one branch, with a circuit breaker |
| `scripts/run_review.py` | Fresh-context review of a diff, in a dedicated worktree; `--prompt` picks the axis |
| `scripts/aggregate_findings.py` | Union the reviewers' findings, dedupe, order, enforce the confidence floor |
| `scripts/run_triage.py` | Frontier triage by CLI, strict output contract, renders chained fix tasks |
| `prompts/` | Every prompt the pipeline sends: four review axes, the broad review, triage |
| `scripts/status_page.py` | What the worker is doing right now: `status` prints JSON, `serve` is a loopback page on :8765 |
| `docs/runtime.md` | Model, backend, flag rationale, tuning |
| `docs/harness-pi.md` | Pi configuration and observed worker behaviour |
| `docs/using-small-models.md` | Standing reference: how to get useful work out of a small local model |
| `evaluation/` | Task specs, run records, results |

## Hardware

| Resource | Available |
| --- | --- |
| GPU | NVIDIA RTX 3070, 8 GB VRAM |
| CPU | AMD Ryzen 5 3600, 6 cores / 12 threads |
| RAM | 32 GB |

The model is an MoE with ~3B active parameters, which is what makes a 35B model viable here:
attention and shared weights sit on the GPU, expert weights live in system RAM, and only a small
fraction of the parameters are touched per token.

Measured: **~690 tok/s prompt processing, ~25 tok/s generation**, full 120k context. See
[evaluation/results.md](evaluation/results.md).

## Status

Phases 1–2 done; the pipeline has run end to end once (E8). Eight experiments recorded in
[`evaluation/experiments.md`](evaluation/experiments.md), each with its hypothesis written before
the result; [`docs/pipeline-design.md`](docs/pipeline-design.md) tracks the design and what each
experiment changed. Short version: the worker builds real features from a well-formed task;
fresh-context focused reviewers find real defects with almost no false positives; triage has to be
a frontier step because one finding in eleven was inverted; and bounded one-finding fix cycles hold.

E9 then ran the chain unattended on a greenfield feature (the status page), triage automated.
Next: findings-only triage, Codex as a second frontier, a repeat arm on f03.
