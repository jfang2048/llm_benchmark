# Change one thing on a 6 GiB GPU

The Home Lab scorecard compares complete deployments and shows what worked
on this laptop. These five follow-up comparisons change one setting per
pair and replay the same jobs. The laptop stays in WSL2 for every run.

| Change | Settings held steady |
|---|---|
| Qwen3.5-0.8B → 2B | Qwen3.5 text-only family, Bartowski Q4_K_M, upstream llama.cpp, one client, 4,096 total context |
| Qwen3.5-2B → 4B | Same controls as the 0.8B → 2B comparison |
| Context 4,096 → 16,384 | Same Qwen3.5-2B GGUF, upstream llama.cpp, one client and two slots |
| One client → four clients | Same Qwen3.5-2B GGUF, upstream llama.cpp, 4,096 total context and two slots |
| Upstream → XHToken llama.cpp | Same Qwen3-4B Q4_K_M file, one client, 4,096 total context and two slots |

A model-size change here means switching to another checkpoint in the same
family. Each checkpoint brings its own architecture and training. The two
engine builds share a CUDA 13.3.1 base and use identical launch flags.
The engine comparison includes each build's chat formatting, GPU kernels
and scheduling. Both builds reported the same input and output token counts
and the same scoring outcome for each of the 108 matched requests.

## What changed

Correct and on-time counts show the median of six runs per arm, out of 18
tasks per run. The delta columns show the median of six B−A differences
with the observed low and high in brackets.

| Change | Correct A → B | On time A → B | First visible p95 Δ (ms) | Usable jobs/min Δ | Peak VRAM Δ (MiB) |
|---|---:|---:|---:|---:|---:|
| Qwen3.5-0.8B → 2B | 6.0 → 11.0 | 6.0 → 11.0 | +57.2 [+45.8, +60.0] | +41.6 [+38.7, +48.5] | +744.0 [+744.0, +744.0] |
| Qwen3.5-2B → 4B | 11.0 → 11.0 | 11.0 → 11.0 | +246.1 [+233.0, +267.6] | -60.1 [-69.0, -56.8] | +1648.0 [+1648.0, +1648.0] |
| Context 4,096 → 16,384 | 11.0 → 11.0 | 11.0 → 11.0 | +0.6 [-0.5, +15.4] | -0.8 [-2.2, +6.5] | +150.0 [+150.0, +150.0] |
| One → four clients | 11.0 → 11.0 | 11.0 → 3.0 | +556.0 [+540.5, +645.8] | -95.7 [-126.9, -65.6] | +0.0 [+0.0, +0.0] |
| Upstream → XHToken llama.cpp | 10.0 → 10.0 | 10.0 → 10.0 | +1.5 [-3.3, +3.4] | -0.2 [-1.1, +0.8] | +0.0 [+0.0, +0.0] |

1,080 measured requests ran across 60 launches, with
0 transport errors. The four-client result has
the same 500 ms and 5 s targets as the one-client result. The 13-deployment
scorecard gave its four-client batch more time, which answers a different
question about work you can leave running in the background.

## How the runs were matched

Each comparison has six pairs. A runs first in pairs 1, 3 and 5. B runs first
in pairs 2, 4 and 6. Both sides of a pair get the same seeded shuffle of the
18 English and Chinese fixtures. Each arm starts a fresh container after the
GPU reaches 60 °C or cooler. It does two warm-up requests, one short and one
archive lookup, before the timed workload. Only one benchmark server runs
at a time. The manifest records device VRAM and temperature before each launch.

The shared settings include two server slots, F16 key and value caches,
greedy decoding, reasoning disabled, 192 output tokens at most, and a
30-second client timeout. Every launch checks full GPU layer offload and the
expected context allocation per slot. Server prompt cache storage is off.
The client also sends `cache_prompt=false`. The runner verifies that
every warm-up and measured request starts with zero cached prompt tokens.

Four closed-loop clients can submit up to four requests while the server
has two slots. Client latency includes the queue. Each arm keeps the same
first-answer target of 500 ms and completion target of 5 seconds. This
gives the concurrency comparison a fixed definition of an on-time job.

## How to read the numbers

- **Correct** means strict JSON matching on the defined fields, values and
  types. **On time** adds both client-side deadlines. **Usable jobs/minute**
  divides the on-time count by the time to dispatch and finish the whole
  measured batch. **Output tokens/s** uses that same window and counts every
  completed reply with usage.
- Both latency percentiles use completed streams. First visible answer p95
  also requires visible text. End-to-end p95 includes the full stream. The
  deployment scorecard's latency columns use correct replies, so compare
  numbers within each view.
- **Peak VRAM** is the larger of device-wide VRAM at readiness and the
  largest 500 ms sample during warm-up and the workload. The paired
  dashboard also shows peak minus the pre-launch reading, which includes
  the server and any change in background usage. A brief spike between
  samples may escape the probe.
- Each arm's p95 is calculated on one run of 18 cases. The comparison
  subtracts A from B within each pair, then reports the median and observed
  range of those six changes. Each point in the chart is one paired change.
  The range describes these six trials. The same 18 cases repeat across
  runs, so the total request count does not enlarge the set of tasks.
- The context test tells us the cost of reserving more room while serving
  the same short jobs. The longest inputs in this suite are the archive
  lookups. Throughput at a filled 8,192-token slot needs a workload designed
  for that length.

The warm-up and repeat policy follows the measurement principles in the
[pyperf run guide](https://github.com/psf/pyperf/blob/main/doc/run_benchmark.rst).
The Home Lab protocol defines the [tasks and strict scoring](home-lab.md).

## Engine launch outside the matched trials

A vLLM 0.26.0 GGUF preflight with the same Qwen3-4B file failed during worker
initialization with `RuntimeError: UVA is not available`. That run used the
locally built GGUF plugin image, an eager runner, a 2,048-token maximum per
sequence and two sequences. It yielded a startup outcome only. The paired
engine results cover the two llama.cpp builds named above.

## Replay

From the repository root on a Docker host with a CUDA GPU:

```bash
./scripts/build.sh
./scripts/download_models.sh qwen3_5_08b_light qwen3_5_2b_light qwen3_5_4b_compact qwen3_4b_compact
python3 -m bench.controlled --output .agent/controlled-local
python3 -m bench.controlled_report .agent/controlled-local
```

[Experiment settings](../configs/controlled.json) ·
[Request rows, launch manifest and raw GPU samples](../results/current/controlled/) ·
[Interactive paired results](https://jfang2048.github.io/llm_benchmark/#controlled)
