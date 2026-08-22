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

## Never review and execute in the same working tree

A review agent inspects a branch: it checks out, reverts files to mutation-test, runs the suite,
and restores. A worker run edits that same tree. Doing both at once destroys the run — the
reviewer's restore wipes the worker's uncommitted changes mid-flight, and the run's result becomes
meaningless without anything obviously looking wrong.

This has already happened once and voided a run. Being careful is not the fix. Either:

- spawn review agents with worktree isolation so they get their own checkout, or
- run reviews strictly after all executions have finished.

The same applies to anything else that mutates the repository while a run is live.

## The repository comes from the spec, not from a default

`run_task.py`, `run_review.py` and `run_triage.py` all resolve the repository through
`resolve_repo()`: an explicit `--repo` if given, otherwise the spec frontmatter's `repo` field.

The review and triage runners used to default to `C:\Dev\homelab` instead. Omitting `--repo` then
ran `git diff <base>...<branch>` in the workspace repository, which holds neither ref, and the run
died with:

    fatal: ambiguous argument 'main...worker/f04-status-page-detail': unknown revision

That reads as a bad branch name, so it sends you looking at the branch instead of the repository.
It cost a chain launch to diagnose. Keep the spec as the single source of the repository.

Review worktrees land in `<repo>.parent/homelab-worktrees/review-<id>`, so for this experiment
that is `C:\Dev\homelab\experiments\homelab-worktrees\` -- not the workspace's
`C:\Dev\homelab-worktrees\`. A worktree left registered by a crashed run blocks a rerun on the
same id; clear it with `git worktree remove --force <path>` and `git worktree prune`.

## Recording results

Every delegated task gets a row in `evaluation/results.md`, including the failures. A prototype
that only records successes cannot answer the question it exists to answer. Distinguish harness
failures from model failures — see `evaluation/README.md`.
