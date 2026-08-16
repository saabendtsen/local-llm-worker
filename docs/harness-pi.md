# Harness: Pi

[Pi](https://github.com/earendil-works/pi) (`@earendil-works/pi-coding-agent`) is a terminal
coding agent built on a small tool core — read, write, edit, bash — with a `--mode json` event
stream and a one-shot `-p` mode. That combination is what makes it usable as a *measured* worker
rather than something a human watches, so it is the harness for this prototype.

Issue #74 originally suggested proving the concept in Cline first. That step was skipped
deliberately: Cline is UI-driven and can never be the automated backend, so time spent
configuring it would not carry forward. Pi can be both the experiment and the eventual worker.

Installed: `@earendil-works/pi-coding-agent` v0.84.2, globally via npm.

## Configuration

The local endpoint is registered as a provider in `~/.pi/agent/models.json`
(`C:\Users\<you>\.pi\agent\models.json`):

```json
{
  "providers": {
    "local-worker": {
      "baseUrl": "http://127.0.0.1:8000/v1",
      "api": "openai-completions",
      "apiKey": "local",
      "compat": { "supportsDeveloperRole": false },
      "models": [
        {
          "id": "local-worker",
          "name": "Qwen3.6 35B A3B (local llama.cpp)",
          "contextWindow": 120000,
          "maxTokens": 32000
        }
      ]
    }
  }
}
```

`contextWindow` must match `CTX` in `scripts\start-worker.cmd`. If Pi believes the window is
larger than the server's, the server truncates silently and the worker behaves erratically for
reasons that look like model failure.

`apiKey` is required by the client but ignored by llama-server. `supportsDeveloperRole: false`
keeps Pi from sending a `developer` role the server does not implement.

Check it directly:

```cmd
pi --model local-worker/local-worker --no-session -p "Reply with exactly: pi worker ready"
```

## Headless invocation

The harness runs Pi like this (see `scripts/run_task.py`):

```text
pi -a --no-session --exclude-tools ask_question --mode json --model local-worker/local-worker -p <task>
```

| Flag | Why |
| --- | --- |
| `-a` | Trust project files. The run happens on a throwaway branch, which is the real safety net. |
| `--no-session` | Each task is independent; no state leaks between runs. |
| `--exclude-tools ask_question` | **Essential.** With no human attached, a question would hang until the timeout and burn the run. |
| `--mode json` | One JSON object per line: `turn_end` counts iterations, `tool_execution_end` counts tool calls. This is where the evaluation metrics come from. |

## Never launch Pi through the Windows shim

`shutil.which("pi")` resolves to `pi.CMD`. Launching a `.CMD` hands the argument list to
`cmd.exe`, **which truncates any argument at its first newline** — so a multi-line task prompt
arrives as its first line only.

This is not hypothetical. It cost two runs that were initially recorded as model failures: the
worker received only a task's title line, did something plausible and irrelevant with it, and the
result read as a comprehension failure. See
[../evaluation/results.md](../evaluation/results.md).

`scripts/run_task.py` therefore resolves the package's JS entry point and runs it under `node`
directly:

```text
node <npm-global>/@earendil-works/pi-coding-agent/dist/cli.js -a --no-session ...
```

It also verifies after every run that the prompt in the event stream matches what was sent, and
labels any mismatch a harness failure rather than a capability result. **A truncated prompt is
indistinguishable from a stupid model if you only look at the diff.** Any harness that measures a
worker has to verify its own input first.

## What the model does with tools

Tool choice tracks the difficulty of the change:

- **Trivial appends go through the shell.** On a throwaway two-file repository the worker used
  `cat >> file << 'EOF'` and `sed -i 's/old/new/'`, and touched no structured edit tool.
- **Real edits use `edit`.** On the first genuine task — inserting a new entry into the middle of
  an existing dictionary, plus two tests in an existing class — it used `edit` four times
  alongside `read` and `bash`, and anchored the insertion correctly.

The shell habit is still worth watching, because `cat >>` can only append and `sed` substitutes by
pattern, so a pattern matching twice changes both occurrences silently. But the initial worry that
the worker *never* reaches for structured edits was drawn from a single trivial run and did not
survive contact with real work.

The standing rule is unchanged and does not depend on which tools it picked: **read the diff, do
not trust the exit code**. A run that changes nothing still passes a suite that was already green.

## Reasoning behaviour

Qwen 3.6 thinks before answering, and llama-server returns that trace as
`message.reasoning_content` rather than in `message.content`. Two consequences:

- **Budget for it.** Asked to reply with the two words `worker ready`, the model spent 166 tokens:
  150 of reasoning, 2 of answer. At ~25 tokens/sec that is six seconds before any visible output,
  paid on every agent step.
- **A low token limit silently returns nothing.** A 32-token cap produced an empty `content` with
  a full token count — reasoning consumed the whole budget before the answer began. If replies
  come back blank, suspect the limit before suspecting the model.

- **Reasoning can run away entirely.** One run spent its *whole* 32,000-token output budget
  thinking about a three-line fix, stopped mid-sentence with `stop: "length"`, and took no action
  in 23 minutes. Two turns, two file reads, nothing else. And because it changed nothing, the
  already-green suite reported `verify: passed` — a 23-minute no-op recorded as a success.

`THINK_MAX` in `scripts\start-worker.cmd` maps to llama-server's `--reasoning-budget` and defaults
to 4096. It is a safety valve, not a preference: it converts "silently thinks forever and returns
nothing" into "thinks up to the budget, then acts". `EFFORT` maps to `--reasoning-effort` and is
the softer dial.

Treat *lowering* effort as an experiment to record, not a default — thinking is likely part of why
the model can implement at all, and trading it away to make a bad diff arrive faster is not a win.
The budget is different: it bounds a catastrophic failure rather than trading quality for speed.

## Other rough edges

- **Context exhaustion.** 120k is generous, but an agent that `cat`s whole files repeatedly fills
  it faster than one using targeted reads. Watch for truncation and record where it starts.
- **Slow first response.** Prompt processing dominates on a large context — roughly 19 seconds for
  a 13k-token prompt. Time-to-first-token is not a hang.
- **`__pycache__` in untracked files.** Running tests leaves artefacts. In a repository with a
  proper `.gitignore` these do not appear; in the scratch repo used for harness testing they did.
  The runner reports untracked files honestly rather than filtering them, so read the list before
  concluding the worker created something unexpected.
