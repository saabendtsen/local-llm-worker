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

## What the model actually does with tools

The first measured run is the most useful thing learned so far. Asked to add a function and a
test, the worker used **8 bash calls and 2 read calls — and zero edit or write calls**. It made
its changes like this:

```sh
cat >> greet.py << 'EOF'

def shout(name):
    return greet(name).upper()
EOF

sed -i 's/from greet import greet/from greet import greet, shout/' test_greet.py
```

The result was correct, idiomatic, and passed tests. But *how* it got there predicts where this
worker will break:

- **`cat >>` only appends.** It works for adding a function to the end of a file and cannot
  express an edit in the middle of one. Tasks needing insertion into existing code have to go
  through `sed` or a rewrite instead.
- **`sed -i` is unanchored.** It substitutes by pattern, so a pattern matching in more than one
  place changes all of them silently. Pi's `edit` tool exists precisely to make edits verifiable;
  the model is declining to use it.
- **No verification that an edit landed where intended.** The model re-`cat`s the file afterwards,
  which catches gross failures but not a substitution that also hit an unintended line.

So the expected failure mode is not "refuses the task" but "edits the wrong place and the tests
still pass". That is the quiet-failure case the evaluation is most concerned with, and it means
**diffs must be read, not just test results trusted**. Do not score a run from its exit code.

Whether this is the model's preference or a weakness in emitting Pi's structured edit format is
worth a deliberate test: run a task that requires modifying the middle of a large file and see
whether it reaches for `edit` or contorts `sed`.

## Reasoning behaviour

Qwen 3.6 thinks before answering, and llama-server returns that trace as
`message.reasoning_content` rather than in `message.content`. Two consequences:

- **Budget for it.** Asked to reply with the two words `worker ready`, the model spent 166 tokens:
  150 of reasoning, 2 of answer. At ~25 tokens/sec that is six seconds before any visible output,
  paid on every agent step.
- **A low token limit silently returns nothing.** A 32-token cap produced an empty `content` with
  a full token count — reasoning consumed the whole budget before the answer began. If replies
  come back blank, suspect the limit before suspecting the model.

If reasoning latency proves to dominate, `EFFORT` in `scripts\start-worker.cmd` maps to
llama-server's `--reasoning-effort`. Treat lowering it as an experiment to record, not a default:
thinking is likely part of why the model can implement at all, and trading it away to make a bad
diff arrive faster is not a win.

## Other rough edges

- **Context exhaustion.** 120k is generous, but an agent that `cat`s whole files repeatedly fills
  it faster than one using targeted reads. Watch for truncation and record where it starts.
- **Slow first response.** Prompt processing dominates on a large context — roughly 19 seconds for
  a 13k-token prompt. Time-to-first-token is not a hang.
- **`__pycache__` in untracked files.** Running tests leaves artefacts. In a repository with a
  proper `.gitignore` these do not appear; in the scratch repo used for harness testing they did.
  The runner reports untracked files honestly rather than filtering them, so read the list before
  concluding the worker created something unexpected.
