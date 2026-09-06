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
| llama.cpp | ggml-org/llama.cpp, pinned tag `v0.4.0`, built against CUDA 13.3, arch 86 |
| llama.cpp serving image | `llama-cpp-upstream:v0.4.0` |

## Models (current cohort, IQ4_XS)

| Model | File | SHA256 |
|---|---|---|
| Qwen3-8B | `Qwen3-8B-IQ4_XS.gguf` | `0f69fe02…` |
| DeepSeek-R1-Distill-Llama-8B | `DeepSeek-R1-Distill-Llama-8B-IQ4_XS.gguf` | `a076a5f7…` |
| GLM-4-9B-0414 | `GLM-4-9B-0414-IQ4_XS.gguf` | `c85b661e…` |
| Yi-1.5-9B-Chat | `Yi-1.5-9B-Chat-IQ4_XS.gguf` | `acf00531…` |

Full SHA256 values and GGUF sources are in `configs/models.json`. GGUFs come
from a single uniform source (bartowski, IQ4_XS).

## Serving configuration (llama.cpp)

All models run the identical command (only `--model` and `--alias` differ):

```
--model /models/<file>.gguf --alias <name> \
  --host 0.0.0.0 --port 8000 \
  --ctx-size 4096 --parallel 2 --cont-batching --metrics --n-gpu-layers 999
```

## Reproducing this environment

1. WSL2 + Ubuntu 24.04 with the NVIDIA Windows driver and the NVIDIA Container
   Toolkit inside the distro.
2. Docker with GPU passthrough (`docker run --rm --gpus all … nvidia-smi`).
3. Acquire the four IQ4_XS GGUFs into `models/` (see `models/README.md`).
4. Build the image:
   `docker build -t llama-cpp-upstream:v0.4.0 -f docker/llama-cpp-upstream/Dockerfile docker/llama-cpp-upstream/`
5. Run `./scripts/admit_8b9b.sh` to verify admission before benchmarking.

Run `./scripts/preflight.sh` to validate a new machine against these
requirements.
