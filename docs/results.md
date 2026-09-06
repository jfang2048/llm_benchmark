# Results

Results for the current mainstream 8-9B cohort. All numbers are generated from
the machine-readable data under [`results/current/`](../results/current/); the
interactive dashboard is at [`docs/index.html`](../index.html). Nothing here is
hand-edited.

## Serving conditions (identical across all models)

- Engine: ggml-org/llama.cpp pinned tag v0.4.0, CUDA arch 86.
- Quantization: IQ4_XS (single uniform source, SHA256 in `configs/models.json`).
- Serving: `--ctx-size 4096 --parallel 2 --n-gpu-layers 999 --cont-batching`.
- GPU: RTX 3060 Laptop, 6 GiB VRAM. No CPU offload used.

## Capacity (60 req/cell, 3 repeats, temperature 0, OSL 128)

All four models completed the sweep with 0 failures and 0% error at every
concurrency (1/2/4/6/8). Aggregate means over 3 repeats:

| Model | TTFT p50 @ c=1 (ms) | Output tok/s @ c=8 | Peak VRAM (MiB) |
|---|---|---|---|
| Qwen3-8B | 104.1 | 94.5 | 4837 |
| DeepSeek-R1-Distill-Llama-8B | 91.3 | 98.0 | 4721 |
| GLM-4-9B-0414 | 54.6 | 85.4 | 5095 |
| Yi-1.5-9B-Chat | 68.6 | 86.7 | 5041 |

GLM-4-9B has the lowest first-token latency but also the lowest sustained
throughput and the highest VRAM (closest to the 6 GiB ceiling). DeepSeek-R1-
Distill-Llama-8B has the highest sustained throughput.

## Reliability (200 requests, c=1 and c=4, Wilson 95% CI)

Every cell: 200/200 successful, observed 100%, Wilson 95% CI [98.12%, 100%].
No transport errors for any model.

## Workload shape (per-model tokenizer, 5 profiles)

36 of 40 cells PASS. `rag_medium` (ISL 768) is unreliable for **Qwen3-8B** and
**DeepSeek-R1-Distill-Llama-8B** (`ServerDisconnectedError`/`ConnectionReset`/
request timeouts) while **GLM-4-9B** and **Yi-1.5-9B** remain clean. Those cells
are marked `UNSTABLE`/`TIMEOUT` and are excluded from the ranking — see the
dashboard shape table and `results/current/shape/`.

## Raw engine microbenchmark (llama-bench, pp512 / tg128, same binary)

| Model | pp512 tok/s | tg128 tok/s |
|---|---|---|
| Qwen3-8B | 1913 | 56.1 |
| DeepSeek-R1-Distill-Llama-8B | 1974 | 57.7 |
| GLM-4-9B-0414 | 1649 | 47.5 |
| Yi-1.5-9B-Chat | 1593 | 50.8 |

These are raw-engine numbers and are kept separate from the AIPerf end-to-end
serving numbers above.

## Energy estimate

`gpu_energy_j` / `gpu_j_per_request` / `gpu_j_per_output_token` in the cell
telemetry are GPU-side estimates (integral of 500 ms `nvidia-smi` power
sampling). They are not full-system energy and are not MLPerf Power compliant.

## Reading the data

- `results/current/capacity/` — `aggregate.tsv` (mean + CI95), `repeats.tsv`
  (raw repeats), `manifest.json` (engine/image/flags/workload hash).
- `results/current/reliability/` — `reliability.tsv` (Wilson CI + error types).
- `results/current/shape/` — per-profile aggregate + repeats.
- `results/current/llama-bench/` — raw llama-bench output.

Regenerate the dashboard with `make report-current`.
