# Spark-X2.5-4B vs Qwen3-4B — Model Benchmark

- Run ID: `20260904_192416`
- GPU: `NVIDIA GeForce RTX 3060 Laptop GPU`, driver `610.74`, 6144 MiB VRAM
- AIPerf profiling requests per cell: **80**; warmup: **5**; repeats: **4**; output cap: **128 tokens**
- Concurrency: **1 2 3 4**; engine fixed: **llama.cpp**; quantization fixed: **Q4_K_M**
- Workload fixed: identical raw-text prompts, identical order, `temperature=0`, `ignore_eos=true`, `cache_prompt=false`
- Independent variable: **model** (checkpoint/architecture/tokenizer treated as the model package)
- Spark GGUF SHA256: `7934660bfc5b9bf04be0a0ac6179a1d16e1d4331b448857c86b8b2801b3ef72c`
- Qwen GGUF SHA256: `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`

## Run validity

| Concurrency | Spark PASS / total | Qwen PASS / total | Spark mean error | Qwen mean error |
|---:|---:|---:|---:|---:|
| 1 | 4/4 | 4/4 | 3.75% | 4.69% |
| 2 | 4/4 | 4/4 | 10.62% | 4.06% |
| 3 | 4/4 | 4/4 | 16.56% | 10.62% |
| 4 | 4/4 | 4/4 | 12.50% | 5.31% |

## Side-by-side results

Values are mean ± 95% CI across successfully parsed repeats (PASS + UNSTABLE). `Δ Qwen vs Spark` is positive when Qwen is better for that metric.

### Concurrency 1

| Metric | Spark | Qwen | Δ Qwen vs Spark | Winner |
|---|---:|---:|---:|---|
| Error rate | 3.75 ± 2.81 | 4.69 ± 1.90 | -25.0% | Spark |
| TTFT p50 | 112.58 ± 2.75 | 90.69 ± 1.07 | +19.4% | Qwen |
| TTFT p95 | 132.00 ± 13.86 | 110.47 ± 6.08 | +16.3% | Qwen |
| Inter-token latency p50 | 14.97 ± 0.04 | 12.82 ± 0.01 | +14.3% | Qwen |
| Inter-token latency p95 | 15.23 ± 0.11 | 12.95 ± 0.04 | +15.0% | Qwen |
| E2E latency p50 | 2016.41 ± 5.33 | 1721.30 ± 2.95 | +14.6% | Qwen |
| E2E latency p95 | 2056.27 ± 14.50 | 1743.95 ± 8.85 | +15.2% | Qwen |
| Request throughput | 0.492 ± 0.003 | 0.576 ± 0.001 | +17.1% | Qwen |
| Output token throughput | 62.971 ± 0.381 | 73.718 ± 0.062 | +17.1% | Qwen |
| Peak VRAM | 3439.00 ± 0.00 | 3881.00 ± 0.00 | -12.9% | Spark |
| Peak power | 91.82 ± 8.58 | 95.66 ± 10.84 | -4.2% | Spark |

### Concurrency 2

| Metric | Spark | Qwen | Δ Qwen vs Spark | Winner |
|---|---:|---:|---:|---|
| Error rate | 10.62 ± 7.35 | 4.06 ± 3.76 | +61.8% | Qwen |
| TTFT p50 | 187.79 ± 2.85 | 172.82 ± 4.45 | +8.0% | Qwen |
| TTFT p95 | 219.81 ± 15.22 | 203.81 ± 9.91 | +7.3% | Qwen |
| Inter-token latency p50 | 18.36 ± 0.88 | 35.33 ± 0.46 | -92.5% | Spark |
| Inter-token latency p95 | 19.14 ± 0.52 | 37.85 ± 1.21 | -97.8% | Spark |
| E2E latency p50 | 2520.38 ± 105.40 | 4658.30 ± 55.62 | -84.8% | Spark |
| E2E latency p95 | 2621.31 ± 76.77 | 4992.30 ± 154.80 | -90.5% | Spark |
| Request throughput | 0.781 ± 0.028 | 0.426 ± 0.007 | -45.4% | Spark |
| Output token throughput | 99.946 ± 3.551 | 54.545 ± 0.887 | -45.4% | Spark |
| Peak VRAM | 3441.00 ± 0.00 | 3885.00 ± 0.00 | -12.9% | Spark |
| Peak power | 93.84 ± 11.81 | 95.03 ± 9.10 | -1.3% | Spark |

