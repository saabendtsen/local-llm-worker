# Getting the most out of a small local model

A working reference for delegating real work to a locally hosted model. It combines published
findings with what has been measured on this machine, and keeps the two clearly separated —
first-party results are marked **[measured here]**, everything else is cited at the bottom.

Scope: models in the range this hardware can run (roughly 8B–35B, quantised), driven by an agent
harness against a real repository. Not chat, not RAG.

## The one idea that matters

**The model supplies judgement. Everything else is the harness's job.**

This is the most consistent finding in the literature and it matches what this project has seen.
The same weights behave completely differently depending on the scaffolding around them: one
ablation study took an 8B model from ~53% to ~82–86% task completion on agentic workflows purely
through engineering around the model, against a ~91% frontier baseline.[^guardrails]

The corollary is where most effort should go. Time spent on validation, task framing, and
verification buys more than time spent hunting for a better checkpoint.

## 1. Task design — the highest-leverage lever

Bound the task, but do not prescribe the edits. If the task already contains every change, the
reasoning cost has been paid elsewhere and nothing was delegated.

What a good task carries:

- **The deliverable, stated first.** Name the files to change in the opening sentence.
- **The invariant that must not break.** State it as a rule, not a hope.
- **The failure case to avoid.** "A longer filename that merely contains this word must not be
  flagged" is worth more than three paragraphs of description.
- **An acceptance command.** One thing to run whose exit code is meaningful.
- **A short "notes" section** with anything already known — the pattern to follow, the convention,
  the gotcha. This is cheap to supply and is the difference between a bounded task and an
  open-ended one.

Ambiguity between *"make the tool do X"* and *"do X"* is a real hazard: a frontier model resolves
it from context, a smaller one may not. Write the imperative.

> **[measured here]** Do not over-fit to this. A run that looked like a comprehension failure —
> the worker audited the repository instead of editing code — turned out to be a truncated prompt
> delivering only the task's title line. Verify the input before blaming the model. See
> [../evaluation/results.md](../evaluation/results.md).

## 2. Context discipline

Every model tested by Chroma across 18 models degraded as input length grew, *even on trivial
tasks*, and effective context routinely falls far below the advertised
window.[^contextrot][^mecw] Two consequences worth designing around:

- **Distractors cost more than length.** Content that is topically related but irrelevant
  measurably degrades answers; a single distractor is enough to matter.[^contextrot] Pointing the
  worker at three relevant files beats letting it explore thirty.
- **Position matters.** Put the critical instruction at the very start. Accuracy is best for
  material near the beginning and degrades for content buried mid-context.[^contextrot]

Practical rules:

- A large context window is a budget, not a target. 120k available does not mean 120k should be
  used.
- One task per session. Start clean rather than continuing a long thread.
- If quality falls off a cliff at a consistent point, that is context management — compact
  earlier or restart more often.[^harness]

> **[measured here]** Prompt processing runs at ~690 tok/s, so a 13k-token context costs ~19
> seconds before the first token. Prefix caching makes that a per-task rather than per-step cost,
> *provided the harness keeps the prefix stable* — a second request sharing the same prefix
> reprocessed only the 2k-token tail.

## 3. Tool calling

The documented failure modes for small models are specific and worth recognising by
name:[^failuremodes][^invocation]

| Failure | What it looks like |
| --- | --- |
| Malformed call | Broken JSON or invented parameters |
| **Failure to initiate** | The model knows a tool is needed and answers from its weights anyway |
| Text-vs-tool ambiguity | It writes prose describing the action instead of taking it |
| Unbounded loop | Repeated near-identical calls with no progress |
| Context saturation | Quality collapses as the transcript fills |

Mitigations, roughly in order of measured value:[^guardrails]

1. **Keep the model in tool-calling mode.** Allowing a free choice between prose and tools is
   reported to collapse completion rates dramatically. A mandatory terminal tool (a `respond`
   tool) was the single highest-leverage change in that study.
2. **Rescue-parse before retrying.** Recover intent from nearly-valid output rather than spending
   a retry.
3. **Targeted nudges, not blind retries.** Tell it exactly what was wrong: *"That was not a valid
   tool call. You must call one of: …"* (+6–9 pp).
4. **Enforce prerequisites.** Block a step that skipped a required earlier one (+5–8 pp).

Practically, exclude any "ask the human" tool when running headless. With nobody attached, a
question is not a graceful degradation — it burns the whole run against the timeout.

> **[measured here]** Tool calling has not been the weak point here. Across runs, calls were
> well-formed and exploration was competent. Tool *choice* tracked task difficulty: shell text
> manipulation (`cat >>`, `sed -i`) for a trivial append, and real `edit` calls for inserting into
> the middle of an existing file.

## 4. Runtime choices

- **Weight quantisation is cheap at Q4_K_M.** Reported code-generation quality holds up well at
  4-bit K-quants; the step to Q5 buys less than the memory it costs on a constrained
  machine.[^quant]
- **KV-cache quantisation is cheaper than people assume, to a point.** Roughly ~98% of FP16
  quality at q8_0 and ~92% at q4 for code generation, with q8_0 a defensible production
  default.[^kv][^kvcliff] Prefer q8_0; treat q4 KV as a last resort, because the degradation is
  quiet.
