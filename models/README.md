# Model Weights

Model weight files are **not** stored in this repository. They are acquired
into this directory (git-ignored) and verified against pinned SHA256 values
recorded in `configs/models.json`.

## Current cohort (mainstream 8-9B, IQ4_XS)

All four GGUFs come from a single uniform source (bartowski) so no model is
served from a different quantization pipeline.

| Model | File | Source (HF repo) | SHA256 | Size (approx) |
|---|---|---|---|---|
| Qwen3-8B | `Qwen3-8B-IQ4_XS.gguf` | `bartowski/Qwen_Qwen3-8B-GGUF` | `0f69fe02ca9764c93bcc12ac96509bee53488114d6a7fe47764f80990c28751a` | ~4.3 GiB |
| DeepSeek-R1-Distill-Llama-8B | `DeepSeek-R1-Distill-Llama-8B-IQ4_XS.gguf` | `bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF` | `a076a5f7e48a054067d420c32740e1e63b425e1318a9a4eba89024906d67adcd` | ~4.1 GiB |
| GLM-4-9B-0414 | `GLM-4-9B-0414-IQ4_XS.gguf` | `bartowski/THUDM_GLM-4-9B-0414-GGUF` | `c85b661ed11c36f8b5a4f75da8bc1672b011febf8d71f098feab41186ad1767e` | ~4.9 GiB |
| Yi-1.5-9B-Chat | `Yi-1.5-9B-Chat-IQ4_XS.gguf` | `bartowski/Yi-1.5-9B-Chat-GGUF` | `acf005319fa455ea91f6c8954d5beb1a08138114ea0cb88be718cdbfc8b1c5ba` | ~4.5 GiB |

Acquire with `huggingface-cli` or `hf` (the exact filenames differ from the
local names above; rename after download):

```bash
# example: Qwen3-8B
huggingface-cli download bartowski/Qwen_Qwen3-8B-GGUF Qwen_Qwen3-8B-IQ4_XS.gguf --local-dir models/
mv models/Qwen_Qwen3-8B-IQ4_XS.gguf models/Qwen3-8B-IQ4_XS.gguf
```

A helper that downloads all four and verifies SHA256 is available in the
onboarding tooling (`.agent/download_ggufs.py`).

## Historical cohort (4B, Q4_K_M)

The legacy 4B cohort is preserved as historical data and is no longer the
primary cohort. Its weights were Qwen3-4B (official Qwen GGUF) and
Spark-X2.5-4B (XHToken fork, see below).

Spark-X2.5-4B has no single canonical public GGUF URL; obtain it by copying an
existing `Spark-X2.5-4B-Q4_K_M.gguf` and verifying against
`7934660bfc5b9bf04be0a0ac6179a1d16e1d4331b448857c86b8b2801b3ef72c`, or convert
from the official XHToken/Spark-X2.5-4B weights using the fork in
`docker/llama-cpp/`.

## License

Model weights are governed by their own upstream licenses (Qwen3 and Yi:
Apache-2.0; DeepSeek-R1-Distill-Llama-8B and GLM-4-9B: MIT). This repository
does not claim rights over them and does not redistribute them. `models/` and
its contents are git-ignored (`*.gguf`).
