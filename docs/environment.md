# Environment

Reproducibility environment for the current 8-9B benchmark. Hardware and
software values are captured from the machine and also encoded in each suite's
`results/current/<suite>/manifest.json`.

## Hardware

| Component | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 3060 Laptop GPU |
| VRAM | 6144 MiB (6 GiB) |
| GPU driver | 610.74 |
| CUDA | 13.3 |
| CPU | AMD Ryzen 7 6800H with Radeon Graphics (16 logical CPUs) |
| Platform | WSL2 (Ubuntu 24.04) |

## Software

| Component | Version |
|---|---|
| Docker | 29.7.2 |
| AIPerf | 0.12.0 |
| llama.cpp (8-9B) | ggml-org/llama.cpp, pinned tag `v0.4.0`, built against CUDA 13.3, arch 86 |
| llama.cpp (Spark) | XHToken llama.cpp fork, pinned commit (see `configs/models.json`) |
| Serving images | `llama-cpp-upstream:v0.4.0` (8-9B), `spark-x25-llama:cuda13` (Spark) |

Two engine profiles are pinned in `configs/models.json`:

- `upstream_llama_cpp` — mainstream 8-9B cohort.
- `xhtoken_llama_cpp` — Spark-X2.5-4B reference.

## Models (current cohort, IQ4_XS)

| Model | File | SHA256 |
|---|---|---|
| Qwen3-8B | `Qwen3-8B-IQ4_XS.gguf` | `0f69fe02…` |
| DeepSeek-R1-Distill-Llama-8B | `DeepSeek-R1-Distill-Llama-8B-IQ4_XS.gguf` | `a076a5f7…` |
| GLM-4-9B-0414 | `GLM-4-9B-0414-IQ4_XS.gguf` | `c85b661e…` |
| Yi-1.5-9B-Chat | `Yi-1.5-9B-Chat-IQ4_XS.gguf` | `acf00531…` |

### Reference model

| Model | File | SHA256 | Quantization |
|---|---|---|---|
| Spark-X2.5-4B | `Spark-X2.5-4B-IQ4_XS.gguf` | `e164454e…` | IQ4_XS |

Full SHA256 values and GGUF sources are in `configs/models.json`. The 8-9B
GGUFs are IQ4_XS artifacts from the same GGUF publisher (bartowski), each
pinned by SHA256; the Spark IQ4_XS is quantized locally from the official FP16
GGUF with the pinned XHToken fork.

## Serving configuration (llama.cpp)

All models run the identical command (only `--model` and `--alias` differ),
regardless of engine profile:

```
--model /models/<file>.gguf --alias <name> \
  --host 0.0.0.0 --port 8000 \
  --ctx-size 4096 --parallel 2 --cont-batching --metrics --n-gpu-layers 999
```

## Reproducing this environment

1. WSL2 + Ubuntu 24.04 with the NVIDIA Windows driver and the NVIDIA Container
   Toolkit inside the distro.
2. Docker with GPU passthrough (`docker run --rm --gpus all … nvidia-smi`).
3. `make setup` — builds both engine images (`scripts/build.sh`) and acquires
   the current models (`scripts/download_models.sh`: the four IQ4_XS GGUFs plus
   the Spark reference, quantized from the official FP16).
4. `make smoke` — runs `scripts/admit.sh`, the registry-driven admission gate
   for both cohorts (healthcheck, `/v1/models`, generation, 20-request smoke,
   VRAM/OOM).

Run `./scripts/preflight.sh` to validate a new machine against these
requirements.
