# Results

## Runtime baselines

Record one row per configuration change (quant, `NCMOE`, llama.cpp build). From
`scripts\bench-worker.cmd`.

| Date | Build | Quant | NCMOE | pp512 (t/s) | tg128 (t/s) | VRAM | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | b10448 CUDA 13.3 | UD-Q4_K_M | 99 | | | | initial baseline, all experts on CPU |

## Delegated tasks

| # | Task | Category | Iterations | Tests | Outcome | Time | Diff quality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | |

Outcome is one of: clean / minor repair / major repair / takeover / harness failure.
See [README.md](README.md) for what each means.

## Findings

<!-- As patterns emerge: which categories are reliable, where the task horizon ends,
     whether failures are loud or quiet. -->
