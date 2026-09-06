"""Shared benchmark workload (raw-text capacity/soak prompts).

Single source of truth for the raw-text prompt set. The runner expands the 20
base cases into 100 prompt records (5 variants each) with a deterministic
case_id + variant tag, matching the historical workload bytes so results stay
comparable across cohorts.
"""
import json

BASE_PROMPTS = [
    "Explain TCP TIME_WAIT, why it exists, and when many TIME_WAIT sockets become operationally harmful. Give a concise SRE-oriented answer.",
    "A Linux host has load average 18 on 8 CPUs but CPU utilization is 25 percent. Give the diagnostic sequence and exact commands.",
    "A Docker container exits with code 137. Explain how to distinguish cgroup OOM, host OOM, and an external SIGKILL.",
    "A Kubernetes pod is in CrashLoopBackOff. Give a minimal investigation sequence and explain what each command proves.",
    "df -h shows free space but writes fail with No space left on device. List likely causes and exact validation commands.",
    "Explain TTFT, inter-token latency, end-to-end latency, request throughput, token throughput, and goodput for LLM serving.",
    "Why do p95 and p99 matter for an inference SLO even when average latency looks healthy?",
    "Explain prefill versus decode in transformer inference and the usual compute or memory bottleneck of each phase.",
    "Explain continuous batching and why it changes throughput and tail latency under concurrent LLM requests.",
    "An HTTP streaming response intermittently ends with connection reset by peer. Give a prioritized debugging checklist.",
    "Explain model weight memory, KV cache, activations, CUDA graph memory, and allocator overhead in LLM inference.",
    "A GPU process uses nearly all VRAM but GPU utilization oscillates between 20 and 90 percent. Explain possible causes and measurements.",
    "Explain how to detect thermal throttling on an NVIDIA laptop GPU while benchmarking inference.",
    "Explain why identical parameter counts do not guarantee identical inference cost across transformer models.",
    "Compare latency-oriented and throughput-oriented scheduling objectives for an LLM serving system.",
    "Explain why tokenizer differences make cross-model tokens-per-second comparisons imperfect.",
    "Describe how to determine whether an inference service is CPU-bound, GPU-compute-bound, memory-bandwidth-bound, or queue-bound.",
    "Explain Server-Sent Events framing and failure modes that cause incomplete streamed HTTP payloads.",
    "Describe a reproducible benchmark methodology for comparing two local LLM inference servers.",
    "Explain why a benchmark must distinguish cold-start latency, steady-state latency, saturation throughput, and failure rate.",
]


def write_workload_jsonl(path, variants=5):
    """Write the expanded 100-record workload to `path` and return its SHA256."""
    import hashlib
    with open(path, "w", encoding="utf-8") as f:
        n = 0
        for variant in range(variants):
            for text in BASE_PROMPTS:
                n += 1
                rec = {"text": f"case_id={n:03d}; {text} Variant={variant}."}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
