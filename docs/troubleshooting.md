# Troubleshooting

Real failure modes observed while running this benchmark, distilled from the
experiment logs. Each entry lists symptom, cause, verification, and fix.

## 1. `ServerDisconnectedError` during the benchmark

**Symptom** — AIPerf reports a nonzero error rate; the classified error output
shows `ServerDisconnectedError` for a fraction of requests.

**Cause** — The llama.cpp server drops in-flight streaming connections under
load; AIPerf's default pooled connection reuse races with the server closing
keep-alive connections.

**Verification** — Inspect `server.log` in the cell directory and the error
types in the reliability summary.

**Fix** — Run every request with `--connection-reuse-strategy never` (the
runner does this by default). A cell that still fails is reported as
`UNSTABLE` and is not presented as a ranking point.

## 2. Container starts but never becomes API-ready

**Symptom** — `admit.sh` or the runner logs that the container never
became ready.

**Cause** — Model load exceeds VRAM (OOM at startup), the GGUF path is wrong,
or the model is still loading past `STARTUP_TIMEOUT`.

**Verification** — `docker logs --tail 200 <container>`; look for OOM / CUDA
allocation errors. `docker inspect -f '{{.State.OOMKilled}}' <container>`.

**Fix** — Confirm the model file exists and matches its SHA256 (see
`models/README.md` and `configs/models.json`), free VRAM (stop other GPU
containers), or reduce `--ctx-size` / `--n-gpu-layers`.

## 3. GPU passthrough fails

**Symptom** — `docker run --gpus all … nvidia-smi` errors with "could not
select device driver … unknown capability gpu".

**Cause** — NVIDIA Container Toolkit not installed/enabled in the WSL2 distro.

**Verification** — `./scripts/preflight.sh` reports
`[WARN] docker GPU passthrough failed`.

**Fix** — Install `nvidia-container-toolkit`, restart Docker, re-run preflight.

## 4. Insufficient VRAM at higher concurrency

**Symptom** — Cells at higher concurrency fail or the server restarts mid-run.

**Cause** — KV cache and activations for concurrent requests exceed 6 GiB VRAM.

**Verification** — Watch `peak_vram_mib` in `repeats.tsv`; check for OOM in
`server.log`.

**Fix** — The published matrix (C=1,2,4,6,8) fits by design at
`--ctx-size 4096 --parallel 2`. For heavier loads, reduce `--ctx-size` or cap
`--parallel`.

## 5. Wrong port

**Symptom** — `curl` to the endpoint returns connection refused.

**Cause** — The everyday deployments use 8000/8001; the 8-9B benchmark arms use
8200-8203 and the Spark reference uses 8100 (historical 4B arms used 8101-8105).

**Verification** — `./scripts/preflight.sh` port checks; check `configs/models.json`
for the per-model port.

**Fix** — Point clients at the correct port for the arm.

## 6. Startup timeout

**Symptom** — The container is healthy but slow to load the model.

**Cause** — First load compiles CUDA graphs / loads a multi-GB GGUF; on this
laptop it can exceed the default timeout.

**Verification** — `docker logs --timestamps` shows the model still loading.

**Fix** — Raise `STARTUP_TIMEOUT` (e.g. `STARTUP_TIMEOUT=300`).

## 7. Spark-X2.5-4B returns empty `content` (reasoning model)

**Symptom** — A short generation against the Spark reference returns an empty
`choices[0].message.content` even though `usage.completion_tokens > 0`.

**Cause** — Spark-X2.5-4B is a reasoning model; its first tokens are emitted in
`message.reasoning_content`, and `content` stays empty until reasoning ends.

**Verification** — Inspect the full response: `message` has both `content` and
`reasoning_content` keys.

**Fix** — None needed for the benchmark. AIPerf runs with
`--use-server-token-count`, so the server's `usage.completion_tokens` (which
includes reasoning tokens) drives the metrics.

## 8. Spark-X2.5-4B drops requests at long inputs

**Symptom** — The Spark reference is transport-unreliable at input lengths
&ge; 256 tokens; shape cells at higher ISL (256/512/768) show a nonzero error
rate.

**Cause** — The XHToken fork's HTTP server drops streaming connections under
long-prefill load; this is specific to the fork, not the upstream build.

**Verification** — The `shape` suite aggregate marks these cells `UNSTABLE` or
`FAIL`.

**Fix** — The affected shape cells are reported as `UNSTABLE` and excluded
from ranking. Short-prompt suites (capacity, reliability) are unaffected.