### Concurrency 3

| Metric | Spark | Qwen | Δ Qwen vs Spark | Winner |
|---|---:|---:|---:|---|
| Error rate | 16.56 ± 13.62 | 10.62 ± 6.18 | +35.8% | Qwen |
| TTFT p50 | 239.08 ± 27.81 | 215.68 ± 26.31 | +9.8% | Qwen |
| TTFT p95 | 276.13 ± 16.40 | 256.83 ± 25.89 | +7.0% | Qwen |
| Inter-token latency p50 | 22.66 ± 0.55 | 37.86 ± 0.19 | -67.1% | Spark |
| Inter-token latency p95 | 24.09 ± 0.79 | 40.53 ± 0.31 | -68.3% | Spark |
| E2E latency p50 | 3120.82 ± 62.83 | 5023.02 ± 38.11 | -61.0% | Spark |
| E2E latency p95 | 3259.25 ± 94.17 | 5352.28 ± 50.49 | -64.2% | Spark |
| Request throughput | 0.932 ± 0.030 | 0.589 ± 0.006 | -36.8% | Spark |
| Output token throughput | 119.251 ± 3.801 | 75.386 ± 0.781 | -36.8% | Spark |
| Peak VRAM | 3441.00 ± 0.00 | 3885.00 ± 0.00 | -12.9% | Spark |
| Peak power | 106.97 ± 14.67 | 98.39 ± 6.69 | +8.0% | Qwen |

### Concurrency 4

| Metric | Spark | Qwen | Δ Qwen vs Spark | Winner |
|---|---:|---:|---:|---|
| Error rate | 12.50 ± 15.99 | 5.31 ± 6.16 | +57.5% | Qwen |
| TTFT p50 | 287.02 ± 36.80 | 270.51 ± 12.94 | +5.8% | Qwen |
| TTFT p95 | 353.15 ± 26.55 | 300.60 ± 12.97 | +14.9% | Qwen |
| Inter-token latency p50 | 27.66 ± 1.12 | 22.01 ± 0.21 | +20.4% | Qwen |
| Inter-token latency p95 | 29.77 ± 2.67 | 22.67 ± 0.96 | +23.9% | Qwen |
| E2E latency p50 | 3824.40 ± 105.84 | 3065.82 ± 27.20 | +19.8% | Qwen |
| E2E latency p95 | 4056.20 ± 288.18 | 3131.49 ± 40.78 | +22.8% | Qwen |
| Request throughput | 1.024 ± 0.049 | 1.290 ± 0.030 | +26.0% | Qwen |
| Output token throughput | 131.135 ± 6.242 | 165.173 ± 3.862 | +26.0% | Qwen |
| Peak VRAM | 3441.00 ± 0.00 | 3885.00 ± 0.00 | -12.9% | Spark |
| Peak power | 103.01 ± 11.18 | 88.11 ± 9.67 | +14.5% | Qwen |

## Interpretation notes

- Treat **error rate as a hard gate**: a faster arm with materially higher request failures is not the better serving result.
- For interactive use, prioritize **TTFT p95** and **E2E p95**; for saturation behavior, prioritize **request throughput** together with error rate.
- `Output token throughput` is secondary across different models because their tokenizers differ; request-level latency/throughput is more directly comparable under identical raw prompts.
- Peak VRAM and power are efficiency metrics, not quality metrics; do not merge them into latency/throughput without an explicit weighting policy.

