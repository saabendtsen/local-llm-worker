# Local LLM worker instructions

A prototype under the homelab workspace. Read the workspace `AGENTS.md` first; the zero-cost
policy and change discipline apply here unchanged.

## Scope

This repository holds the runtime scripts, harness configuration, and evaluation record for the
local worker prototype. It does not hold the model weights or the llama.cpp binaries — those
live outside any repository:

- Model: `C:\models\`
- Backend: `C:\Tools\llama.cpp-cuda\`
- Harness provider config: `~/.pi/agent/models.json`

Never commit GGUF files, binaries, or benchmark logs. Run records under `evaluation/runs/` are
the exception — they are the evaluation's evidence and belong in Git.

## Working here

- Scripts target CMD (`.cmd`), matching the workstation's default shell.
- The runtime and the harness stay decoupled. The same `llama-server` endpoint must remain usable
  by unrelated tools, so do not add coding-agent-specific behaviour to the runtime scripts.
- Do not build a custom agent loop. Pi is the harness; `scripts/run_task.py` only launches it and
  collects evidence. A bespoke agent loop would answer a different question and cost more to
  maintain.
- The runner must never score its own output. It records metrics and the diff; judgement belongs
  to the reviewing agent. Adding pass/fail heuristics to the runner would hide precisely the
  quiet failures the evaluation exists to find.
- `CTX` in `scripts\start-worker.cmd` and the harness's configured context window must stay in
  sync. Changing one without the other produces silent truncation that looks like model failure.

## Recording results

Every delegated task gets a row in `evaluation/results.md`, including the failures. A prototype
that only records successes cannot answer the question it exists to answer. Distinguish harness
failures from model failures — see `evaluation/README.md`.
