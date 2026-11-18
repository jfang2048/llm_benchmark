# What runs well on a 6 GiB GPU?

**I'd leave Qwen3.5-2B running on this laptop.** It got 11 of 18 local jobs
right in every paired size trial. The 0.8B model got six. The 4B model also
got 11 and used almost twice the peak VRAM of the 2B.

The laptop is an RTX 3060 running Ubuntu 24.04 under Windows WSL2. The jobs
are the kind of things I'd rather keep on my own machine. We asked the models to pull a total
from a note, mask an identifier, or find a detail buried in an
archive. We used invented English and Chinese records and sent every
request to a local endpoint.

## A faster batch can make you wait longer

With the 2B model and two server slots, four clients pushed output from
**83 to 98 tokens/s**. The first visible reply at p95 took **750 ms**, up
from **194 ms** with one client. With the same half-second deadline, the
rate of correct, on-time jobs fell from **142 to 46 per minute**.

The paired test varied one setting at a time across 1,080 requests.
Reserving more context on the 2B cost **150 MiB** for the same short jobs.
Switching between two llama.cpp builds on the same Qwen3-4B weights gave
the same scores and peak VRAM. [Methods, figures and data](docs/controlled.md)

## What I'd run at home

In the wider 13-deployment scorecard, Qwen3-8B got **24 of 36** desk jobs
right and on time, compared with **22 of 36** for Qwen3.5-2B. I'd take the
2B for everyday use. It peaked at **1,753 MiB** versus **4,922 MiB** and
started its correct replies sooner. For masking known identifiers, I'd
keep a deterministic masking step. [The full scorecard](docs/home-lab-results.md)

Where the weights live mattered too. On the same WSL2 laptop, Phi-4-mini
was ready in **3.36 s** from the Linux filesystem and **22.85 s** from
the Windows mount, using medians of three pre-read launches per path.
[WSL2 test setup](docs/home-lab.md#wsl2-is-part-of-the-machine)

## Explore and reproduce

- [Interactive results](https://jfang2048.github.io/llm_benchmark/#home-lab) · [Paired trials](https://jfang2048.github.io/llm_benchmark/#controlled) · [中文说明](docs/zh/home-lab.md)
- [Start with one model](docs/home-lab.md#start-with-one-model) · [Replay the deployment scorecard](docs/home-lab.md#reproduce) · [Replay the paired tests](docs/controlled.md#5-data-and-reproduction)
- [Raw requests and GPU samples](results/current/controlled/) · [Serving sweeps](docs/results.md) · [Coding evaluations](docs/capability-results.md) · [Documentation index](docs/README.md)

Model weights are distributed by their publishers under the
[upstream licenses](docs/model-selection.md).
