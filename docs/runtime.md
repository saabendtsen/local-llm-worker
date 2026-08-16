# Local model runtime

The runtime is deliberately independent of the agent harness. It is a plain `llama-server`
process exposing an OpenAI-compatible API, reusable by any other tool or experiment.

## Model

`unsloth/Qwen3.6-35B-A3B-GGUF` — `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf` (20.6 GB).

Installed at `C:\models\Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`.

Q5_K_M (24.6 GB) was rejected: with 32 GB of system RAM and the OS resident, it leaves no room
for the KV cache and working set once expert weights are held in RAM. Q4_K_M is the largest
quant that fits with headroom.

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
| `-ncmoe %NCMOE%` | ...then push the expert tensors of the first N layers back to CPU RAM. This pair is the standard recipe for running a large MoE on small VRAM: dense attention and shared weights stay on the fast device, bulky experts live in RAM. |
| `-fa on` | Flash attention. Required for quantized KV cache, and cuts KV memory and prompt-processing time. |
| `-ctk q8_0 -ctv q8_0` | Quantized KV cache. A coding agent sends long contexts; at f16 the cache alone would compete with the model for RAM. |
| `--jinja` | Uses the model's own chat template. **Required for tool calling** — without it the harness cannot reliably drive tools. |
| `-t 6` | Physical cores only. Expert evaluation is memory-bandwidth bound; SMT threads add contention, not throughput. |
| `-np 1` | One slot. Concurrent slots would split the context budget, and the worker handles one task at a time. |
| `-c 32768` | Coding agents burn context fast. Lower it if RAM is tight; raise it only after confirming headroom. |

### Tuning `NCMOE`

`NCMOE` is the one number that needs fitting to the machine. It is the count of layers whose
experts are kept in CPU RAM — **higher means less VRAM used and slower generation**.

The script defaults to `99`, i.e. all experts on CPU. That is the safe starting point and is
guaranteed to load. To trade VRAM for speed:

1. Start the server and note the reported VRAM use.
2. Lower `NCMOE` by 4 and restart.
3. Repeat until the process fails to allocate or Windows starts evicting, then go back up by 4.

```cmd
set NCMOE=32
scripts\start-worker.cmd
```

Set it on its own line — `set NCMOE=32 && ...` on one line assigns the trailing space too.

Leave roughly 1 GB of VRAM free — the desktop compositor and any browser will take some, and an
allocation failure mid-session is worse than a few lost tokens/sec.

## Endpoint

| Property | Value |
| --- | --- |
| Base URL | `http://127.0.0.1:8000/v1` |
| Model name | `local-worker` |
| API key | Not required; send any non-empty string if the client insists |

Bound to `127.0.0.1` on purpose: the endpoint has no authentication and must not be reachable
from the network. Exposing it later requires a deliberate decision, not a flag change.

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
