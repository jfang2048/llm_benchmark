# Engine and quantization

## Serving engine

All primary-cohort models are served by the **same llama.cpp binary**, built
from a single pinned Docker image (`docker/llama-cpp/Dockerfile`).

The binary is built from the [XHToken/llama.cpp](https://github.com/XHToken/llama.cpp)
fork, which adds Spark-X2.5 architecture support that upstream llama.cpp does
not yet provide. The pinned fork's `src/models/models.h` registers all
primary-cohort architectures — `qwen3`, `spark2_5`, `gemma3`, `phi3`
(Phi-4), `minicpm3`, `nemotron` — so a single binary serves every candidate.

### Fork state (pinned)

- Fork commit: `4a3635c32fc9f044c2bde9ebeabf50c7e1ec5991` (2026-09-04)
- Upstream parent: `ggml-org/llama.cpp`
- Divergence: **15 commits ahead**, **321 commits behind** upstream master
  (fork base commit `6d05498314db1b57f81c271080018aa2d0b89be9`)

The 15 fork commits add, in a focused way:

| Area | Files |
|---|---|
| Model architecture | `src/models/spark2_5.cpp`, `src/models/models.h`, `src/llama-arch.cpp/.h`, `src/llama-model.cpp`, `src/llama-model-saver.cpp` |
| Tokenizer / vocab | `src/llama-vocab.cpp/.h` |
| GGUF conversion | `conversion/spark2_5.py`, `conversion/base.py`, `convert_hf_to_gguf_update.py`, `gguf-py/gguf/constants.py` |
| Chat template | `models/templates/Spark2.5.jinja` |
| Function-calling parser | `src/llama-model.cpp`, `docs/autoparser.md` |

### Rebase plan (follow-up)

The Spark patch is small and mostly additive, so it is a candidate for a
minimal patch on a recent upstream commit. This is the preferred long-term
approach but is not yet done: it requires forward-porting the ~18-file patch
across 321 commits of upstream changes to the arch/vocab/conversion code and
rebuilding/re-testing both arms. Until that lands, the pinned fork is the
single source for all arms — no model is served by a different llama.cpp build.

## Quantization recipe

The target is a single, reproducible quantization path for every primary model:

```
official FP16/BF16 checkpoint
  -> pinned convert_hf_to_gguf.py   (same commit as the server)
  -> pinned llama-quantize          (same commit)
  -> Q4_K_M
  -> record SHA256
```

Third-party / official pre-quantized GGUFs are used only for onboarding smoke
tests, not for the final ranking, unless their provenance is demonstrably
equivalent to the recipe above.

Current status: Qwen3-4B is served from the official Qwen GGUF
(`Qwen/Qwen3-4B-GGUF`, Q4_K_M); Spark-X2.5-4B from a locally converted Q4_K_M.
Both SHA256s are pinned in `configs/models.json`. New models are re-quantized
through the recipe above during onboarding.

## Hardware constraint

The single GPU (RTX 3060 Laptop, 6 GiB VRAM) forces Q4_K_M. It also bounds the
per-slot context: the server runs `--ctx-size 9216 --parallel 4` with a
non-unified KV cache, i.e. 2304 tokens per slot.
