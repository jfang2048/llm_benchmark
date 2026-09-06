# Engine and quantization

## Serving engine

All primary-cohort models are served by the **same llama.cpp binary**, built
from a single pinned Docker image (`docker/llama-cpp-upstream/Dockerfile`) from
upstream `ggml-org/llama.cpp`, with no fork patches.

- Upstream tag: `v0.4.0` (commit `5ac847190e979e0da7c4a21806630805f396d487`)
- CUDA arch: `86` (Ampere RTX 3060 Laptop)
- Image: `llama-cpp-upstream:v0.4.0`
- Built targets: `llama-server`, `llama-cli`, `llama-quantize`, `llama-bench`

This upstream release registers all four cohort architectures — `qwen3`,
`llama` (DeepSeek-R1-Distill-Llama-8B and Yi-1.5-9B), `glm4` — so one binary
serves the whole cohort.

The legacy 4B cohort used the XHToken/llama.cpp fork (Spark-X2.5 support). That
fork is retained only for historical 4B reproduction under `docker/llama-cpp/`.

## Quantization

The whole cohort uses a single common quantization: **IQ4_XS**, the smallest
"good" quant, which is what lets 8-9B models fit the 6 GiB envelope.

The GGUFs are pre-quantized IQ4_XS from a single uniform source (bartowski),
with SHA256 recorded per model in `configs/models.json`. IQ4_XS's importance
matrix affects generation quality, not the serving metrics this benchmark
measures (latency, throughput, VRAM), so the provenance choice does not bias
the ranking.

## Serving policy (identical across models)

```
--model /models/<file>.gguf --alias <name> \
  --host 0.0.0.0 --port 8000 \
  --ctx-size 4096 --parallel 2 --cont-batching --metrics --n-gpu-layers 999
```

`--n-gpu-layers 999` offloads every layer to the GPU. Admission confirmed the
whole cohort fits without CPU offload at this policy (peak 5.1 GiB for
GLM-4-9B). If any model required CPU offload, that would be recorded
explicitly and the comparison described as a fixed-hardware deployment
benchmark, not a pure architecture benchmark.

## Hardware constraint

The single GPU (RTX 3060 Laptop, 6 GiB VRAM) forces IQ4_XS and a 4096-token
serving context. The per-slot context (2048 tokens) is bounded by the 4096
total context shared across `--parallel 2`.
