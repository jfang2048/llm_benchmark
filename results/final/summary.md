# Benchmark Summary

- Run ID: `20260904_192416`
- Comparison: **Spark-X2.5-4B-Q4_K_M vs Qwen3-4B-Q4_K_M**
- Engine fixed: **llama.cpp** (same binary and serving flags for both arms)
- Quantization fixed: **Q4_K_M**
- GPU: `NVIDIA GeForce RTX 3060 Laptop GPU` (6144 MiB VRAM)
- Workload: identical raw-text prompts, identical order, `temperature=0`, `ignore_eos=true`, `cache_prompt=false`
- Per cell: 80 profiling requests, 5 warmup, 4 repeats, output cap 128 tokens
- Concurrency: 1, 2, 3, 4

## Headline results

| Concurrency | Spark req/s | Qwen req/s | Spark TTFT p50 (ms) | Qwen TTFT p50 (ms) | Spark error | Qwen error |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.492 | 0.576 | 112.6 | 90.7 | 3.8% | 4.7% |
| 2 | 0.781 | 0.426 | 187.8 | 172.8 | 10.6% | 4.1% |
| 3 | 0.932 | 0.589 | 239.1 | 215.7 | 16.6% | 10.6% |
| 4 | 1.024 | 1.290 | 287.0 | 270.5 | 12.5% | 5.3% |

See `model_comparison.md` for the full side-by-side tables and the interactive dashboard at `docs/index.html`.

