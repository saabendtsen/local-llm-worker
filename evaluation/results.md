# Results

## Runtime baselines

One row per configuration change (quant, `NCMOE`, load mode, llama.cpp build).

Measured with a 13,115-token prompt against the running server, reading `print_timing` from the
server log. Take the **warm** figure: generation on the first request after load ran at
19.8 tok/s and settled around 25 tok/s by the third, so a cold reading understates the
configuration by roughly 20%.

| Date | Build | Quant | NCMOE | Load mode | Prompt eval | Generation | VRAM used | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-08-16 | b10448 CUDA 13.3 | UD-Q4_K_M | 35 | `mmap+mlock` | 692 tok/s | 27.3 tok/s | 7802 MiB | Guide's value. Only 390 MiB free — too tight to share the GPU with a desktop session. |
| 2026-08-16 | b10448 CUDA 13.3 | UD-Q4_K_M | 35 | `none` | 524 tok/s | 24.5 tok/s | 7740 MiB | llama.cpp's startup advice. Slower on both axes; rejected. |
| 2026-08-16 | b10448 CUDA 13.3 | UD-Q4_K_M | **38** | `mmap+mlock` | **690 tok/s** | **25.3 tok/s** | **6034 MiB** | **Current default.** 1.8 GB headroom for ~7% of generation speed. |

Load time was 54 s cold and ~20 s with the model still in the OS file cache. Resident set is
~17–18 GB of the machine's 32 GB.

Context: the full 120,000-token context requested by the guide allocates successfully
(`n_ctx_slot = 120064`), so context size is not the binding constraint here — VRAM headroom is.

### Correctness spot-check

Asked to count 600 generated lines inside a 13k-token prompt, the model answered `600` correctly
on 4 of 4 attempts across configurations. That is a retrieval check, not a coding-ability check;
it only establishes that long context is genuinely being attended to rather than truncated.

## Harness validation

Before any scored task, the end-to-end loop was proven on a throwaway two-file Python repository:
add a function plus a covering test, then run pytest.

| Metric | Result |
| --- | --- |
| Wall clock | 49.5 s, unattended |
| Turns | 9 |
| Tool calls | 10 (`bash` ×8, `read` ×2) |
| Diff | 2 files, +7/−1 |
| Verify | `python -m pytest -q` passed, confirmed by an independent rerun |

The implementation was better than the minimum asked for: `shout()` was written as
`greet(name).upper()`, reusing the existing function rather than duplicating its string. That is
a real, if small, sign of judgement rather than pattern completion.

