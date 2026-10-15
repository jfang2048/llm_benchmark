# Documentation

This repository runs two independent evaluation layers. They are never merged
into one score.

## 1. Serving benchmark (fixed-hardware inference)

Measures serving performance under one GPU / engine / quantization policy:
latency, throughput, VRAM, reliability.

| Doc | What it covers |
|---|---|
| [methodology.md](methodology.md) | How the serving benchmark works: workload, fairness views, metrics. |
| [results.md](results.md) | Measured serving results (capacity, reliability, shape, open-loop). |
| [engine.md](engine.md) | Engine setup: upstream llama.cpp v0.4.0 vs the XHToken fork. |
| [environment.md](environment.md) | Hardware/software environment and reproducibility. |
| [model-selection.md](model-selection.md) | Why these models; size-controlled cohort rationale. |
| [experiment-history.md](experiment-history.md) | Earlier cohorts and the engine A/B (llama.cpp vs vLLM) work. |
| [troubleshooting.md](troubleshooting.md) | Serving failure modes observed in practice. |

## 2. Coding / software-engineering capability

Measures model coding ability, split into direct coding and agentic SWE.

| Doc | What it covers |
|---|---|
| [capability-methodology.md](capability-methodology.md) | How capability is measured, served, and normalized. |
| [capability-results.md](capability-results.md) | Capability results (EvalPlus, admission, SWE). |
| [benchmark-selection.md](benchmark-selection.md) | Which benchmarks and why; what each measures. |
| [capability-troubleshooting.md](capability-troubleshooting.md) | Capability problems + solutions (P0-P18 + implementation fixes). |

## Cross-cutting

| Doc | What it covers |
|---|---|
| [architecture.md](architecture.md) | Repository structure and how the layers fit together. |
| [references.md](references.md) | Frontier related work: inference engines, KV-cache quantization, reasoning-model serving, agentic-coding benchmark landscape (cited). |

## 中文文档 (Chinese)

| Doc | 内容 |
|---|---|
| [zh/problems-and-solutions.md](zh/problems-and-solutions.md) | 问题与解决方法总结（设计问题 + 实现问题 + 为什么）。 |
| [zh/results-analysis.md](zh/results-analysis.md) | 结果分析：模型差异、原因、推理框架对比、前沿调研。 |
