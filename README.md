# Local LLM worker

A prototype for delegating token-heavy execution work from Codex to a locally hosted model,
so Codex spends its budget on planning and review instead of implementation loops.

Tracked by [homelab-workspace#74](https://github.com/saabendtsen/homelab-workspace/issues/74).

## What this is

Two independent pieces, deliberately not coupled:

1. **The runtime** — `llama-server` serving an OpenAI-compatible endpoint on
   `http://127.0.0.1:8000/v1`. Any tool can use it; nothing about it is specific to coding agents.
   See [docs/runtime.md](docs/runtime.md).
2. **The harness** — an existing coding agent (Cline first) pointed at that endpoint and run
   against a real repository. See [docs/harness-cline.md](docs/harness-cline.md).

No custom orchestration is built at this stage. The question the prototype answers is narrow:

> What percentage of Codex execution work can reliably be delegated
> without creating more review and rework than it saves?

## Quick start

```cmd
scripts\start-worker.cmd
```

Then confirm the endpoint is up:

```cmd
scripts\check-worker.cmd
```

## Layout

| Path | Purpose |
| --- | --- |
| `scripts/` | Start, check, and benchmark the local runtime |
| `docs/runtime.md` | Model choice, hardware budget, launch flags, tuning |
| `docs/harness-cline.md` | Cline configuration against the local endpoint |
| `evaluation/` | Delegated-task records and the running result log |

## Hardware budget

This prototype targets the development PC as-is:

| Resource | Available |
| --- | --- |
| GPU | NVIDIA RTX 3070, 8 GB VRAM (~7.1 GB usable) |
| CPU | AMD Ryzen 5 3600, 6 cores / 12 threads |
| RAM | 32 GB |

The model is an MoE with ~3B active parameters, which is what makes a 35B model viable here:
attention and shared weights sit on the GPU, expert weights stream from system RAM, and only a
small fraction of the parameters are touched per token. Expect single-digit-to-low-teens
tokens/sec, not interactive-chat speed. That is acceptable for a background worker and is itself
one of the things the evaluation measures.

## Status

Phase 1 — runtime and harness bring-up. Nothing is automated yet; Codex does not call the worker.
