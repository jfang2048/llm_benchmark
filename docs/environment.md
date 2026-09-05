# Environment

Reproducibility environment for the published benchmark (run `20260904_192416`).
These values were captured from the machine and the run artifacts; they are
also encoded in `results/final/provenance.json`.

## Hardware

| Component | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 3060 Laptop GPU |
| VRAM | 6144 MiB (6 GiB) |
| GPU driver | 610.74 |
| CUDA (UMD) | 13.3 |
| CPU | AMD Ryzen 7 6800H with Radeon Graphics (16 logical CPUs) |
| Platform | WSL2 (Ubuntu 24.04), kernel `6.18.33.2-microsoft-standard-WSL2` |

## Software

| Component | Version |
|---|---|
| Docker | 29.7.2 |
| Docker Compose | v5.4.0 |
| AIPerf | 0.12.0 |
| llama.cpp | XHToken fork (`github.com/XHToken/llama.cpp`), built against CUDA 13.3.1, arch 86 |
| llama.cpp serving image | `spark-x25-llama:cuda13` (digest `sha256:28f81be4…`) |
| vLLM | 0.26.0 (`vllm/vllm-openai:v0.26.0`) — engine-comparison context |
| vLLM GGUF plugin | 0.0.4 |

## Models

| Model | Quantization | File | SHA256 |
|---|---|---|---|
| Spark-X2.5-4B | Q4_K_M | `Spark-X2.5-4B-Q4_K_M.gguf` | `7934660b…` |
| Qwen3-4B | Q4_K_M | `Qwen3-4B-Q4_K_M.gguf` | `7485fe6f…` |

Spark-X2.5-4B metadata (from the llama.cpp `/models` endpoint): 4,112,079,360
parameters, Q4_K - Medium ftype, 131,072 vocab, trained context 1,048,576.

## Serving configuration (llama.cpp)

Both arms ran the identical command (only `--model` and `--alias` differ):

```
--model /bench-models/<file>.gguf --alias <name> \
  --host 0.0.0.0 --port 8000 \
  --ctx-size 9216 --parallel 4 --cont-batching --metrics --n-gpu-layers 999
```

## Reproducing this environment

1. WSL2 + Ubuntu 24.04 with the NVIDIA Windows driver and the NVIDIA Container
   Toolkit inside the distro.
2. Docker with GPU passthrough (`docker run --rm --gpus all … nvidia-smi`).
3. `make setup` to download models and build the llama.cpp image.

Run `./scripts/preflight.sh` to validate a new machine against these
requirements before benchmarking.
