#!/usr/bin/env python3
"""Capability-evaluation runner.

Launches the existing IQ4_XS models under a *separate* coding/agent serving
profile (parallel=1, longer context) and exposes a minimal OpenAI-compatible
generation helper. It does not touch the serving benchmark or its results.

Model metadata is read from configs/models.json; benchmark pins and profiles
from evals/config.json. Nothing is hardcoded per model.

Usage:
    python3 evals/runner.py serve Qwen3-8B-IQ4_XS.gguf --ctx 8192 --parallel 1
    python3 evals/runner.py generate <arm> --prompts prompts.jsonl --out out.jsonl
    python3 evals/runner.py stop <arm>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = Path(os.environ.get("MODEL_DIR", ROOT / "models"))
EVALS_CFG = ROOT / "evals" / "config.json"


def load_models():
    with open(ROOT / "configs" / "models.json") as f:
        return json.load(f)


def load_evals_cfg():
    with open(EVALS_CFG) as f:
        return json.load(f)


def current_models():
    """Current serving cohort + Spark reference (enabled, current cohorts)."""
    data = load_models()
    cur = set(data["cohorts"].keys()) - {"historical_4b"}
    return [m for m in data["models"]
            if m.get("enabled") and m.get("cohort") in cur]


def model_by_arm(arm):
    return next((m for m in load_models()["models"] if m["arm"] == arm), None)


def engine_image_for(model):
    data = load_models()
    cohort = data["cohorts"][model["cohort"]]
    return data["engines"][cohort["engine"]]["image"]


def container_name(arm):
    return f"eval-{arm}"


def sh(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def serve(arm, ctx_size=8192, parallel=1, n_gpu_layers=999, reasoning="off",
          cache_type=None):
    m = model_by_arm(arm)
    if m is None:
        raise SystemExit(f"unknown arm: {arm}")
    image = engine_image_for(m)
    container = container_name(arm)
    sh("docker", "rm", "-f", container)
    args = [
        "docker", "run", "-d", "--name", container,
        "--gpus", "all", "--ipc", "host",
        "-p", f"127.0.0.1:{m['port']}:8000",
        "-v", f"{MODEL_DIR}:/models:ro",
        "--entrypoint", "/src/build/bin/llama-server",
        image,
        "--model", f"/models/{m['gguf_filename']}", "--alias", m["arm"],
        "--host", "0.0.0.0", "--port", "8000",
        "--ctx-size", str(ctx_size), "--parallel", str(parallel),
        "--cont-batching", "--metrics",
        "--n-gpu-layers", str(n_gpu_layers),
        "--reasoning", reasoning,
        "--reasoning-format", "deepseek",
    ]
    if cache_type:
        args += ["--cache-type-k", cache_type, "--cache-type-v", cache_type]
    r = sh(*args)
    if r.returncode != 0:
        raise SystemExit(f"docker run failed: {r.stderr.strip()}")
    return container


def wait_ready(arm, timeout=300):
    m = model_by_arm(arm)
    url = f"http://127.0.0.1:{m['port']}/health"
    start = time.time()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        if time.time() - start >= timeout:
            return False
        time.sleep(2)


def stop(arm):
    return sh("docker", "rm", "-f", container_name(arm)).returncode == 0


def generate(arm, prompts, temperature=0.0, n=1, max_tokens=1024, is_chat=True):
    """prompts: list of prompt strings (chat user messages) or list of
    {role, content} message lists. Returns list of completion dicts."""
    m = model_by_arm(arm)
    base = f"http://127.0.0.1:{m['port']}/v1"
    out = []
    for p in prompts:
        if is_chat:
            msgs = p if isinstance(p, list) else [{"role": "user", "content": p}]
            body = {"model": m["arm"], "messages": msgs,
                    "temperature": temperature, "n": n,
                    "max_tokens": max_tokens}
            endpoint = f"{base}/chat/completions"
        else:
            body = {"model": m["arm"], "prompt": p,
                    "temperature": temperature, "n": n,
                    "max_tokens": max_tokens}
            endpoint = f"{base}/completions"
        req = urllib.request.Request(
            endpoint, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                resp = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            resp = {"error": e.read().decode()[:400]}
        except Exception as e:
            resp = {"error": str(e)}
        out.append(resp)
    return out


def extract_text(resp):
    """Best-effort text extraction from an OpenAI-compatible response.
    Prefers the final answer (`content`); falls back to `reasoning_content`
    only when content is empty (e.g. a model that never ends its think)."""
    if not resp or "choices" not in resp:
        return ""
    c = resp["choices"][0]
    msg = c.get("message") or {}
    content = msg.get("content") or ""
    if content.strip():
        return content
    return msg.get("reasoning_content") or c.get("text") or ""


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("serve")
    p.add_argument("arm")
    p.add_argument("--ctx", type=int, default=8192)
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--gpu-layers", type=int, default=999)
    p.add_argument("--reasoning", default="off", choices=["on", "off", "auto"])

    p = sub.add_parser("stop")
    p.add_argument("arm")

    p = sub.add_parser("generate")
    p.add_argument("arm")
    p.add_argument("--prompts", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--chat", action="store_true", default=True)
    p.add_argument("--no-chat", dest="chat", action="store_false")

    p = sub.add_parser("health")
    p.add_argument("arm")

    a = ap.parse_args()

    if a.cmd == "serve":
        print(f"starting {a.arm} (ctx={a.ctx}, parallel={a.parallel}, reasoning={a.reasoning})")
        serve(a.arm, a.ctx, a.parallel, a.gpu_layers, a.reasoning)
        ok = wait_ready(a.arm)
        print("READY" if ok else "NOT_READY")
        sys.exit(0 if ok else 1)

    if a.cmd == "stop":
        ok = stop(a.arm)
        print("STOPPED" if ok else "NOT_FOUND")
        sys.exit(0 if ok else 1)

    if a.cmd == "health":
        print("OK" if wait_ready(a.arm, timeout=5) else "DOWN")

    if a.cmd == "generate":
        with open(a.prompts) as f:
            prompts = json.load(f)
        resps = generate(a.arm, prompts, a.temperature, a.n, a.max_tokens, a.chat)
        rows = [{"prompt": prompts[i], "raw": resps[i],
                 "text": extract_text(resps[i])} for i in range(len(prompts))]
        with open(a.out, "w") as f:
            json.dump(rows, f, indent=2)
        print(f"wrote {len(rows)} completions to {a.out}")


if __name__ == "__main__":
    main()
