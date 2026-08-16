# Local LLM worker

A prototype for delegating token-heavy execution work to a locally hosted model, so a frontier
agent spends its budget on planning and review instead of implementation loops.

Tracked by [homelab-workspace#74](https://github.com/saabendtsen/homelab-workspace/issues/74).

## The loop

```text
Claude                          Local worker (Pi + Qwen3.6 35B A3B)
  │
  ├── writes a bounded task ────────►  explores the repository
  │   (constraints + acceptance          implements on a throwaway branch
  │    criteria, not a list of edits)    runs tests, iterates on failures
  │                                                │
  ◄──── diff, test result, metrics ────────────────┘
  │
  └── reads the diff and scores the run
```

Claude never writes the implementation and the worker never decides what "done" means. The
`scripts/run_task.py` runner sits between them and gathers evidence; it deliberately makes no
judgement about quality, because a runner that scored its own output would defeat the point.

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
| `scripts/run_task.py` | Execute one delegated task and record the evidence |
| `docs/runtime.md` | Model, backend, flag rationale, tuning |
| `docs/harness-pi.md` | Pi configuration and observed worker behaviour |
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

Phase 1 complete. The runtime is up, Pi drives it headless, and the worker has completed a real
multi-file task — edits plus a passing test suite — unattended in under a minute.

Phase 2 is the evaluation: run 10–20 bounded tasks from real repositories and find where the
reliable task horizon ends.
