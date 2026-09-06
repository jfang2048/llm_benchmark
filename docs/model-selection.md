# Model selection

The current primary cohort is size-controlled: dense, autoregressive,
text-generating models whose actual total parameter count is 8.0-9.4B, served
by the same pinned upstream llama.cpp binary at IQ4_XS, fitting the RTX 3060
Laptop (6 GiB VRAM), with a license that permits local evaluation and
recordable provenance.

Parameter counts are taken from official model cards / safetensors metadata,
not marketing names. All four models are MIT or Apache-2.0 and ungated.

| Model | Exact params | Architecture | Context (native) | License | Primary | Reason |
|---|---|---|---|---|---|---|
| Qwen3-8B | 8,190,735,360 | Dense GQA (qwen3) | 40,960 | Apache-2.0 | Yes | Mainstream 8B, permissive, native support |
| DeepSeek-R1-Distill-Llama-8B | 8,030,261,248 | Dense GQA (Llama 3.1 base) | 131,072 | MIT | Yes | Mainstream 8B distill, dense (not MoE) |
| GLM-4-9B-0414 | 9,400,279,040 | Dense GQA (glm4) | 131,072 | MIT | Yes | Mainstream 9B, native glm4 support |
| Yi-1.5-9B-Chat | 8,829,407,232 | Dense GQA (llama family) | 4,096 | Apache-2.0 | Yes | Mainstream 9B, llama arch |

## Notes on accuracy

- **DeepSeek-R1-Distill-Llama-8B** is a DeepSeek-distilled Llama-3.1-8B dense
  model. It is not the DeepSeek-R1/V3 Mixture-of-Experts architecture, and it
  is documented as such throughout the repository.
- **Yi-1.5-9B-Chat** has a 4K native context, shorter than its peers; it is
  still included because the fixed serving context (4096) is the binding
  constraint on this hardware for every model in the cohort.
- Exact GGUF SHA256 values are recorded in `configs/models.json`.

## Excluded

- **Meta-Llama-3.1-8B-Instruct** and **gemma-2-9b-it** were considered as
  optional arms but are gated on Hugging Face; gated models must not block
  progress, so they are not part of the primary ranking.
- Models substantially outside the 8-9B window (e.g. the legacy ~4B cohort,
  14B/32B/70B models) are not in the primary ranking. The legacy 4B cohort
  remains available as historical data.
