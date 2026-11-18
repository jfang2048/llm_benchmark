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

## Reference model

- **Spark-X2.5-4B** (4.11B params, IQ4_XS, XHToken llama.cpp fork) is a
  fixed-hardware cross-cohort reference baseline. It is not part of the
  size-matched 8-9B ranking: it differs in parameter count, serving fork, and
  quantization. It is reported alongside the cohort for hardware-efficiency
  context and never compared as a size-matched winner.

## Compact 4B cohort

Four weights were measured on the pinned upstream llama.cpp image in
Q4_K_M. Qwen3-4B uses Qwen's official GGUF. Phi-4-mini-instruct and
[Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) use Bartowski's GGUFs,
and Gemma 3 4B uses the ggml-org text-only GGUF. The Qwen3.5 run loads the
text checkpoint without the vision projector.
Their exact source revisions and checksums are recorded in the registry.
See the [short capacity results](results.md#compact-4b-short-capacity).

## November 2026 model refresh

The registry includes three opt-in candidates. Their GGUF source revisions
and SHA256 values are pinned alongside the four published 8-9B artifacts.
On 2026-11-18, all five published models passed a short admission run
on the RTX 3060 Laptop GPU with context 4096, parallel 2, and three
requests per model. The three candidate artifacts were verified against
upstream metadata. Their GPU admission is pending a complete download.

| Candidate | Artifact | Selection rationale |
|---|---|---|
| [DeepSeek-R1-0528-Qwen3-8B](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B) | IQ4_XS | Newer DeepSeek reasoning distill with a Qwen3-8B Base backbone and a DeepSeek tokenizer |
| [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | IQ4_XS, text-only | Newer Qwen hybrid-attention architecture. The full upstream checkpoint has 9.65B parameters including vision, and the GGUF is 5.50 GB before runtime buffers. |
| [Spark-X2.6-4B](https://huggingface.co/XHToken/Spark-X2.6-4B) | Official Q4_K_M | Same 4.11B architecture as X2.5 with updated post-training. A same-quantization comparison with the IQ4_XS reference requires a separate IQ4_XS build. |

Use a model ID from the registry to download and test it individually.

```bash
./scripts/download_models.sh deepseek_r1_0528_qwen3_8b
SMOKE_REQS=3 OUT_LEN=32 ./scripts/admit.sh deepseek_r1_0528_qwen3_8b
```

The other candidate IDs are `qwen3_5_9b` and `spark_x2_6_4b`. The
admission script saves the latest run to `.agent/admission.tsv` and returns
a nonzero exit status if any selected model fails admission.

Qwen also released the larger [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B),
outside this benchmark's parameter window.

The historical small-model families also have newer releases, including
[Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B),
[Gemma 4 E4B](https://huggingface.co/google/gemma-4-E4B-it), and the
reasoning variant [Phi-4-mini-reasoning](https://huggingface.co/microsoft/Phi-4-mini-reasoning).
Z.ai's [GLM-4.6V-Flash](https://huggingface.co/zai-org/GLM-4.6V-Flash)
is a roughly 10B multimodal option. The [Yi catalog](https://huggingface.co/01-ai/models)
includes the task-specific Yi-Coder-9B-Chat and a longer-context Yi-1.5-9B
Chat variant.

## Excluded

- **Meta-Llama-3.1-8B-Instruct** and **gemma-2-9b-it** were considered as
  optional arms but are gated on Hugging Face; gated models must not block
  progress, so they are not part of the primary ranking.
- Models substantially outside the 8-9B window (14B/32B/70B, and the earlier
  ~4B cohort) are not in the primary ranking. The earlier 4B comparison
  remains available as historical data.
