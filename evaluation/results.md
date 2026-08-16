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
| 0001 | credential path detectors | feature-small | 9 | passed | **takeover** | 254 s | no diff — wrong deliverable |

Outcome is one of: clean / minor repair / major repair / takeover / harness failure.
See [README.md](README.md) for what each means. Score from the diff, not from `verify.passed`.

### 0001 — the failure mode, in full

The task asked for a new entry in `PATH_DETECTORS` so the credential-inventory script would
recognise `.netrc`, `.npmrc`, `.pypirc`, and `kubeconfig`, with tests.

The worker instead **audited the repository for credential files** and returned a confident
report titled *"Credential-Bearing Config Filename Detection Report"*, concluding *"No hardcoded
secrets or credential files were found. The workspace is clean."* Across 9 turns and 16 tool
calls over 254 seconds it never opened `scripts/inventory-git-credential-exposure.py` and never
opened the test module. It changed nothing.

It did the *subject matter* of the tool rather than the *engineering task about* the tool.

Three things make this the most instructive run so far:

1. **`verify.passed` was `true`.** Nothing changed, and the suite was already green, so the
   acceptance command reported success. A pipeline scoring on exit codes would have filed this as
   a win. This is the exact quiet failure the evaluation was built to catch, and it appeared on
   the very first scored task.
2. **Tool use was not the problem.** All 16 calls were well-formed, and the exploration was
   competent. The failure was comprehension of what the deliverable was.
3. **The framing probably contributed.** The task's heading read *"detect well-known
   credential-bearing config filenames"* — which is genuinely ambiguous between "make the tool
   detect these" and "go detect these". A frontier model resolves that from context; this one
   took the literal reading and never revisited it.

The open question is how much of this is model capability and how much is prompt framing. Rerun
the same task with an unambiguous imperative opening — naming the file to edit in the first
sentence — before concluding anything about the task horizon. If explicit framing fixes it, the
finding is *"this worker needs the deliverable stated as an instruction, not described as an
outcome"*, which is cheap to accommodate. If it does not, the horizon is lower than hoped.

## Findings

**The worker edits with shell text manipulation, not structured edit tools.** In its first real
task it used `cat >> file << 'EOF'` to append and `sed -i 's/old/new/'` to substitute, never
touching Pi's `edit` or `write` tools. The result was correct, but the method sets the expected
failure mode: `cat >>` cannot express an edit in the middle of a file, and `sed` substitutes by
pattern, so a pattern matching twice changes both occurrences silently. The prediction to test is
that this worker fails *quietly* — wrong line changed, tests still green — rather than loudly.
Diffs must be read. See [../docs/harness-pi.md](../docs/harness-pi.md).

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
