# Frontier references

Cited related work across the four areas this repository touches: inference
engines, KV-cache quantization, reasoning-model serving, and the agentic-coding
benchmark landscape. Sources are numbered and listed at the bottom.

## 1. Inference engines (llama.cpp / vLLM / SGLang)

Concurrency is the deciding factor when comparing serving engines. On dual H100
GPUs running DeepSeek-R1-Distill-Llama-8B, SGLang wins at low concurrency
(583 ms vs 2,141 ms TTFT at c=1, ~3.7x faster) while vLLM wins at high
concurrency (5,129 vs 4,638 tok/s peak, ~11% higher); SGLang also used ~47%
less GPU memory.[1] A larger independent A/B harness over 149 fair
head-to-head runs on matched host/model/workload gives vLLM 82% of decided
match-ups (119 vs 27 SGLang).[2]

For llama.cpp-family runtimes specifically, the runtime wrapper matters less
than the engine underneath: on identical sha256-verified GGUF bytes, llama.cpp
decodes 2-6% faster than Ollama, and Ollama vs LM Studio gaps are 5-11% — small,
measurable, and attributable to the runtime rather than the quantization.[3]
This is why this repository fixes the engine (llama.cpp) and only ever A/B-tests
vLLM as a disabled arm, to avoid conflating engine differences with model
differences.

## 2. KV-cache quantization for long context on small VRAM

The KV cache grows linearly with context length and dominates memory at long
contexts. llama.cpp quantizes K/V to Q8_0 / Q4_0 (etc.), trading a small
accuracy loss for substantially lower KV memory; a quantized V cache requires
flash attention.[9] The research line is stronger: KVQuant reaches 3-bit KV
quantization with <0.1 perplexity degradation and ~4.8x KV-memory reduction,
enabling 1M-token context for LLaMA-7B on a single A100-80GB.[10] On this
repository's 6 GiB GPU this is the practical lever for long agentic contexts —
the capability layer currently serves ctx 16384 without KV quantization and
records `kv_cache_policy: none` in the manifest.

## 3. Reasoning-model serving (thinking tokens)

llama.cpp can separate thinking from the final answer by placing it in a
`reasoning_content` field (via `--reasoning-format` / `--jinja`), so clients
don't parse per-model thinking delimiters.[11] DeepSeek-R1 support (including
tool calls) landed separately; the maintainers note that R1-Distill-8B "takes
liberties with its tool-call start tag" and may skip the tools output tag, so
8B (or lower) quants are discouraged for tool calling.[12] This repository
observed the same class of problem from the other direction: with
`--reasoning off`, R1-Distill-8B emits truncated thinking fragments
(`"\nWait,"`) and scores far below the other models on EvalPlus
(see [capability-troubleshooting.md](capability-troubleshooting.md)).

## 4. Agentic-coding benchmark landscape (2026)

The field is moving fast and several classic benchmarks are saturating or
retiring:

- **SWE-bench Verified is effectively retired.** OpenAI stopped reporting it in
  February 2026, citing an audit in which most consistently-failed problems had
  flawed tests, plus contamination — frontier models can reproduce gold patches
  and verbatim problem details.[4]
- **Terminal-Bench 2.1** (89 tasks) is saturating: top models are compressed
  into a 74-84% band, and a scaffold change alone moves a score by up to
  5.1 points — larger than the gap between the #1 and #3 models — so "a
  Terminal-Bench score with no version and no harness attached is not a
  fact."[4]
- **Frontier-Bench v0.1** (74 tasks across 7 domains) launched ~July 2026 with a
  top score of 34.4%, still wide open.[4]
- **DeepSWE**: 113 original long-horizon tasks authored from scratch across 91
  repos and 5 languages, graded by hand-written verifiers; an independent judge
  disagrees with its verifier ~1.4% of the time versus ~32.4% for SWE-bench
  Pro's inherited tests.[5] (This is the Datacurve benchmark this repository
  uses, distinct from the unrelated ~32B "DeepSWE-Preview" model.)
- **SWE-bench-Live**: 1,319 tasks from GitHub issues created since 2024 across
  93 repos, with automated environment construction (RepoLaunch) and
  contamination-resistance via release-date windowing.[6]
- **ProgramBench** is the least saturated of the widely-cited set: the top
  model resolves only ~4.5% fully (binary-to-source reconstruction); DeepSWE's
  leader sits ~74%; Senior SWE-bench ~35%.[7]
- Overall, SWE-bench Verified climbed from ~13% (early 2024) to ~78% (May 2026)
  — approaching saturation — and open-weight agents trail closed-API agents by
  25-40% on it.[8]

The takeaway for this repository: local 4-9B models are far below the frontier,
and local subsets of these benchmarks are explicitly labeled *Local-N* and are
not leaderboard-equivalent — they measure the local model + harness + context
policy, never a claim about frontier standing.

## Sources

[1] https://rawlinson.ca/articles/vllm-vs-sglang-performance-benchmark-h100 — vLLM vs SGLang benchmark (H100)
[2] https://vllm-sglang-dashboard.vercel.app — vLLM vs SGLang dashboard
[3] https://www.kaggle.com/datasets/lowellwoodiblessi/local-llm-runtime-comparison-rtx-5080/data — Ollama vs llama.cpp vs LM Studio (RTX 5080)
[4] https://backgrind.com/blog/agentic-coding-benchmarks-2026 — Agentic coding benchmarks 2026
[5] https://arxiv.org/html/2607.07946v1 — DeepSWE paper
[6] https://arxiv.org/html/2505.23419v2 — SWE-bench-Live paper
[7] https://peterindia.net/OpenSourceBenchmarksForAICodingAgents.html — Coding-agent benchmarks field guide 2026
[8] https://presenc.ai/research/coding-agent-benchmarks-2026 — Coding agent benchmarks 2026
[9] https://github.com/gravitee-io/llamaj.cpp/blob/main/docs/quantized-kv-cache/README.md — llama.cpp quantized KV cache
[10] https://arxiv.org/pdf/2401.18079v4 — KVQuant paper
[11] https://github.com/ggml-org/llama.cpp/discussions/15333 — llama.cpp thinking blocks
[12] https://github.com/ggml-org/llama.cpp/pull/11607 — llama.cpp DeepSeek-R1 reasoning_content
