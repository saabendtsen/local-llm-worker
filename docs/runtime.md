# Local model runtime

The runtime is deliberately independent of the agent harness. It is a plain `llama-server`
process exposing an OpenAI-compatible API, reusable by any other tool or experiment.

The configuration follows the deployment guide referenced in
[homelab-workspace#74](https://github.com/saabendtsen/homelab-workspace/issues/74)
(*Running Qwen 3.6 35B A3B on Windows*, kept at `docs/reference/local_llm_guide.pdf`).
Where this setup deviates from the guide, the reason is recorded under
[Deviations from the guide](#deviations-from-the-guide) — none of them are accidental.

## Model

`unsloth/Qwen3.6-35B-A3B-GGUF` — `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (20.6 GB).

Installed at `C:\models\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`.

The guide accepts either Q4_K_M or Q5_K_M and its example script uses Q5_K_M. Q4_K_M is used
here because this configuration also locks the weights into RAM (see `LOADMODE` below): 20.6 GB
locked out of 32 GB leaves room for the KV cache, the harness, and the OS, whereas 24.6 GB
locked would leave roughly 5 GB for everything else on the machine.

## Backend

`llama.cpp` **CUDA 13.3** build, installed at `C:\Tools\llama.cpp-cuda\`.

The winget package `ggml.llamacpp` ships the **Vulkan** zip only. Vulkan works on the RTX 3070
but is measurably slower than CUDA and handles MoE offload worse, so the CUDA build is installed
alongside rather than replacing it. The winget copy remains on `PATH` as a fallback; the scripts
here always use the absolute CUDA path so there is no ambiguity about which binary ran.

To upgrade, replace the contents of `C:\Tools\llama.cpp-cuda\` with a newer
`llama-b<NNNNN>-bin-win-cuda-13.3-x64.zip` plus its matching `cudart-` zip from
[llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases).

Verify the GPU is visible to the CUDA build:

```cmd
C:\Tools\llama.cpp-cuda\llama-server.exe --list-devices
```

## Launch

```cmd
scripts\start-worker.cmd
```

Every setting is overridable by environment variable; see the top of the script.

### Why these flags

| Flag | Reason |
| --- | --- |
| `-ngl 999` | Offload every layer to the GPU... |
| `-ncmoe 35` | ...then push the expert tensors of the first 35 layers back to CPU RAM. This pair is the whole trick: a ~3B-active MoE keeps dense attention and shared weights on the fast device while the bulky experts live in system RAM, so a 35B model runs in 8 GB of VRAM. |
| `-c 120000` | Long context, from the guide. Cheap here because the KV cache is quantized; see the note below on verifying it actually fits. |
| `-b 4096` / `-ub 2048` | Prompt-processing batch sizes. Larger batches speed up ingesting a big repository context, at the cost of VRAM for the compute buffer. |
| `-fa on` | Flash attention. Required for quantized KV cache, and cuts KV memory and prompt-processing time. |
| `-ctk q8_0` / `-ctv q8_0` | 8-bit KV cache. A coding agent sends long contexts; at f16 the cache alone would compete with the model for memory. |
| `--load-mode mmap+mlock` | Locks weights into physical RAM so Windows cannot page them to disk mid-generation. This is the modern spelling of the guide's `--mlock`, which is deprecated in this build. |
| `-t 6` | Physical cores only. Expert evaluation is memory-bandwidth bound; SMT threads add contention, not throughput. |
| `-np 1` | One slot. Concurrent slots would split the context budget, and the worker handles one task at a time. |
| `--jinja` | Uses the model's own chat template. Enabled by default in this build, but stated explicitly because **tool calling depends on it** and a future default change would break the harness silently. |

### When it does not fit

Three settings compete for the same 7.1 GB of usable VRAM: `NCMOE` (lower keeps more experts on
the GPU), `CTX` (KV cache), and `UBATCH` (compute buffer). If the server fails to allocate, back
off in this order:

1. `set UBATCH=512` — the guide's own fallback, and the cheapest thing to give up. Prompt
   processing slows; nothing else changes.
2. `set CTX=65536` — halve the context. Costs usable task size, so prefer giving up UBATCH first.
3. `set NCMOE=48` — push more experts to CPU. Frees VRAM but directly slows generation.

Each is a separate line before the script; `set NCMOE=48 && scripts\start-worker.cmd` on one line
assigns the trailing space too.

Going the other way, **lower** `NCMOE` in steps of 4 to buy generation speed with spare VRAM, and
stop about 1 GB short of full — the desktop compositor and any browser take VRAM too, and an
allocation failure mid-session costs more than a few tokens/sec.

Record the working combination in [../evaluation/results.md](../evaluation/results.md). The
guide's numbers were measured on an RTX 5060 Ti; this machine is an RTX 3070 of the same VRAM
size but a different generation, so its limits have to be confirmed rather than assumed.

## Deviations from the guide

| Setting | Guide | Here | Why |
| --- | --- | --- | --- |
| `--host` | `0.0.0.0` | `127.0.0.1` | The endpoint has **no authentication**. Binding it to every interface would expose an unauthenticated model server to the whole network. Loopback is the correct default; exposing it later must be a deliberate decision, not an inherited flag. |
| Quant | Q5_K_M | Q4_K_M | Combined with `mlock`, Q5_K_M would leave ~5 GB of RAM for the OS and harness. See [Model](#model). |
| `-t` | `8` | `6` | This CPU is a 6-core/12-thread Ryzen 5 3600. Threads beyond the physical core count contend for the same memory bandwidth. |
| `--mlock` | `--mlock` | `--load-mode mmap+mlock` | `--mlock` is deprecated in build b10448; this is its replacement spelling, same behaviour. |
| Paths | `C:\llama.cpp`, `C:\LLM_Models` | `C:\Tools\llama.cpp-cuda`, `C:\models` | The CUDA build sits in its own directory so it cannot be confused with the winget Vulkan install. |
| — | — | `--jinja`, `-np 1`, `--alias` | Needed for tool calling, single-slot context, and a stable model name for the harness. |

If `mlock` cannot lock the full working set, llama.cpp prints a warning and continues with
ordinary paging. That is not fatal, but it is the most likely cause of mid-generation stutter, so
it is worth reading the startup output the first time.

## Endpoint

| Property | Value |
| --- | --- |
| Base URL | `http://127.0.0.1:8000/v1` |
| Model name | `local-worker` |
| API key | Not required; send any non-empty string if the client insists |

Check it:

```cmd
scripts\check-worker.cmd
```

## Benchmarking

```cmd
scripts\bench-worker.cmd
```

Records prompt-processing and token-generation throughput. Run this once after any change to
`NCMOE`, the quant, or the llama.cpp build, and note the result in
[../evaluation/results.md](../evaluation/results.md) — inference time is one of the metrics the
prototype is judged on.
