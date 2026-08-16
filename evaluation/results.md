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

## Delegated tasks

| # | Task | Category | Iterations | Tests | Outcome | Time | Diff quality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |

Outcome is one of: clean / minor repair / major repair / takeover / harness failure.
See [README.md](README.md) for what each means.

## Findings

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
