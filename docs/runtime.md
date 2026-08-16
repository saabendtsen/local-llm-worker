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

Run it in its own terminal window and leave it there. The server holds ~17 GB of locked RAM and
takes 20–55 seconds to load, so it is a long-lived process, not something to start per task. If
it is launched as a child of a tool or script that later exits, it is killed along with its
parent and the next request fails with a connection error rather than anything descriptive.

### Why these flags

| Flag | Reason |
| --- | --- |
| `-ngl 999` | Offload every layer to the GPU... |
| `-ncmoe 38` | ...then push the expert tensors of the first 38 layers back to CPU RAM. This pair is the whole trick: a ~3B-active MoE keeps dense attention and shared weights on the fast device while the bulky experts live in system RAM, so a 35B model runs in 8 GB of VRAM. The guide uses 35; see [VRAM headroom](#vram-headroom) for why 38 is the default here. |
| `-c 120000` | Long context, from the guide. Cheap here because the KV cache is quantized; see the note below on verifying it actually fits. |
| `-b 4096` / `-ub 2048` | Prompt-processing batch sizes. Larger batches speed up ingesting a big repository context, at the cost of VRAM for the compute buffer. |
| `-fa on` | Flash attention. Required for quantized KV cache, and cuts KV memory and prompt-processing time. |
| `-ctk q8_0` / `-ctv q8_0` | 8-bit KV cache. A coding agent sends long contexts; at f16 the cache alone would compete with the model for memory. |
| `--load-mode mmap+mlock` | Locks weights into physical RAM so Windows cannot page them to disk mid-generation. This is the modern spelling of the guide's `--mlock`, which is deprecated in this build. |
| `-t 6` | Physical cores only. Expert evaluation is memory-bandwidth bound; SMT threads add contention, not throughput. |
| `-np 1` | One slot. Concurrent slots would split the context budget, and the worker handles one task at a time. |
| `--jinja` | Uses the model's own chat template. Enabled by default in this build, but stated explicitly because **tool calling depends on it** and a future default change would break the harness silently. |

### VRAM headroom

The guide's `-ncmoe 35` loads and runs on this machine, but leaves almost nothing spare:

| `NCMOE` | VRAM used | Free | Prompt eval | Generation |
| --- | --- | --- | --- | --- |
| 35 (guide) | 7802 MiB | 390 MiB | ~692 tok/s | ~27.3 tok/s |
| **38 (default here)** | **6034 MiB** | **2158 MiB** | **~690 tok/s** | **~25.3 tok/s** |

Measured on the RTX 3070 with a 13k-token prompt, warm. The idle desktop already holds ~600 MiB
to 1 GB of VRAM before the server starts, and a browser can take several hundred more, so at
`NCMOE=35` an ordinary desktop session can push the GPU into an allocation failure part-way
through a task.

Three layers of experts moved to CPU buys 1.8 GB of headroom and costs about 7% of generation
speed. Prompt processing — the dominant cost when an agent sends a large repository context — is
unchanged. For a worker running in the background while the machine is also being used, that is
the right trade. Set `NCMOE=35` if the GPU is otherwise idle and generation speed matters more.

Measure warm, not cold. Generation on the first request after load ran at 19.8 tok/s and settled
around 25 tok/s by the third; a single cold reading will understate the configuration by 20%.

### When it does not fit

Three settings compete for the same 7.1 GB of usable VRAM: `NCMOE` (lower keeps more experts on
the GPU), `CTX` (KV cache), and `UBATCH` (compute buffer). If the server fails to allocate, back
off in this order:

1. `set NCMOE=42` — push more experts to CPU. The cheapest lever by a wide margin: it frees VRAM
   in large steps and costs only a few percent of generation speed each time.
2. `set UBATCH=512` — the guide's own fallback. Prompt processing slows; nothing else changes.
3. `set CTX=65536` — halve the context. Costs usable task size, so give this up last.

Each is a separate line before the script; `set NCMOE=42 && scripts\start-worker.cmd` on one line
assigns the trailing space too.

Record the working combination in [../evaluation/results.md](../evaluation/results.md).

## A tested piece of advice that did not hold

At startup llama.cpp prints:

```text
tensor overrides to CPU are used with mmap enabled - consider using --load-mode none for better performance
```

That was measured and rejected. On the same 13k-token prompt:

| Load mode | Prompt eval | Generation |
| --- | --- | --- |
| `mmap+mlock` | ~692 tok/s | ~27 tok/s |
| `none` | ~524 tok/s | ~24 tok/s |

`--load-mode none` was slower on both axes here, so the guide's intent — keep the weights locked
in RAM — is kept. The warning is left un-silenced because it is legitimate general advice; it
simply does not apply to this hardware. Re-test it after a llama.cpp upgrade rather than assuming
the result still holds.

## Deviations from the guide

| Setting | Guide | Here | Why |
| --- | --- | --- | --- |
| `--host` | `0.0.0.0` | `127.0.0.1` | The endpoint has **no authentication**. Binding it to every interface would expose an unauthenticated model server to the whole network. Loopback is the correct default; exposing it later must be a deliberate decision, not an inherited flag. |
| CORS | not set (`*`) | `--cors-origins localhost` | llama-server allows **all** origins by default and warns about it at startup. With the default, any page in a running browser can call the loopback endpoint cross-origin *and read the response* — a stranger's site using your GPU and seeing what it produced. Restricting to localhost withholds the `Access-Control-Allow-Origin` header from foreign origins, so the browser refuses to hand the response back to the page. Verified: an `Origin: https://evil.example.com` request gets no such header, `http://localhost:8000` gets it reflected. Note this is a browser-enforced control — it stops pages reading replies, not a non-browser client from calling the port. The built-in web UI still works, and Cline is unaffected since it sends no `Origin` header. |
| `-ncmoe` | `35` | `38` | 1.8 GB more VRAM headroom for ~7% of generation speed. See [VRAM headroom](#vram-headroom). |
| Quant | Q5_K_M | Q4_K_M | Combined with `mlock`, Q5_K_M would leave ~5 GB of RAM for the OS and harness. See [Model](#model). |
| `-t` | `8` | `6` | This CPU is a 6-core/12-thread Ryzen 5 3600. Threads beyond the physical core count contend for the same memory bandwidth. |
| `--mlock` | `--mlock` | `--load-mode mmap+mlock` | `--mlock` is deprecated in build b10448; this is its replacement spelling, same behaviour. |
| Paths | `C:\llama.cpp`, `C:\LLM_Models` | `C:\Tools\llama.cpp-cuda`, `C:\models` | The CUDA build sits in its own directory so it cannot be confused with the winget Vulkan install. |
| — | — | `--jinja`, `-np 1`, `--alias` | Needed for tool calling, single-slot context, and a stable model name for the harness. |
| — | — | `--reasoning-effort` | Exposed as `EFFORT` so reasoning verbosity can be traded against latency. Left at the template default; see [harness-cline.md](harness-cline.md). |

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