- **Prefer more context headroom over marginal speed.** On an 8 GB card, generation rate is rarely
  the binding constraint; VRAM is.

> **[measured here]** Q4_K_M on a 35B MoE gives ~690 tok/s prompt processing and ~25 tok/s
> generation with q8_0 KV cache and 120k context. Giving up ~7% of generation speed bought 1.8 GB
> of VRAM headroom — a good trade on a machine that is also a desktop. See
> [runtime.md](runtime.md).

## 5. Reasoning models

If the model thinks before answering, that trace is spent from the same token budget:

- **Set generous limits.** A small `max_tokens` can be consumed entirely by reasoning, returning
  empty content with a full token count. That reads as a broken server.
- **Do not reflexively disable thinking.** It is likely part of why the model can implement at
  all. Trading it away to make a worse diff arrive faster is not a win — treat any reduction as an
  experiment to measure, not a default.

> **[measured here]** Asked to reply with two words, the model spent 166 tokens: 150 reasoning, 2
> answer. At ~25 tok/s that is ~6 seconds of latency on every step.

## 6. Verification — assume the report is wrong

Small models produce confident, plausible, wrong summaries. So do large ones; the rate differs,
the failure does not.

- **Never score from the exit code.** A run that changes nothing still passes a suite that was
  already green. **[measured here]** This happened on the first scored task.
- **Read the diff.** Every time.
- **Mutation-test the tests it wrote.** Remove the change and confirm the new test fails. A test
  that passes with and without the implementation is decoration. **[measured here]** This is how
  task 0003's tests were confirmed genuine.
- **Verify the harness before blaming the model.** Confirm the prompt arrived intact. A truncated
  input is indistinguishable from a stupid model if you only look at the output.
- **Separate harness failures from capability failures** in the record, or the evaluation
  converges on the wrong conclusion.

## 7. Division of labour

Keep with the frontier model: ambiguous requirements, architecture, decomposition, defining
constraints and acceptance criteria, reviewing output, and anything the worker failed at.

Delegate: exploration, implementation against a known design, mechanical refactors, renames,
boilerplate, tests, docs, lint and type errors, repetitive edits.

The metric is not whether the local model matches the frontier one. It is whether delegation
saves more than the review it creates.

## Open questions for this project

- Where does the task horizon actually end? One clean bounded task is a data point, not a curve.
- Does an explicit imperative framing measurably beat a descriptive one? Untested — the run
  intended to answer this was invalidated by a harness bug.
- Does the shell-editing habit cause quiet corruption on larger files, or does the model reliably
  switch to structured edits when the change is non-trivial?
- Is a mandatory terminal `respond` tool worth adding to this harness, given tool calling has not
  yet been the bottleneck here?

---

## Sources

Blog and vendor posts below are practitioner reports, not peer-reviewed; the ablation numbers in
particular come from a single study and should be treated as directional.

[^guardrails]: [LLM Agent Guardrails: Taking an 8B Local Model from 53% to 99% on Agentic Workflows](https://dev.to/monuminu/llm-agent-guardrails-the-engineering-playbook-for-taking-an-8b-local-model-from-53-to-99-on-18c)
[^contextrot]: [Chroma — Context Rot: How Increasing Input Tokens Impacts LLM Performance](https://www.trychroma.com/research/context-rot)
[^mecw]: [LLM Context Window Limitations in 2026](https://atlan.com/know/llm-context-window-limitations/)
[^harness]: [Agent Harness for Local LLMs — Build or Configure the Layer Around the Model](https://llmconfigurator.com/en/guides/coding-agents/agent-harness-local-llm)
[^failuremodes]: [LLM Agentic Failure Modes: Task Drift, Reward Hacking, Alignment Faking and More](https://ceaksan.com/en/llm-agentic-failure-modes)
[^invocation]: [When Agents Fail to Act: A Diagnostic Framework for Tool Invocation Reliability in Multi-Agent LLM Systems](https://arxiv.org/pdf/2601.16280)
[^quant]: [The Complete Guide to LLM Quantization with vLLM: Benchmarks & Best Practices](https://jarvislabs.ai/blog/vllm-quantization-complete-guide-benchmarks)
[^kv]: [KV-Cache Quantization: Boost Your Local LLM Setup](https://medium.com/rigel-computer-com/optimize-your-gpu-kv-cache-for-llama-cpp-opencode-co-13b6bc74f5ec)
[^kvcliff]: [KV-Cache Quantization: The q4_0 Cliff Your Logs Won't Warn You About](https://inventivehq.com/blog/kv-cache-quantization-quality-benchmark)

Further reading: [The State of Coding Agents Using Local LLMs (Feb 2026)](https://medium.com/@rontom/the-state-of-coding-agents-using-local-llms-february-2026-83259140e6ec),
[Using local LLMs for agentic coding](https://blog.alexewerlof.com/p/local-llms-for-agentic-coding),
[AgentFloor: How Far Up the Tool-Use Ladder Can Small Open-Weight Models Go?](https://arxiv.org/pdf/2605.00334)
