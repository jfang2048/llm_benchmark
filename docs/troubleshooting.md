# Home Lab troubleshooting

Find the failing stage first. Acquisition, model loading, prompt admission,
generation and scoring each leave different evidence.

| Symptom | First place to look |
|---|---|
| Download stalls or fails verification | Expected size, partial file, HTTP status and SHA-256 |
| Container exits before `/health` | Server log, exit state and free device memory |
| vLLM reports `UVA is not available` | Runner selection and WSL pinned-memory messages |
| The server rejects one long prompt | Tokenized input length and `n_ctx_slot` |
| The stream ends with `length` or empty visible text | Finish reason, usage and reasoning fields |
| JSON looks right but scores zero | Exact values, types, array order, duplicate keys and fences |
| Startup time is missing or implausible | Manifest field type and readiness probe |

## GGUF download stalls or checksum differs

**Observed.** Multi-gigabyte Hub downloads sometimes fell below 1 MB/s per
transfer. Interrupted downloads left staged `.part` files.

**Check.** Compare the final size and SHA-256 with the pinned artifact.
A byte-range download should return HTTP 206 and the exact `Content-Range`
for the offset and total size. A 200 carries the full representation.
A 403 on a cached signed URL calls for a fresh redirect from the pinned revision.

**Recover.** Re-run `scripts/download_models.sh MODEL_ID`, which resumes
staged downloads with curl when the Hub CLI is unavailable. For persistent
stalls, try the Hub CLI or a trusted alternate transfer route. Accept the
assembled artifact only when its SHA-256 matches the pinned source. In the model refresh, the Ollama
blob for Granite 4.1 matched IBM's Hub GGUF exactly. The Gemma and
Nemotron blobs are separately pinned quantizations with their own digests.
[Refresh artifact provenance](model-refresh.md#candidate-selection)

## The container exits before it becomes ready

Check host and container GPU visibility, then inspect the named service.

```bash
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv
docker run --rm --gpus all nvidia/cuda:13.3.1-base-ubuntu24.04 nvidia-smi
docker inspect --format '{{.State.ExitCode}} {{.State.OOMKilled}}' CONTAINER
docker logs --tail 100 CONTAINER
```

- If host GPU visibility works and the container probe fails, check the
  NVIDIA runtime configuration for Docker. [CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
- For an unknown architecture or missing tensor, verify the GGUF digest
  and serving build. A compatible image or conversion is a new configuration.
- For CUDA allocation failures, check device usage and the model, KV and
  compute buffers in the log. A userspace CUDA allocation error can occur
  with `OOMKilled=false`. Lower context, smaller quantization and CPU
  offload are options for a separate deployment configuration.
- When logs show continued progress, extend the readiness timeout.
  Check the registered port and health URL before judging a slow startup.

[llama.cpp server options](https://github.com/ggml-org/llama.cpp/blob/5ac847190e979e0da7c4a21806630805f396d487/tools/server/README.md)

## Startup is slow from a Windows mount

The same Phi-4-mini weight reached health in a median of 3.36 s on the
WSL Linux filesystem and 22.85 s on `/mnt/c`. Each path had three
pre-read launches. Keep frequently loaded weights on the Linux filesystem
and mount that directory into Docker. [Storage measurements](home-lab.md#wsl2-is-part-of-the-machine)

## vLLM exits with `UVA is not available`

**Observed.** vLLM 0.26.0 with the GGUF plugin failed on this WSL2 host
while initializing the V2 runner in `worker/gpu/buffer_utils.py`.

**Mechanism.** WSL2 limits pinned host memory. The V2 runner can request
a UVA-backed buffer when vLLM has disabled pinned-memory allocation.
[NVIDIA WSL limitations](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) · [vLLM issue #50239](https://github.com/vllm-project/vllm/issues/50239)

**Resolved on this host.** With the same Qwen3-4B Q4_K_M GGUF, the V2
runner passed the UVA stage after setting `VLLM_WSL2_ENABLE_PIN_MEMORY=1`
on the container. It reached health in 116.49 s and served an eight-token
completion. The earlier 90 s check stopped during initialization. A
240 s deadline allowed the verification to finish. Switching to the V1
runner also advanced to model loading within the 90 s check.

The successful smoke used a pinned local tokenizer, `--max-model-len 2048`,
`--max-num-seqs 2`, `--enforce-eager` and a 576 MiB explicit KV cache. The
environment switch applies to the observed WSL and driver stack. Treat
the result as a startup and completion smoke test. [Smoke record](../results/current/fresh-refresh/vllm-smoke.json)



## The prompt exceeds the slot context

**Observed.** Yi-1.5-9B encoded one invoice prompt as 2,096 tokens. Its
2,048-token slot rejected the request. The client classified the HTTP
failure as `transport_error`. The server log establishes the cause.
Ministral encountered the same limit on eight email prompts, with
tokenized inputs from 2,060 to 2,217 tokens.

**Check.** Read `n_ctx_slot` at startup. Count the input with the GGUF's
tokenizer and chat template, including the schema. Leave room for the reply.

**Recover.** Shorten the input or schema, raise total context, or use fewer
slots. Keep the original rejection in fixed-configuration results.
[Run audit](../results/current/fresh/audit.json) · [Context comparison](controlled.md)

## Generation reaches its limit before visible JSON

**Observed.** The first 192-case sweep recorded 255 `length` stops.
Some responses spent tokens on reasoning or repetition. Others reached
the context boundary. Older Spark replies could begin in
`reasoning_content` while visible `content` was empty.

**Check.** Compare `finish_reason`, token counts, first emitted token and
first visible answer. Compare input plus output against the slot size as
well as the output cap.

**Recover.** Try direct-answer mode where the model template supports it.
Adjust output or context budgets as their own test configuration. Timing
from the first emitted token and timing from visible content describe
two different waits.

## JSON looks right but the exact-match score is zero

A single Markdown fence, duplicate key, wrong array order, extra field
or numeric string can change the result. Replay the same parser with
the reference object and inspect the exact mismatch. In the refresh,
Ministral 3 3B scored zero under the raw format. One-fence parsing
recovered 46/96 public-case and 41/96 holdout-case exact matches. A deterministic
fence adapter or a structured decoding constraint can help in deployment.
Measure its effect under a fixed model and runtime. The expanded study
tracks fence recovery and the raw score separately.
[Scoring rules](fresh.md#3-outcomes-and-analysis)

## The log shows cached tokens with prompt reuse disabled

A pilot audit flagged nonzero cached-token messages during chunked
prefill. Later chunks can use state computed earlier within that request.
Group by task ID and inspect the first `cached n_tokens` message. The
published audit checks initial reuse under `--cache-ram 0` and
`cache_prompt=false`. [Paired cache policy](controlled.md#2-execution-and-instrumentation)

## Startup timing is missing from the first expanded sweep

The launch verifier reused the startup-time variable for the server log.
The original archive records null for that metadata field. Request and
window timers have distinct fields. The fix keeps the log and numeric
`startup_ms` separate. [Original manifest](../results/current/fresh/manifest.json)

## Streaming disconnects during historical AIPerf runs

Older shape cells reported `ServerDisconnectedError` at longer inputs.
Pooled keep-alive reuse and server behavior during long prefill were both
investigated. The runner now uses `--connection-reuse-strategy never`.
If the error persists, compare the server log and response error before
marking the cell unstable. [Serving results](results.md) · [Historical engine experiments](experiment-history.md)
