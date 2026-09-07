# Results

Results for the current benchmark: the mainstream 8-9B cohort plus the
Spark-X2.5-4B reference baseline. All numbers are generated from the
machine-readable data under [`results/current/`](../results/current/); the
interactive dashboard is at [`docs/index.html`](../index.html). Nothing here
is hand-edited.

## Serving conditions

| Cohort | Engine | Quantization |
|---|---|---|
| Mainstream 8-9B | ggml-org/llama.cpp v0.4.0 (CUDA arch 86) | IQ4_XS |
| Spark reference | XHToken llama.cpp fork (pinned) | IQ4_XS |

Serving: `--ctx-size 4096 --parallel 2 --n-gpu-layers 999 --cont-batching`,
GPU RTX 3060 Laptop (6 GiB), no CPU offload.

## Mainstream 8-9B cohort

### Capacity (60 req/cell, 3 repeats, temperature 0, OSL 128)

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

### Reliability (200 requests, c=1 and c=4, Wilson 95% CI)

Every cell: 200/200 successful, observed 100%, Wilson 95% CI [98.12%, 100%].
No transport errors for any model.

### Workload shape (per-model tokenizer, 5 profiles)

36 of 40 cells PASS. `rag_medium` (ISL 768) is unreliable for **Qwen3-8B** and
**DeepSeek-R1-Distill-Llama-8B** (`ServerDisconnectedError`/`ConnectionReset`/
request timeouts) while **GLM-4-9B** and **Yi-1.5-9B** remain clean. Those
cells are marked `UNSTABLE`/`TIMEOUT` and are excluded from the ranking.

### Raw engine microbenchmark (llama-bench, pp512 / tg128, same binary)

| Model | pp512 tok/s | tg128 tok/s |
|---|---|---|
| Qwen3-8B | 1913 | 56.1 |
| DeepSeek-R1-Distill-Llama-8B | 1974 | 57.7 |
| GLM-4-9B-0414 | 1649 | 47.5 |
| Yi-1.5-9B-Chat | 1593 | 50.8 |

Raw-engine numbers, kept separate from the AIPerf end-to-end serving numbers.

### Startup (cold start, 3 repeats)

| Model | min (ms) | mean (ms) | max (ms) |
|---|---|---|---|
| Qwen3-8B | 4213 | 4740 | 5352 |
| DeepSeek-R1-Distill-Llama-8B | 4203 | 5382 | 6184 |
| GLM-4-9B-0414 | 4806 | 6114 | 7527 |
| Yi-1.5-9B-Chat | 4270 | 5327 | 7438 |

### Soak (600 s at 0.75 x capacity, c=8)

All four models ran 600 s without errors and without thermal throttle: GPU
~77 C, power ~81-85 W, 0% error rate.

### Open-loop (Poisson goodput, c=8)

Achieved throughput tracks the offered load up to ~90-100% then flattens;
no request errors at any load fraction.

### Sessions (multi-turn, 3 turns, cache on/off)

Per-turn TTFT p50 (ms): nocache 681-835 ms, cache 400-434 ms. `cache_prompt`
roughly halves per-turn TTFT.

## Reference baseline: Spark-X2.5-4B (IQ4_XS)

Spark-X2.5-4B (4.11B, IQ4_XS, XHToken fork) is a fixed-hardware cross-cohort
reference. It is **not ranked against the 8-9B cohort** (different parameter
count, serving fork, and quantization pipeline); it appears for
hardware-efficiency context.

### Capacity

| Concurrency | TTFT p50 (ms) | Output tok/s | Peak VRAM (MiB) |
|---|---|---|---|
| 1 | 114.7 | 66.3 | 2845 |
| 2 | 186.8 | 112.2 | 2847 |
| 4 | 2465.1 | 111.9 | 2847 |
| 6 | 4742.0 | 111.9 | 2847 |
| 8 | 7085.3 | 111.1 | 2847 |

Output throughput saturates ~112 tok/s at c>=2 (GPU-bound); higher concurrency
only adds queueing latency. IQ4_XS uses ~2847 MiB VRAM (the Q4_K_M historical
run used ~3045 MiB).

### Reliability

200/200 successful at c=1 and c=4, observed 100%, Wilson 95% CI
[98.12%, 100%], zero errors.

### Startup

Cold start 4.7 s (first) / ~2.9 s (warm).

### Soak

600 s at 0.75 x capacity: 0% error, peak ~78 C / ~86 W.

### Open-loop

Poisson 0.5-1.1 x capacity: 0% error, achieved goodput 0.42-0.82 req/s.

### Sessions

TTFT p50 582 ms nocache / 362 ms cache_prompt.

### Workload shape (transport limit)

ISL 128 profiles (`short_chat`, `generation`) PASS 60/60. At ISL >= 256 the
XHToken fork drops streaming connections: `balanced` (256) ~56/60,
`summarization` (512) ~42/60, `rag_medium` (768) TIMEOUT/UNSTABLE. This is a
property of the fork's HTTP server, not the quantization (the Q4_K_M run
showed the same limit). Affected cells are marked and excluded from ranking.

## Energy estimate

`gpu_energy_j` / `gpu_j_per_request` / `gpu_j_per_output_token` in the cell
telemetry are GPU-side estimates (integral of 500 ms `nvidia-smi` power
sampling). Not full-system energy, not MLPerf Power compliant.

## Reading the data

- `results/current/mainstream-8-9b/` — 8-9B cohort suites.
- `results/current/spark-reference/` — Spark reference suites.
- `results/history/spark-q4-km/` — historical Spark Q4_K_M run.
- Each suite dir: `aggregate.tsv` (mean + CI95), `repeats.tsv` (raw repeats),
  `manifest.json` (engine/image/flags/workload hash), plus `reliability.tsv`
  and `startup.tsv` where applicable.

Regenerate the dashboard with `make report`.
