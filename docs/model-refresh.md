# Model refresh on the RTX 3060

## Candidate selection

The refresh targets small open-weight instruction models with a published
GGUF. It screens the text path on the same 6,144 MiB RTX 3060 Laptop GPU
and Ubuntu 24.04 under WSL2. The original 192 prompts and their scoring
rules stay fixed. Admission checks two representative streamed prompts
and the server log's full layer count and 2,048-token slot allocation.

The Google names E2B and E4B refer to effective parameter counts. The
selected Q4_K_M artifacts are 3.50 GB and 5.49 GB on disk. Disk size leaves
out the KV cache, workspace and background GPU memory. The NVIDIA model
uses its own Open Model License. Google, IBM and Mistral candidates use
Apache 2.0. The Gemma and Nemotron weights were acquired as immutable
Ollama registry blobs and run by the same llama.cpp server. The Granite
4.1 blob matches IBM's published Hugging Face SHA-256 byte for byte.
The registry records each selected conversion and digest.
The refresh uses pinned artifacts and the same publicly released cases.
The [original provenance audit](fresh.md#exposure-audit) records the source
and exposure checks for the first sweep.

[Google model overview](https://ai.google.dev/gemma/docs/core) ·
[IBM Granite 4.1](https://huggingface.co/ibm-granite/granite-4.1-3b) ·
[Mistral GGUF](https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-GGUF) ·
[NVIDIA GGUF and license](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF) ·
[Ollama Gemma tags](https://ollama.com/library/gemma4/tags) · [Ollama NVIDIA tags](https://ollama.com/library/nemotron-3-nano/tags)

## Protocol and bridge run

All added models use the original upstream llama.cpp image and Q4_K_M
artifacts. The server uses the same two closed-loop clients, two slots,
4,096 total context, 512-token output cap, greedy decoding and request
budgets of 1 s to visible content and 12 s to completion. The corpus and
its seeded permutation match the [original sweep](fresh.md). Each
deployment has one measured request per case. The archive records
two launch batches. Model transfers were quiesced for timed measurements.
A Qwen3.5-4B bridge run on the original image and weights provides an across-session check on the
same cases. The dashboard retains its original measurement for comparison.

The refresh is a deployment comparison. Model families, tokenizers and
quantization publishers vary. Each peak covers the full mixed-corpus run.
Each timing p95 uses completed streams, with visible text required for the
first-answer metric.

The Gemma 4 E4B admission reported 43/43 GPU layers and a 3,427 MiB
device peak. Its loader also reported a 2,730 MiB CPU-mapped model
buffer and a 3,019 MiB CUDA model buffer. The GPU layer count describes
layer placement. Host mappings and allocated device memory have separate
meanings. Both buffers are recorded in the [launch audit](../results/current/fresh-refresh/audit.json).

<!-- refresh-results-start -->

## Results

The refresh measured 1,344 requests, including
192 for the bridge run. The expanded dashboard covers 19 distinct
deployments. Each corpus contributes 96 cases per deployment.

**Table 1 | Admission at two slots and 4,096 total context.** Peak is from the smoke.

| Candidate | Status | GPU layers | Peak VRAM (MiB) |
|---|---|---:|---:|
| Gemma 4 E4B | admitted | 43 | 3427 |
| Granite 4.0 1B | admitted | 41 | 1513 |
| Gemma 4 E2B | admitted | 36 | 1811 |
| Granite 4.1 3B | admitted | 41 | 2523 |
| Ministral 3 3B | admitted | 27 | 2669 |
| Nemotron 3 Nano 4B | admitted | 43 | 2967 |

**Table 2 | Full sweep.** Accuracy denominators are 96 cases per corpus.
First-visible p95 uses completed streams with visible text. Parentheses show the sample count.

| New deployment | Email exact (of 96) | Bilingual on time (of 96) | Email first p95 (ms) | Bilingual first p95 (ms) | Peak VRAM (MiB) |
|---|---:|---:|---:|---:|---:|
| Granite 4.1 3B | 29 | 45 | 486 (96) | 179 (96) | 2,525 |
| Nemotron 3 Nano 4B | 28 | 65 | 811 (96) | 443 (96) | 3,003 |
| Granite 4.0 1B | 20 | 46 | 288 (96) | 124 (96) | 1,515 |
| Ministral 3 3B | 0 | 0 | 499 (88) | 328 (96) | 2,671 |
| Gemma 4 E2B | 0 | 0 | 490 (96) | 236 (96) | 1,813 |
| Gemma 4 E4B | 0 | 34 | 816 (96) | 386 (96) | 3,429 |

**Table 3 | Qwen3.5-4B bridge.** Same GGUF, image, launch arguments and cases.

| Sweep | Email exact (of 96) | Bilingual on time (of 96) | Email first p95 (ms) | Bilingual first p95 (ms) | Peak VRAM (MiB) |
|---|---:|---:|---:|---:|---:|
| Original | 42 | 69 | 859 (96) | 357 (96) | 3,239 |
| Refresh | 42 | 69 | 872 (96) | 357 (96) | 3,195 |

The bridge reproduced both scoring verdicts on all 192 cases.

**Table 4 | Parser diagnostics.** Recovered replies add to the strict
exact counts after accepting one Markdown fence around the same answer.
The error column counts client-side failures under the original protocol.

| New deployment | Email fence recoveries | Bilingual fence recoveries | Client errors |
|---|---:|---:|---:|
| Granite 4.0 1B | 0 | 0 | 0 |
| Ministral 3 3B | 46 | 41 | 8 |
| Gemma 4 E2B | 27 | 59 | 0 |
| Granite 4.1 3B | 0 | 0 | 0 |
| Gemma 4 E4B | 29 | 44 | 0 |
| Nemotron 3 Nano 4B | 0 | 0 | 0 |

<!-- refresh-results-end -->

## Reproduction and data

Weights, hashes, revisions and ports are in the
[model registry](../configs/models.json). Download the chosen model IDs
with `scripts/download_models.sh`. For current candidates, run the
admission screen and then select the admitted arms explicitly.

```bash
python3 -m bench.fresh_admit --output .agent/refresh-admission-local
python3 -m bench.fresh --model ARM --model qwen3_5_4b_compact --output .agent/refresh-local
python3 -m bench.fresh_report --extension .agent/refresh-local
```

Repeat `--model` for additional arms. The [archive](../results/current/fresh-refresh/)
contains request timings, GPU samples, admission evidence and the model
image and weight identifiers. [Expanded dashboard](https://jfang2048.github.io/llm_benchmark/#fresh) ·
[Troubleshooting knowledge base](troubleshooting.md)
