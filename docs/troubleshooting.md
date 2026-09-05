# Troubleshooting

Real failure modes observed during this project's history, distilled from the
experiment logs. Each entry lists symptom, cause, verification, and fix.

## 1. `ServerDisconnectedError` during the benchmark

**Symptom** — AIPerf reports a nonzero error rate; `error_summary.tsv` shows
`ServerDisconnectedError('Server disconnected')` for a fraction of requests.

**Cause** — The llama.cpp server (or its HTTP layer) drops in-flight streaming
connections under load. In the final run this appeared at every concurrency
level for both models, worsening as concurrency rose (up to ~28% in one cell).

**Verification** — Inspect `server.log` in the run directory and the classified
`error_summary.tsv`. Count errors against `records` in `results.tsv`.

**Fix** — This is a measured property of the experiment, not a fatal setup bug.
It is reported explicitly rather than hidden; treat error rate as a hard gate
when comparing arms.

## 2. Container starts but never becomes API-ready

**Symptom** — `scripts/healthcheck.sh` prints `[FAIL] … did not become API-ready`.

**Cause** — Usually model load exceeds VRAM (OOM at startup), the GGUF path is
wrong, or the model is still loading past the `STARTUP_TIMEOUT`.

**Verification** — `docker logs --tail 200 <container>`; look for OOM / CUDA
allocation errors. `docker inspect -f '{{.State.OOMKilled}}' <container>`.

**Fix** — Confirm the model file exists and matches its SHA256
(`./scripts/download_models.sh`), free VRAM (stop other GPU containers), or
reduce `--ctx-size` / `--n-gpu-layers`.

## 3. GPU passthrough fails

**Symptom** — `docker run --gpus all … nvidia-smi` errors with "could not
select device driver … unknown capability gpu".

**Cause** — NVIDIA Container Toolkit not installed/enabled in the WSL2 distro.

**Verification** — `./scripts/preflight.sh` reports
`[WARN] docker GPU passthrough failed`.

**Fix** — Install `nvidia-container-toolkit`, then restart Docker and re-run
preflight.

## 4. vLLM does not recognize the GGUF model

**Symptom** — `bench-qwen-vllm-gguf` fails with an unknown-model-format error.

**Cause** — The `vllm-gguf-plugin` is missing, or its install silently changed
the vLLM version.

**Verification** — `docker run --rm --entrypoint python3 vllm-openai-gguf:v0.26.0 -c "import importlib.metadata as m; print(m.version('vllm'), m.version('vllm-gguf-plugin'))"`.

**Fix** — Rebuild `docker/vllm-gguf` (its Dockerfile asserts vLLM == 0.26.0 after
installing the pinned plugin).

## 5. Insufficient VRAM at higher concurrency

**Symptom** — Cells at concurrency 3–4 fail or the server restarts mid-run.

**Cause** — KV cache and activations for concurrent requests exceed 6 GiB VRAM.

**Verification** — Watch `peak_vram_mib` in `results.tsv`; check for OOM in
`server.log`.

**Fix** — The published matrix (C=1..4) fits by design. For heavier loads,
reduce `--ctx-size`, cap `--parallel`, or use a smaller quantization.

## 6. Wrong port / 401 Unauthorized

**Symptom** — `curl` to the endpoint returns connection refused, or vLLM returns
`401` / AIPerf reports `HTTP 401`.

**Cause** — The everyday deployments use 8000/8001; the benchmark uses 8100–8103.
vLLM is configured with `--api-key`, so unauthenticated requests are rejected.

**Verification** — `./scripts/preflight.sh` port checks; `curl -i http://127.0.0.1:8101/v1/models`.

**Fix** — Point clients at the right port; the llama.cpp benchmark arms have no
API key, so 401 against 8100/8101 indicates the wrong endpoint.

## 7. Startup timeout

**Symptom** — `STARTUP FAILURE …` with the container healthy but slow to load.

**Cause** — First load compiles CUDA graphs / loads a multi-GB GGUF; on this
laptop it can exceed the default 180 s.

**Verification** — `docker logs --timestamps` shows the model still loading.

**Fix** — Raise `STARTUP_TIMEOUT` (e.g. `STARTUP_TIMEOUT=300`).
