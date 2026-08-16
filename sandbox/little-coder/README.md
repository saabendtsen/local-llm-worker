# little-coder sandbox

A place to try [little-coder](https://github.com/itayinbarr/little-coder) without touching the
working setup. Nothing here is wired into `scripts/run_task.py` or the evaluation; it is a
tinkering bench.

## Why a sandbox rather than a swap

little-coder is not a competing harness — it *is* Pi, plus ~34 extensions. That makes it appealing
and also makes it dangerous to install carelessly:

- It depends on `@earendil-works/pi-coding-agent` at **`^0.83.0`**, which under npm's 0.x semver
  means `>=0.83.0 <0.84.0`. The working setup runs **0.84.2**. Its own history contains a commit
  titled *"pi 0.83 tool-name fix"*, so tool names moved between those versions — and
  `scripts/run_task.py` counts tool calls by name from the JSON event stream. A careless global
  install could silently change what the metrics mean.
- Its launcher forces `--no-context-files` and its own ~7k-token system prompt. At ~25 tok/s that
  is prefill paid on every run, and it replaces the task framing the evaluation has been measuring.

## What isolates this from the working setup

| Concern | How it is isolated |
| --- | --- |
| Pi version | Installed **locally** into this directory (`npm install`, no `-g`). Its Pi 0.83 lives in `./node_modules`; the global `pi` stays 0.84.2. |
| Model config | Its own `models.json`, passed explicitly via `LITTLE_CODER_MODELS_FILE`. The working setup's `~/.pi/agent/models.json` is untouched. |
| Repository under test | Runs against a dedicated Git worktree, never the main checkout. See below. |
| Run records | Anything written here stays here. Nothing lands in `evaluation/runs/`. |
| Node modules | Gitignored — this directory holds configuration and notes, not a vendored dependency tree. |

**The one thing genuinely shared is the model server.** Both point at
`http://127.0.0.1:8000/v1`, which is deliberate — loading a second 20 GB model is not possible on
this hardware. But `llama-server` runs with `-np 1`, a single slot, so **do not run a little-coder
trial while an evaluation run is in flight.** They will queue behind each other and both sets of
timings become meaningless.

## Setup

```cmd
cd sandbox\little-coder
npm install
```

Then confirm which Pi it actually resolved — this is the number that matters:

```cmd
node -e "console.log(require('./node_modules/@earendil-works/pi-coding-agent/package.json').version)"
```

## Running against an isolated worktree

Never point a trial at `C:\Dev\homelab` directly. Give it its own worktree:

```cmd
git -C C:\Dev\homelab worktree add C:\Dev\homelab-worktrees\little-coder-trial -b trial/little-coder experiment/74-local-llm-worker
```

Then:

```cmd
run-trial.cmd C:\Dev\homelab-worktrees\little-coder-trial "Your task here"
```

When finished:

```cmd
git -C C:\Dev\homelab worktree remove C:\Dev\homelab-worktrees\little-coder-trial --force
git -C C:\Dev\homelab branch -D trial/little-coder
```

## First measurements

Smoke test, 2026-08-16 — `-p "Reply with exactly: little-coder ready"` against the trial worktree.
It answered correctly, so the plumbing works end to end.

| Observation | Value |
| --- | --- |
| Resolved Pi version | **0.83.0** (global install still 0.84.2 — isolation confirmed) |
| Input tokens for a trivial prompt | **5,373** |
| Output tokens | 22 |
| Event stream shape | `message_start` / `message_update` / `message_end` / `turn_end` / `agent_end` / `agent_settled` — same as 0.84.2 |

**The 5,373 input tokens are the finding.** Bare Pi sends 16 tokens for the same request. So the
injected system prompt and skills cost roughly **5.3k tokens of prefill on every run**, before the
task is even read. At ~690 tok/s prompt processing that is about 8 seconds per run, plus the
context it permanently occupies.

Whether that is worth paying is the question this sandbox exists to answer: 8 seconds is cheap if
the extensions prevent one 23-minute reasoning runaway, and expensive if they change nothing. Do
not decide it from the README — measure both ways on the same task.

The event vocabulary matching 0.84.2 is encouraging for `scripts/run_task.py`, but it is not proof:
tool *names* are what the metrics count, and those are what moved between versions. A trial that
uses tools will settle it.

## What is worth testing

The extensions are the reason to look at this at all. In rough order of value:

- **`permission-gate`** — whitelists command prefixes, judges every segment of `&&`/`||`/`;`/`|`
  chains, refuses redirect and `tee`/`dd` targets, and keeps `rm` and `sudo` off the whitelist.
  Critically it **never prompts**; it returns a structured block, so it cannot hang a headless run.
  Strictly better than the working setup's `--no-shell`, which is all-or-nothing: this keeps bash
  for running tests while still refusing `rm`.
- **`turn-cap`** — bounds runaway loops.
- **`context-watchdog` / `evidence-compact`** — compaction that preserves evidence.
- **`phase-model`** — a different model for planning versus implementing.

## The likely end state

Pi loads extensions with a plain `--extension` flag. So the probable outcome is **not** adopting
little-coder wholesale, but cherry-picking one or two Apache-2.0 extensions onto the existing Pi
0.84.2 — no downgrade, no forced system prompt, no risk to the metrics parser. This sandbox exists
to find out whether they work against this model before doing that.
