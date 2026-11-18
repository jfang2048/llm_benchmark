# Four smaller models on the same 6 GiB GPU

The Home Lab suite added Qwen3.5-0.8B, LFM2.5-1.2B-Instruct, Qwen3.5-2B and
SmolLM3-3B. All four use text-only Q4_K_M GGUFs on the pinned upstream
llama.cpp image. Each ran the original 18 synthetic cases twice at one and
four in-flight requests. The 288 new requests bring the scorecard to 936.
Raw timing windows and source commits remain in the merged manifest.

## One person

| Deployment | Correct JSON | On time | On time with fence | First-answer p95 (ms) | Usable/min | Peak MiB |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-0.8B (text-only) | 12/36 | 12/36 | 16/36 | 162 | 85.8 | 1009 |
| LFM2.5-1.2B-Instruct | 12/36 | 12/36 | 12/36 | 93 | 134.8 | 1199 |
| Qwen3.5-2B (text-only) | 22/36 | 22/36 | 22/36 | 250 | 126.2 | 1753 |
| SmolLM3-3B | 0/36 | 0/36 | 16/36 | — | 0.0 | 2533 |

## Small batch

| Deployment | Correct JSON | On time | On time with fence | First-answer p95 (ms) | Usable/min | Peak MiB |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-0.8B (text-only) | 11/36 | 11/36 | 15/36 | 582 | 97.3 | 1009 |
| LFM2.5-1.2B-Instruct | 12/36 | 12/36 | 12/36 | 487 | 169.0 | 1199 |
| Qwen3.5-2B (text-only) | 22/36 | 22/36 | 22/36 | 814 | 148.2 | 1753 |
| SmolLM3-3B | 0/36 | 0/36 | 14/36 | — | 0.0 | 2533 |

First-answer p95 uses correct raw replies. Usable jobs per minute counts
correct replies within both time limits and uses elapsed batch time.
Runs were collected in separate sessions on one machine, so small rate
differences are best read as approximate.

LFM2.5 finished 12/36 batch jobs correctly and on time. Its short batch
window gave it the highest rate in this run. Qwen3.5-2B finished 22/36
within the same limits and used 1753 MiB at peak. For SmolLM3, accepting
a single code fence recovered 16 single-user replies and 14 batch replies.

## What fits at a larger context?

The probe allocated 4,096, 8,192, and 16,384 tokens in total across two
slots. The largest setting is 8,192 tokens per slot. It disabled auto-fit,
requested all GPU layers, checked the layer counts and slot size in the
server log, and waited for one short streamed reply at each setting.
Peak VRAM is device-wide and includes desktop use. At the largest setting,
Qwen3-8B left 180 MiB of device headroom in its probe.

| Deployment | 4,096 peak MiB | 8,192 peak MiB | 16,384 peak MiB |
|---|---:|---:|---:|
| Qwen3-4B | 3236 | 3814 | 4970 |
| Qwen3.5-4B (text-only) | 3262 | 3392 | 3652 |
| Qwen3-8B | 4912 | 5490 | 5964 |
| Qwen3.5-0.8B (text-only) | 1005 | 1053 | 1153 |
| LFM2.5-1.2B-Instruct | 1191 | 1241 | 1341 |
| Qwen3.5-2B (text-only) | 1747 | 1795 | 1895 |
| SmolLM3-3B | 2525 | 2815 | 3395 |

The context probe measures allocation and short-response startup. The
Home Lab results above use a 4,096-token total context. Accuracy and latency
for long documents would require their own workload.

[Interactive scorecard](https://jfang2048.github.io/llm_benchmark/#home-lab) · [Protocol](home-lab.md) · [Run files](../results/current/home-lab/)

## Weights

| Checkpoint | GGUF file size (MiB) | Q4_K_M source |
|---|---:|---|
| [Qwen3.5-0.8B (text-only)](https://huggingface.co/Qwen/Qwen3.5-0.8B) | 553 | [Pinned artifact](https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF/blob/f36b1ea49a332ede8fe5f389bbf5b3575ef71f48/Qwen_Qwen3.5-0.8B-Q4_K_M.gguf) |
| [LFM2.5-1.2B-Instruct](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct) | 697 | [Pinned artifact](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF/blob/8ed288026e23958ad9dfa92d53ed773a8eee7125/LFM2.5-1.2B-Instruct-Q4_K_M.gguf) |
| [Qwen3.5-2B (text-only)](https://huggingface.co/Qwen/Qwen3.5-2B) | 1332 | [Pinned artifact](https://huggingface.co/bartowski/Qwen_Qwen3.5-2B-GGUF/blob/7d26695454df6de5fbcce2e58681e62dae06ce43/Qwen_Qwen3.5-2B-Q4_K_M.gguf) |
| [SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) | 1827 | [Pinned artifact](https://huggingface.co/bartowski/HuggingFaceTB_SmolLM3-3B-GGUF/blob/86b3536ed1ca0dcb4716745642db4e6804bf3d32/HuggingFaceTB_SmolLM3-3B-Q4_K_M.gguf) |

The figures in this table are disk bytes expressed as MiB. The context
table measures device VRAM, which includes allocations beyond the file.

## Task breakdown

Single-user results with a JSON code fence accepted.

| Deployment | Extraction | Masking | Archive lookup | English | Chinese |
|---|---:|---:|---:|---:|---:|
| Qwen3.5-0.8B (text-only) | 10/12 | 0/12 | 6/12 | 8/18 | 8/18 |
| LFM2.5-1.2B-Instruct | 8/12 | 0/12 | 4/12 | 10/18 | 2/18 |
| Qwen3.5-2B (text-only) | 10/12 | 2/12 | 10/12 | 12/18 | 10/18 |
| SmolLM3-3B | 8/12 | 0/12 | 8/12 | 10/18 | 6/18 |
