# Harness: Cline

Cline is the first harness because it is the fastest path to an answer, not because it is the
intended long-term worker backend. It tolerates weaker tool-calling than Roo Code, which keeps
the first experiment focused on one question — *can the local model do the work?* — rather than
conflating it with *can the local model emit native tool calls?*

Installed: `saoudrizwan.claude-dev` v4.1.10 in VS Code.

## Configure against the local endpoint

Start the runtime first (`scripts\start-worker.cmd`), then in VS Code:

1. Open the Cline sidebar and go to its settings.
2. **API Provider**: `OpenAI Compatible`.
3. **Base URL**: `http://127.0.0.1:8000/v1`
4. **API Key**: any non-empty string — llama-server does not check it, but the field is required.
5. **Model ID**: `local-worker` (this must match `ALIAS` in `start-worker.cmd`).
6. **Context window**: `32768` — must match `CTX` in `start-worker.cmd`. If Cline believes the
   window is larger than the server's, requests are silently truncated by the server and the
   agent behaves erratically for reasons that look like model failure. Keep these two in sync.

## Settings that matter for a local model

- **Auto-approve**: leave read and list operations auto-approved, keep file writes and terminal
  commands manual for the first tasks. The point of the early runs is to *watch* where the model
  goes wrong; auto-approving everything hides exactly the data the evaluation needs.
- **Plan/Act**: use Act mode. Planning is Codex's job in this architecture — if the local model
  is doing the planning, the delegation has not saved anything.

## This is a reasoning model

Qwen 3.6 thinks before answering, and llama-server returns that trace separately as
`message.reasoning_content` rather than in `message.content`. Two consequences:

- **Budget for it.** Asked to reply with the two words `worker ready`, the model spent 166
  tokens: 150 of reasoning, 2 of answer. At ~25 tokens/sec that is six seconds of latency before
  any visible output. An agent step that reads a file and makes one edit pays this tax every
  time, so wall-clock per task is driven as much by reasoning volume as by the work itself.
- **A low `max_tokens` silently returns nothing.** The first smoke test came back with empty
  `content` and a full token count — reasoning consumed the entire 32-token budget before the
  answer began. If the harness reports blank replies, suspect the token limit before suspecting
  the model.

If reasoning latency proves to dominate, `EFFORT` in `scripts\start-worker.cmd` maps to
llama-server's `--reasoning-effort` (`minimal`, `low`, `medium`, `high`). Treat lowering it as an
experiment to record, not a default — thinking is likely part of why the model can implement at
all, and trading it away to make a bad diff arrive faster is not a win.

## Known rough edges to expect

These are the failure modes worth distinguishing from genuine capability limits, because they
are harness or configuration problems rather than model problems:

- **Malformed tool blocks.** Cline parses tool use out of the text stream. A local model that
  drifts on the format produces a retry loop. Log this separately from "wrong implementation".
- **Context exhaustion.** 32k fills quickly once several files are read. Watch for the point
  where Cline starts truncating, and record it — the usable context is a real constraint on task
  size and is one of the prototype's findings.
- **Slow first response.** Prompt processing over a large context is the expensive part on this
  hardware. Time-to-first-token is not a hang.

## Escalation

When a task fails, stop and record it rather than nudging the model repeatedly. The metric that
matters is how much delegation saves; a task rescued by five rounds of human correction has
already cost more than it saved. Record it as a failure and move on.
