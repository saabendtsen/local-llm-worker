# Local LLM worker instructions

A prototype under the homelab workspace. Read the workspace `AGENTS.md` first; the zero-cost
policy and change discipline apply here unchanged.

## Scope

This repository holds the runtime scripts, harness configuration, and evaluation record for the
local worker prototype. It does not hold the model weights or the llama.cpp binaries — those
live outside any repository:

- Model: `C:\models\`
- Backend: `C:\Tools\llama.cpp-cuda\`

Never commit GGUF files, binaries, or benchmark logs.

## Working here

- Scripts target CMD (`.cmd`), matching the workstation's default shell.
- The runtime and the harness stay decoupled. The same `llama-server` endpoint must remain usable
  by unrelated tools, so do not add coding-agent-specific behaviour to the runtime scripts.
- Do not build custom orchestration at this stage. The prototype's value depends on finding out
  whether an off-the-shelf harness is sufficient; a bespoke agent loop would answer a different
  question and cost more to maintain.
- `CTX` in `scripts\start-worker.cmd` and the harness's configured context window must stay in
  sync. Changing one without the other produces silent truncation that looks like model failure.

## Recording results

Every delegated task gets a row in `evaluation/results.md`, including the failures. A prototype
that only records successes cannot answer the question it exists to answer. Distinguish harness
failures from model failures — see `evaluation/README.md`.