This run is not scored below — the target was a scratch repository, so it measures the harness,
not the worker's usefulness on real work. Its run directory was deleted for that reason; the
behavioural finding it produced is recorded under [Findings](#findings).

## Delegated tasks

| # | Task | Category | Turns | Verify | Outcome | Time | Diff quality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0001 | credential path detectors | feature-small | 9 | passed | **harness failure** | 254 s | n/a — prompt truncated |
| 0002 | same, imperative framing | feature-small | 1 | passed | **harness failure** | 16 s | n/a — prompt truncated |
| 0003 | same task, prompt delivered | feature-small | 15 | passed | **clean** | 351 s | correct, tested, in-style |

Outcome is one of: clean / minor repair / major repair / takeover / harness failure.
See [README.md](README.md) for what each means. Score from the diff, not from `verify.passed`.

### 0001 and 0002 — the harness broke, not the model

Both runs were initially misread as model failures. They were not. The runner passed the task as
a command-line argument to `pi`, which on Windows resolves to `pi.CMD`; launching a `.CMD` hands
the argument list to `cmd.exe`, **which truncates any argument at its first newline**.

So the worker never received the task. In 0001 it got only the title line — *"# Task: detect
well-known credential-bearing config filenames"* — which explains its behaviour completely: it
dutifully audited the repository for credential files and returned a confident report, because
that is exactly what the one line it received asked for. In 0002 the file opened with an HTML
comment, so the worker received the four characters `<!--` and sensibly asked what was meant.

The original write-up of 0001 concluded the model had misread an ambiguous heading. That was
wrong, and wrong in the most expensive direction: it blamed the model for the harness's defect
and would have sent the whole evaluation chasing prompt phrasing.

Two changes prevent a repeat:

- The runner now resolves Pi's JS entry point and runs it under `node` directly, bypassing the
  shim and `cmd.exe`.
- Every run verifies the prompt arrived intact by checking the event stream's first user message
  against what was sent, and says explicitly *"score this as a HARNESS FAILURE, not a model
  result"* when it did not.

**The lesson generalises beyond this bug.** A truncated prompt is indistinguishable from a stupid
model when you only look at the diff: the worker does something irrelevant, confidently, and the
run reads as a comprehension failure. Any measurement of a worker has to verify its own input
before attributing anything to capability.

### 0003 — the same task, done properly

With delivery fixed, the identical task from 0001 succeeded: 15 turns, 15 tool calls, 351
seconds, two files changed, +57 lines, whole suite green at 156 passed (up from 154).

The diff was reviewed rather than trusted:

- **The detector is correctly anchored.**
  `(?:^|/)(\.netrc|\.npmrc|\.pypirc)$|(?:(?:^|/)kubeconfig)(?:$|/)` handles both a bare filename
  and one nested in a directory, matching the convention of the three existing entries.
- **The tests are meaningful, not decorative.** Verified by mutation: deleting the new detector
  line makes the positive test fail with `KeyError: '.netrc'`. The test genuinely exercises the
  change rather than passing regardless.
- **The invariant held.** No payload field was added; the tool still reports paths and categories
  only.
- **Constraints were respected.** Exactly the two permitted files changed, and the three existing
  detector categories were untouched.
- **Style matched.** The tests build real temporary Git repositories in the existing style rather
  than mocking, as the task asked.

One quality nit, not a defect: the category is named `config-file`, which is vague next to
`environment-file` / `credential-name` / `private-key-name` — something like
`credential-config-name` would carry more meaning. Worth a rename, not a rejection.

The negative test asserts absence from `candidate_paths` entirely, which passes with or without
the change, so it is weaker than the positive one. It still encodes the right intent.

Work branch: `worker/0003-credential-path-detectors-rerun`.

## Findings

**Tool choice scales with the task.** On a trivial scratch repository the worker did everything
through the shell — `cat >> file << 'EOF'` to append, `sed -i` to substitute — and touched no
structured edit tool. That looked like a weakness worth worrying about. On the real task it used
`edit` four times alongside `read` and `bash`, and produced a properly anchored insertion into
the middle of an existing dictionary. The earlier reading was drawn from one throwaway run and
overstated: the worker reaches for shell text manipulation when the change is a trivial append,
and for real edit tools when it is not.

**A bounded task of this shape is within reach, at roughly six minutes.** 0003 is one data point,
not a task horizon, but it is the right shape: a known file, a stated invariant, an explicit
false-positive case to avoid, and an acceptance command. The worker respected all four.

**Generation speed is not the bottleneck; reasoning volume is.** At ~25 tok/s the raw rate is far
better than expected for a 35B model on an 8 GB card. But the model spent 150 reasoning tokens to
answer a two-word request, so a short agent step costs several seconds of thinking before any
output appears. Whether that is worth paying is the thing to measure across real tasks — see
[../docs/harness-cline.md](../docs/harness-cline.md).

**Prompt processing at ~690 tok/s sets the practical task size.** A 13k-token repository context
costs ~19 seconds before the first token. Prefix caching helps materially on follow-up turns
within a task — a second request sharing the same prefix reprocessed only the 2k-token tail — so
the cost is per-task rather than per-step, as long as the harness keeps the context stable.

<!-- Further findings as tasks are run: which categories are reliable, where the task horizon
     ends, whether failures are loud or quiet. -->
