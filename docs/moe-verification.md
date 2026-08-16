# Is the MoE actually sparse at runtime?

Yes — provably, on this machine. The proof does not depend on trusting llama.cpp's logs or the
model card; it falls out of a physical bound.

Question asked 2026-08-16. Method: GGUF header parsing, tensor accounting, and a memory-bandwidth
argument against measured throughput.

## Architecture, from the file itself

Parsed directly from the GGUF header of `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`
(22,134,528,992 bytes, GGUF v3, 733 tensors, 54 KV pairs):

| Key | Value |
| --- | --- |
| `general.architecture` | `qwen35moe` |
| `qwen35moe.block_count` | 40 |
| `qwen35moe.expert_count` | **256** |
| `qwen35moe.expert_used_count` | **8** |
| `qwen35moe.embedding_length` | 2048 |
| `qwen35moe.expert_feed_forward_length` | 512 |
| `qwen35moe.expert_shared_feed_forward_length` | 512 (one always-on shared expert) |
| `attention.head_count` / `head_count_kv` | 16 / 2 |
| `qwen35moe.full_attention_interval` | 4 — only 10 of 40 layers use full attention |
| `ssm.*` | hybrid SSM / linear attention in the other 30 layers |

Expert tensors are shaped `[2048, 512, 256]` — the trailing 256 *is* the expert axis, matching
`expert_count`. The router tensor `ffn_gate_inp` is `[2048, 256]`, producing exactly 256 logits
per token per layer.

## Where the weights physically live

| Category | Tensors | Bytes | Share |
| --- | --- | --- | --- |
| **Expert** (`ffn_{gate,up,down}_exps`) | 120 | 19,568,525,312 | **88.45%** |
| Attention / SSM / norms / shared expert | 521 | 1,424,148,992 | 6.44% |
| Embeddings and output | 12 | 1,046,650,880 | 4.73% |
| Router | 80 | 84,213,760 | 0.38% |

With `-ngl 999 -ncmoe 38`:

- **CPU RAM**: experts of layers 0–37 — **17.25 GiB**
- **GPU VRAM**: everything else — **3.35 GiB**

Corroborated three ways: the flag itself, the 19.63 GB process working set, and 6126 MiB of VRAM
in use — which matches the non-expert-only prediction and is nowhere near the 20.6 GiB a dense
GPU placement would require. At that size the model simply could not load on an 8 GB card.

## The proof

Measured generation, three runs with `cache_prompt: false` on an otherwise idle server:
23.48, 24.55, 22.69 tok/s. Take the conservative **23.48 tok/s**.

Prompt processing on a 6901-token prompt: 737.67 tok/s. The 31× ratio between prompt processing
and generation is itself the signature of bandwidth-bound decode.

**If every weight were read for every token**, the CPU-side traffic alone would be:

```
18,524,143,616 bytes/token × 23.48 tokens/s = 434.9 GB/s
```

The hardware cannot do this. `Win32_PhysicalMemory` reports 4 × 8 GiB at 3000 MT/s in dual
channel:

```
3000 MT/s × 8 bytes × 2 channels = 48.0 GB/s   (theoretical peak, JEDEC)
```

**434.9 required against 48.0 possible — 9.1× past a hard physical bound.** Turned around: a
dense read could sustain at most 2.59 tok/s in theory, ~1.9 tok/s realistically. We observe 23.48.
The dense hypothesis is falsified, not merely unlikely.

**Under 8-of-256 routing**, per token: 579 MB from CPU RAM, needing **13.59 GB/s** — 28% of
theoretical peak. Comfortably feasible, and the shortfall from 100% is what the gather pattern
predicts (8 scattered ~2.3 MB blocks per layer rather than one long stream).

## The independent cross-check

Active parameters computed *purely from tensor geometry* at `expert_used_count = 8`:

```
routed experts:  32,212,254,720 × 8/256              =  1,006,632,960
everything else, minus the token_embd row lookup     =  1,939,796,608
                                               TOTAL =  2,946,429,568  ≈ 2.95B
```

The model is marketed as **A3B** — 3B active. The file's own geometry reproduces that to within
2%, derived from a completely different direction than the timing. At k=256 it would be 33.2B; at
k=1, 2.07B. Only k=8 satisfies both the geometry and the observed throughput.

## What this does not prove

**It does not prove that different experts are selected for different tokens.** An implementation
that picked the same fixed 8 experts every time would read exactly the same 579 MB per token and
time identically. The bandwidth argument constrains the *cardinality* of the active set, not its
*variability*.

llama.cpp exposes no expert-selection telemetry on any endpoint, and the CUDA build ships no
expert-trace tool. Settling it needs either a custom build instrumenting `ggml_mul_mat_id`, or
`--override-kv qwen35moe.expert_used_count=int:1`, which should produce both a ~2× decode speedup
and a quality collapse. Worth doing the next time the server is being restarted anyway.

Two smaller caveats, stated so the number is not over-read: the 48.0 GB/s figure is theoretical
rather than measured on this box — which makes the conclusion *conservative*, since real achievable
bandwidth is lower and the contradiction therefore larger. And "9.1×" should be read as "at least
9.1×".

## Why it matters practically

The sparsity is what makes the whole prototype viable. A dense 35B model at Q4 would be unusable
here — under 2 tok/s. The MoE structure is the reason a 20.6 GB model runs at 25 tok/s on an 8 GB
card, and it is why `-ncmoe` is the right tuning lever: moving *expert* weights to CPU costs
little because only 3% of them are touched per token, whereas moving attention weights would cost
dearly because all of them are.
