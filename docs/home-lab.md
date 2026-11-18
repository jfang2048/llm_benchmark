# The Home Lab test

A notebook entry, a short masking job, and a decision buried in a long note
are good reasons to keep a model on the laptop. The useful response is the
one you can hand to the next local process. That calls for a simple contract,
a response budget, and a record of what the machine had to keep in memory.

## The two jobs we give the server

| Workload | Requests in flight | First visible answer | Complete reply |
|---|---:|---:|---:|
| One person | 1 | 500 ms | 5 s |
| Small batch | 4 | 2 s | 8 s |

These budgets are the choices for this project. A repeat submits the same
18 public synthetic cases in a seeded order, replenishing requests as they
finish. Each deployment does two repeats per workload. The workload order
alternates between repeats, one model runs at a time, and a short warm-up
precedes measurement. The server uses a 4096-token context, two slots,
temperature zero, up to 192 generated tokens, ordinary end-of-sequence
handling, and prompt caching disabled.

The cases cover structured extraction, exact masking of planted identifiers,
and lookup in a padded archive. Each category has three English and three
Chinese cases. Lookups place the target after 23 lines of unrelated records.
Each case asks for one JSON object. The checker compares keys, JSON types,
values, and exact masking text to the expected object. It rejects duplicate
keys. A second view accepts one fenced JSON block from the same reply. The
masking column counts visible replies that repeated at least one planted
identifier verbatim. JSON escaping, reformatting, and other forms of
disclosure fall outside that simple substring check.

The Qwen3, Qwen3.5 and SmolLM3 deployments use llama.cpp's direct-answer setting.
Other deployments keep their engine defaults. The upstream deployments use
their registered Q4_K_M or IQ4_XS weights. Spark uses the XHToken fork. This
compares deployable configurations on one card, including the model's
tokenizer and chat template.

[Full scorecard and task breakdown](home-lab-results.md) · [Lightweight deployments and VRAM checks](lightweight.md)

## How we read the results

| Measure | Meaning in this test |
|---|---|
| Correct | The visible reply passes the exact task contract. |
| Correct on time | The reply passes the contract and both limits in the selected workload. |
| Usable jobs/min | Correct on-time replies divided by the total elapsed batch windows, scaled to a minute. |
| First visible answer | Time from request dispatch to the first visible non-whitespace content, with engine-reported reasoning excluded. |
| First emitted token | Time to the first streamed content or reasoning chunk. |
| Completion | Time from dispatch until the streaming reply ends. |
| Output tokens/s | All server-reported output tokens divided by elapsed window time. A missing usage count leaves this metric blank. |
| Peak VRAM | The maximum device-level reading at readiness or during 500 ms sampling, in MiB. It includes other use of the device. |
| Startup | Elapsed time from Docker launch to a healthy endpoint, with the local model already on disk. |

Latency percentiles use correct replies; their sample count changes with
the correctness rate. At most 36 observations contribute to each workload's
p95. The 18 fixtures are repeated, so the counts describe this run and the
task set behind it. The short serving and long-run reliability suites add
different evidence about queueing, throughput and transport. [Serving
results](results.md)

The first-token/decode split follows the labels used by MLPerf Client.
The two time budgets borrow the goodput idea from AIPerf and DistServe, with
correctness added to suit the local task. The checker uses IFEval's idea of
verifiable instructions and a task set written for this repo. [MLPerf Client](https://mlcommons.org/benchmarks/client/) ·
[AIPerf goodput](https://docs.nvidia.com/aiperf/tutorials/metrics-analysis/benchmark-goodput-with-ai-perf) ·
[DistServe](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin) ·
[IFEval](https://arxiv.org/abs/2311.07911)

## WSL2 is part of the machine

The measured setup is Windows 11 (build 26300), Ubuntu 24.04 under WSL2, Docker, and an
RTX 3060 Laptop GPU with 6144 MiB. Weights and workloads sit on the WSL
Linux filesystem. NVIDIA's Windows driver exposes CUDA to the Linux guest.
The platform and driver string are stored with the run. Microsoft recommends
keeping Linux workloads on the Linux filesystem for the local I/O path.
[NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/) ·
[Microsoft WSL filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/setup/environment)

Use these figures as a WSL2 baseline. A native comparison would pair the
same physical card with the same GGUF, pinned llama.cpp build options, CUDA
version, power mode, context, and request list. Alternate platform runs and
record cold and warm startup, first answer, completion, and throughput
under both workloads. The current results measure WSL2 directly; a
native-Linux speed difference remains open.

### Same model, two storage paths

We copied the same Phi-4-mini GGUF to a Windows-mounted directory and
checked the SHA256 of both copies. That pre-read warmed the two paths.
Each row pairs one container launch per path. The second pair reverses
order. Both paths use the same WSL2 runtime, CUDA device and server flags.

| Trial | WSL Linux file ready (s) | Windows-mounted file ready (s) |
|---|---:|---:|
| 1 | 3.36 | 22.48 |
| 2 | 3.95 | 23.18 |
| 3 | 2.70 | 22.85 |

Median launch to health was 3.36 s from the Linux path (ext4)
and 22.85 s from the Windows mount (9p). Timing
starts at Docker launch and ends when the health endpoint is ready.
The median first short reply after readiness finished in 0.402 s from
the Linux path and 0.405 s from the Windows mount. The six starts and
their post-ready replies are in
[the storage probe](../results/current/home-lab/storage.json). Run
`python3 -m bench.home_storage LINUX_MODEL_DIR WINDOWS_MODEL_DIR`
with identical copies of the Phi GGUF for another comparison.

## Keep the workload local

The runner binds each server to host loopback and opens it from the WSL
client without a proxy. Start with the public fixtures. Point your own
client at the loopback endpoint and check its logging, history, and any
remote tools before feeding it private material. Keep personal prompts
and replies out of shared run artifacts. The published request TSV holds
IDs, timings, counters, and outcome codes. Raw experiment logs stay local.

## Start with one model

With the upstream image available, this starts the Qwen3-4B deployment from
the test. The port stays on loopback and the model directory is read-only.

```bash
./scripts/download_models.sh qwen3_4b_compact
docker run --rm --gpus all --ipc host -p 127.0.0.1:8220:8000 \
  -v "$PWD/models:/models:ro" --entrypoint /src/build/bin/llama-server \
  llama-cpp-upstream:v0.4.0 --model /models/Qwen3-4B-Q4_K_M.gguf \
  --alias local --host 0.0.0.0 --port 8000 --ctx-size 4096 --parallel 2 \
  --cont-batching --n-gpu-layers 999 --reasoning off
```

Point a local OpenAI-compatible client at `http://127.0.0.1:8220/v1` and
select the `local` alias. The [public cases](../configs/home_tasks.jsonl)
give you inputs to try first.

## Reproduce

```bash
make setup-home
make benchmark-home RUN=.agent/home-local
make home-summary RUN=.agent/home-local
make report HOME_RUN=.agent/home-local
```

Use a fresh output directory for a run. To check one model, pass its arm
to `python3 -m bench.home --model ARM --output .agent/home-single`. The
summary stage reads a run without a GPU. The dashboard generator reads
the curated run under [results/current/home-lab](../results/current/home-lab/).
The manifest records the corpus hash, settings, images, weights and
timed windows. The report rejects missing requests, extra requests and
duplicate rows.
