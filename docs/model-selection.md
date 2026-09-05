# Model selection

The primary benchmark cohort is size-controlled: dense, autoregressive,
text-generating models whose actual total parameter count is 3.8–4.2B (±5% of
4B), served by the same pinned llama.cpp binary at Q4_K_M, fitting the RTX 3060
Laptop (6 GiB VRAM), with a license that permits local evaluation and recordable
provenance.

Parameter counts below are taken from official model cards / technical reports,
not marketing names. Exact counts are re-verified from checkpoint metadata
(`config.json` / GGUF) during onboarding (Phase G).

| Model | Exact params | Architecture | Context | License | llama.cpp | Primary? | Reason |
|---|---|---|---|---|---|---|---|
| Qwen3-4B | 4.0B (3.6B non-emb) | Dense, GQA | 32K native / 128K YaRN | Apache-2.0 | native | Yes | Verified 4.0B, permissive license |
| Spark-X2.5-4B | 4B | Dense, hybrid attention (1 full + 3 sliding-window) | 1M native | verify (custom) | needs XHToken fork | Yes | Already onboarded; custom arch |
| Gemma 3 4B | ~3.9B text (4B incl. 417M vision enc.) | Dense, GQA, 5:1 local/global | 128K | Gemma Terms of Use | native | Yes | Text-only; skip vision projector |
| Phi-4-mini-instruct | 3.8B | Dense, GQA | 128K | MIT | native | Yes | Verified 3.8B, MIT |
| MiniCPM3-4B | 4B | Dense (custom, trust_remote_code) | 32K | MiniCPM Model License | partial | Borderline | Commercial use needs registration |
| Nemotron-Mini-4B-Instruct | 4B (Minitron, pruned from 15B) | Dense, Llama-3 arch | 4K | NVIDIA Community Model License | native | Borderline | 4K context is short vs peers |
| GLM-4-9B-0414 | 9B | Dense | 128K | Apache-2.0 | native | No | 9B > 4.2B |
| DeepSeek-R1-Distill-* | 1.5B / 7B / 8B / 14B / 32B / 70B | Dense (Qwen2.5/Llama bases) | 32K | MIT (Qwen: Apache-2.0; Llama: Llama) | native | No | No 4B size in the family |
| DeepSeek-V2-Lite | 15.7B total / 2.4B active | MoE | 32K | MIT | partial | No | MoE, not dense 4B |

## Conclusions

- **GLM**: the current open GLM-4 model is 9B (GLM-4-9B), outside the 4B
  cohort. Excluded on size.
- **DeepSeek**: R1 distill sizes are 1.5B / 7B / 8B (and larger), none at 4B.
  DeepSeek-V2-Lite is a MoE (15.7B total / 2.4B active), not a dense 4B.
  Excluded.

## Candidate primary cohort

The solid primary cohort is four models:

1. **Qwen3-4B** — 4.0B, Apache-2.0, native llama.cpp.
2. **Spark-X2.5-4B** — 4B, custom arch, XHToken fork (already onboarded).
3. **Gemma 3 4B** — text-only (~3.9B), Gemma Terms of Use, native llama.cpp.
4. **Phi-4-mini-instruct** — 3.8B, MIT, native llama.cpp.

Two additional candidates are recorded as borderline:

- **MiniCPM3-4B** — license requires a registration questionnaire for
  commercial use; architecture needs `trust_remote_code`.
- **Nemotron-Mini-4B-Instruct** — 4K context is short relative to the peers.

The exact GGUF parameter count served for each model is recorded during
onboarding (Phase G); the cohort is finalized only after the common-engine and
quantization normalization (Phase E).
