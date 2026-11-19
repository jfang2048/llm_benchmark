# What runs well on a 6 GiB GPU?

With 18 test cases, I'd have stopped at Qwen3.5-2B. On a larger test, I’d
give Qwen3.5-4B the everyday job. It got **69 of 96** new English and Chinese
tasks right and on time, compared with **56** for the 2B model. Peak VRAM
rose from **1,591 to 3,239 MiB** on the same RTX 3060 laptop under WSL2.

## An inbox is harder than a short note

The longer email tasks asked for complete records, with names, dates,
lists and nested fields in the right places. On 96 cases from HTW Berlin's
November 2026 LLMStructBench2 release, **Qwen3-8B got 61 right**. Qwen3.5-4B got
42 and Qwen3.5-2B got 26. The 8B peak was **4,891 MiB**. I'd spend the
extra memory on structured email extraction, and use the 4B for the mix
of shorter jobs tested here.

The two corpora test different work. We replayed **192 different cases on
each of 13 deployments**, giving 2,496 measured requests. The public dataset
was released after all the tested GGUF checkpoints were already available.
The second corpus contains new, invented notes, identifiers and archive
records, generated after the weights were published. [Methods, figures and data](docs/fresh.md)

## Explore and reproduce

- [Expanded results](https://jfang2048.github.io/llm_benchmark/#fresh) · [中文说明](docs/zh/home-lab.md) · [Raw request rows](results/current/fresh/)
- [Replay the expanded study](docs/fresh.md#5-data-and-reproduction) · [Start with one local model](docs/home-lab.md#start-with-one-model)
- [Single-factor tests](docs/controlled.md) cover size, client load, context and engine builds on the earlier short workload. [WSL2 storage check](docs/home-lab.md#wsl2-is-part-of-the-machine) covers load time from Linux and Windows paths.
- [Earlier deployment scorecard](docs/home-lab-results.md) · [Serving sweeps](docs/results.md) · [Coding evaluations](docs/capability-results.md) · [Documentation index](docs/README.md)

Model weights are distributed by their publishers under the
[upstream licenses](docs/model-selection.md).
