"""Run the synthetic Home Lab workload against Docker-hosted models."""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from . import config, results
from .serving import Telemetry, gpu_vram, oom_check, start_server, wait_for_temperature

ROOT = config.ROOT
SETTINGS = ROOT / "configs/home.json"
TASKS = ROOT / "configs/home_tasks.jsonl"
COLUMNS = [
    "arm", "scenario", "repeat", "task", "kind", "language", "status", "finish_reason",
    "first_token_ms", "first_answer_ms", "complete_ms", "input_tokens", "output_tokens",
    "redaction_leak", "fence_correct",
]
ARCHIVE_LINE = (
    "{i:02d} | Paper inventory check: plain folders counted at the front shelf. "
    "No appointment, room change, confidential identifier or final project decision on this sheet."
)
SYSTEM = "Return exactly one JSON object using the requested fields. Output JSON only."
HTTP = build_opener(ProxyHandler({}))
FENCE = re.compile(r"\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n[ \t]*```\s*", re.IGNORECASE | re.DOTALL)


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def prompt(task):
    text = task["prompt"]
    if task.get("archive"):
        appendix = "\n".join(ARCHIVE_LINE.format(i=i) for i in range(1, 24))
        text = appendix + "\n---\n" + text
    return text


def answer_text(chunks):
    """Strip raw think tags when the server exposes them as ordinary content."""
    joined = "".join(part for _, part in chunks)
    end = joined.rfind("</think>")
    offset = end + len("</think>") if end >= 0 else 0
    if end < 0 and joined.lstrip().startswith("<think>"):
        return "", None
    answer = joined[offset:].lstrip()
    if not answer:
        return "", None
    offset = len(joined) - len(answer)
    for stamp, part in chunks:
        offset -= len(part)
        if offset < 0:
            return answer, stamp
    return answer, None


def unique_object(pairs):
    value = dict(pairs)
    if len(value) != len(pairs):
        raise ValueError("duplicate JSON field")
    return value


def grade(answer, expected, finish_reason):
    if finish_reason == "length":
        return "truncated"
    if not answer:
        return "no_answer"
    try:
        parsed = json.loads(answer, object_pairs_hook=unique_object)
    except ValueError:
        return "invalid_json"
    # JSON equality with types preserved, including integer versus boolean.
    canonical = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False)
    return "correct" if canonical(parsed) == canonical(expected) else "wrong_value"


def request_task(url, alias, task, settings):
    user = prompt(task)
    # A single user turn works with the registered chat templates.
    payload = {
        "model": alias, "messages": [{"role": "user", "content": SYSTEM + "\n\n" + user}],
        "temperature": 0, "max_tokens": settings["max_output_tokens"], "stream": True,
        "stream_options": {"include_usage": True}, "cache_prompt": False,
    }
    req = Request(url + "/v1/chat/completions", data=json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json", "Connection": "close"})
    start = time.perf_counter()
    first_token, finish, usage, chunks = None, "", {}, []
    status = "transport_error"
    try:
        with HTTP.open(req, timeout=settings["request_timeout_s"]) as stream:
            for raw in stream:
                stamp = (time.perf_counter() - start) * 1000
                if stamp > settings["request_timeout_s"] * 1000:
                    raise TimeoutError("request budget exceeded")
                if not raw.startswith(b"data:"):
                    continue
                data = raw[5:].strip()
                if data == b"[DONE]":
                    break
                packet = json.loads(data)
                usage = packet.get("usage") or usage
                if not packet.get("choices"):
                    continue
                choice = packet["choices"][0]
                delta = choice.get("delta") or {}
                content = delta.get("content") or ""
                reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                if first_token is None and (content or reasoning):
                    first_token = stamp
                if content:
                    chunks.append((stamp, content))
                finish = choice.get("finish_reason") or finish
    except (OSError, HTTPException, ValueError, KeyError):
        pass
    else:
        if finish:
            status = None
    complete = (time.perf_counter() - start) * 1000
    answer, visible = answer_text(chunks)
    markers = task.get("sensitive", [])
    leak = int(any(span.casefold() in answer.casefold() for span in markers)) if markers and answer else None
    outcome = status or grade(answer, task["expected"], finish)
    fenced = FENCE.fullmatch(answer) if outcome == "invalid_json" else None
    return {
        "status": outcome, "finish_reason": finish,
        "first_token_ms": first_token, "first_answer_ms": visible, "complete_ms": complete,
        "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "redaction_leak": leak,
        "fence_correct": int(bool(fenced and grade(fenced[1], task["expected"], finish) == "correct")),
    }


def wait_server(url, name, deadline=90):
    expires = time.monotonic() + deadline
    while time.monotonic() < expires:
        try:
            with HTTP.open(url + "/health", timeout=1):
                return
        except (OSError, URLError):
            state = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", name],
                                   capture_output=True, text=True)
            if state.stdout.strip() != "true":
                break
            time.sleep(0.15)
    raise RuntimeError(f"{name} failed to become ready")


