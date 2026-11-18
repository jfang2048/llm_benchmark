# The six-gigabyte test

A model card can tell you how a checkpoint scored on the publisher's test rig.
At home, the job is often a receipt total, an address to mask, or a detail
buried in a note you'd rather keep on your own computer. I wanted to know
which model I'd leave running on a laptop for jobs like those.

The laptop is an RTX 3060 with **6 GiB of VRAM**, running Ubuntu 24.04 under
Windows WSL2. Nine local deployments get the same English and Chinese notes,
planted identifiers, and archive lookups. Every benchmark request goes to a
local endpoint. We score each reply for correctness and how soon it arrives.

[Open the interactive results](https://jfang2048.github.io/llm_benchmark/#home-lab) ·
[中文说明](docs/zh/home-lab.md)

## Results

**For one person, I'd start with Qwen3-8B.** It returned 24/36 correct
replies on time. Its first visible answer p95 on correct replies was 460 ms.
It peaked at 4922 MiB.

**For small batches, Qwen3-4B edged ahead on raw JSON** at 98.0 usable jobs per
minute, alongside Qwen3-8B at 97.0. I'd take the 4B model for the extra
headroom. With one JSON code fence allowed, Phi-4-mini-instruct reached
112.6 usable jobs per minute.

**For more room on the card, try Qwen3-4B.** It delivered 20/36 on-time
replies at a peak of 3244 MiB. The single-user winner repeated planted
identifiers in 6 of 12 visible masking replies. For known identifiers, I'd
add a deterministic masking step.

| Deployment | Desk on time | Desk first-answer p95 (ms) | Batch usable/min | Peak VRAM (MiB) |
|---|---:|---:|---:|---:|
| Qwen3-8B | 24/36 | 460 | 97.0 | 4922 |
| Qwen3-4B | 20/36 | 291 | 98.0 | 3244 |
| Qwen3.5-4B (text-only) | 19/36 | 513 | 77.5 | 3270 |
| Phi-4-mini-instruct | 8/36 | 276 | 41.5 | 3158 |
| Yi-1.5-9B-Chat | 2/36 | 132 | 2.4 | 5124 |
| Spark-X2.5-4B | 0/36 | 2676 | 0.0 | 2926 |
| DeepSeek-R1-Distill-Llama-8B | 0/36 | 3129 | 0.0 | 4806 |
| Gemma 3 4B (text-only) | 0/36 | — | 0.0 | 3088 |
| GLM-4-9B-0414 | 0/36 | — | 0.0 | 5180 |

Phi-4-mini led the earlier 4B serving sweep at 128.9 output tok/s at
concurrency 2. It returned 8/36 correct raw replies at the desk. Accepting
one code fence brought that to 20/36. The same parser recovered useful
replies from Gemma and GLM.

[Per-task results and timings](docs/home-lab-results.md)

![Correct and timely replies for each deployment, with and without one code fence](docs/assets/figures/home-lab.svg)

## What makes a model worth running?

For one person, the target is a first visible answer within **500 ms** and a
finished reply within **5 seconds**. For a small batch with four requests in
flight, those limits are **2 seconds** and **8 seconds**. **Usable jobs per
minute** counts replies that meet both limits and get the task right. Peak
VRAM tells you how much of the 6 GiB card is still available.

The test uses 18 synthetic cases, two repeats per workload, and two
workloads per model. The starting score uses JSON exactly as returned.
The dashboard can accept one Markdown code fence from the same response so
you can see what a small parser changes. The older serving sweeps show how
the same machine behaves when it keeps generating tokens under load.
[Home Lab protocol](docs/home-lab.md) · [Serving results](docs/results.md)

## What changes under WSL2?

In a same-laptop check, Phi-4-mini reached health in a median of **3.36 s**
from the WSL Linux filesystem and **22.85 s** from the Windows mount. We
pre-read the same weight and launched it three times per path. Both paths
used the same WSL2 GPU and image. Native Linux would be a separate paired
test.
[Setup and measurement notes](docs/home-lab.md#wsl2-is-part-of-the-machine)

## Try it on your own machine

```bash
make setup-home
make benchmark-home RUN=.agent/home-local
make home-summary RUN=.agent/home-local
make report HOME_RUN=.agent/home-local
```

The model registry pins the weights and serving images. The benchmark binds
to loopback and uses public, invented records. Keep your model client,
logging, and any tools in mind before sending it private material.
[Start with one model](docs/home-lab.md#start-with-one-model) ·
[Reproduce the full test](docs/home-lab.md#reproduce) ·
[Model and weight sources](docs/model-selection.md)

## Follow the results

- [Home Lab details](docs/home-lab.md) explains the task set, the time budgets,
  the masking check, and the WSL2 test.
- [Serving results](docs/results.md) covers throughput, tail latency, memory,
  queueing, long inputs, and the short 4B sweep.
- [Coding results](docs/capability-results.md) covers separate correctness and
  software-engineering evaluations.
- [Published run files](results/current/home-lab/) hold request outcomes,
  timings, the synthetic cases, and machine and model metadata.
- [Documentation index](docs/README.md) links the rest of the project.

Model weights follow their upstream licenses. This repository publishes
measurements and fixtures. The weights come from their publishers.