def run_arm(model, tasks, settings, output, model_dir):
    arm = model["arm"]
    image = config.engine_image(config.cohort_engine(model["cohort"]))
    name = f"home-{os.getpid()}-{arm.replace('_', '-')}"
    url = f"http://127.0.0.1:{model['port']}"
    flags = ["--ctx-size", str(settings["context"]), "--parallel", str(settings["slots"]),
             "--cont-batching", "--metrics", "--n-gpu-layers", str(settings["gpu_layers"])]
    if arm in settings["disable_reasoning_for"]:
        flags += ["--reasoning", "off"]
    if not wait_for_temperature(70):
        print(f"{arm}: GPU remained above 70 C at launch", flush=True)
    start = time.perf_counter()
    telemetry = Telemetry(output / f"{arm}.gpu.csv")
    try:
        result = start_server(name, image, model["port"], model["gguf_filename"], arm, model_dir, flags)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        wait_server(url, name)
        startup = (time.perf_counter() - start) * 1000
        idle = gpu_vram()
        telemetry.start()
        request_task(url, arm, tasks[0], settings)
        out = []
        windows = []
        scenarios = list(settings["scenarios"].items())
        for repeat in range(1, settings["repeats"] + 1):
            ordered = random.Random(41 + repeat).sample(tasks, len(tasks))
            for scenario, spec in scenarios if repeat % 2 else reversed(scenarios):
                with ThreadPoolExecutor(max_workers=spec["concurrency"]) as pool:
                    start = time.perf_counter()
                    rows = list(pool.map(lambda task: request_task(url, arm, task, settings), ordered))
                    elapsed = time.perf_counter() - start
                windows.append({"scenario": scenario, "repeat": repeat, "seconds": elapsed})
                for task, row in zip(ordered, rows):
                    out.append(dict(row, arm=arm, scenario=scenario, repeat=repeat,
                                    task=task["id"], kind=task["kind"], language=task["language"]))
                print(f"{arm} {scenario} repeat {repeat}: "
                      f"{sum(row['status'] == 'correct' for row in rows)}/{len(rows)} correct "
                      f"in {elapsed:.1f}s", flush=True)
        telemetry.stop()
        peak, _, _, temperature, _ = results.parse_gpu_csv(output / f"{arm}.gpu.csv")
        if oom_check(name):
            raise RuntimeError(f"{arm} emitted an allocation error")
        return out, {
            "arm": arm, "name": model["display_name"], "cohort": model["cohort"],
            "quantization": model["quantization"], "engine_image": image,
            "image_id": subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                                                text=True).strip(),
            "gguf_sha256": model["sha256"], "flags": flags, "startup_ms": startup,
            "ready_vram_mib": idle, "peak_vram_mib": max(v for v in (idle, peak) if v is not None),
            "peak_temperature_c": temperature, "windows": windows,
        }
    finally:
        telemetry.stop()
        log = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
        (output / f"{arm}.server.log").write_text(log.stdout + log.stderr, encoding="utf-8")
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".agent/home-run")
    parser.add_argument("--list-models", action="store_true", help="Print selected model IDs for setup")
    parser.add_argument("--model", action="append", help="Select an arm; can be repeated")
    args = parser.parse_args()
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    tasks = [json.loads(line) for line in TASKS.read_text(encoding="utf-8").splitlines()]
    models = [m for cohort in settings["cohorts"] for m in config.models_for_cohort(cohort)]
    if args.model:
        unknown = set(args.model) - {m["arm"] for m in models}
        if unknown:
            parser.error(f"unknown arms: {', '.join(sorted(unknown))}")
        models = [m for m in models if m["arm"] in args.model]
    if args.list_models:
        print("\n".join(model["id"] for model in models))
        return
    model_dir = Path(os.environ.get("MODEL_DIR", ROOT / "models")).resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("output directory must be empty")
    for model in models:
        file = model_dir / model["gguf_filename"]
        if not file.is_file() or sha(file) != model["sha256"]:
            parser.error(f"missing or invalid weight checksum: {file.name}")
    arms = []
    with (args.output / "requests.tsv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for model in models:
            rows, metadata = run_arm(model, tasks, settings, args.output, model_dir)
            writer.writerows(rows)
            stream.flush()
            arms.append(metadata)
    manifest = {
        "settings": settings, "tasks_sha256": sha(TASKS), "settings_sha256": sha(SETTINGS),
        "gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                                       "--format=csv,noheader,nounits"], text=True).strip(),
        "platform": os.uname().release,
        "source_commit": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
        "arms": arms,
    }
    (args.output / "tasks.jsonl").write_bytes(TASKS.read_bytes())
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
