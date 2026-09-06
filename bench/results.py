"""Parse AIPerf artifacts and aggregate benchmark cells.

Ports the parsing/aggregation logic previously embedded in benchmark.sh into
the bench/ package so the runner and report generator share one implementation.
Kept small and side-effect-free: functions take paths/rows and return values.
"""
import csv
import json
import math
import os
import re
import statistics

TSV_HEADER = [
    "arm", "suite", "isl", "concurrency", "repeat", "status", "error_rate_pct",
    "attempted_requests", "successful_requests", "failed_requests",
    "success_rate_pct", "input_tokens_avg", "output_tokens_avg",
    "ttft_avg_ms", "ttft_p50_ms", "ttft_p95_ms", "ttft_p99_ms",
    "itl_avg_ms", "itl_p50_ms", "itl_p95_ms", "itl_p99_ms",
    "latency_avg_ms", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
    "request_tps", "output_tps", "peak_vram_mib", "peak_power_w",
    "avg_gpu_util_pct", "peak_temp_c", "gpu_energy_j",
    "gpu_j_per_request", "gpu_j_per_output_token",
]


def _metric(summary, name, stat="avg"):
    x = summary.get(name)
    if not isinstance(x, dict):
        return None
    v = x.get(stat)
    return float(v) if isinstance(v, (int, float)) else None


def parse_aiperf_summary(artifact_dir):
    """Return the profile_export_aiperf.json summary dict ({} if absent)."""
    path = os.path.join(artifact_dir, "profile_export_aiperf.json")
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def parse_aiperf_records(artifact_dir):
    """Return (attempted, failed) request counts from profile_export.jsonl."""
    path = os.path.join(artifact_dir, "profile_export.jsonl")
    total = errors = 0
    if os.path.exists(path):
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            md = r.get("metadata") or {}
            if md.get("benchmark_phase") not in (None, "profiling"):
                continue
            total += 1
            if r.get("error") is not None:
                errors += 1
    return total, errors


def parse_gpu_csv(gpu_csv):
    """Return (peak_vram, peak_power, avg_util, peak_temp, energy_j) from the
    nvidia-smi telemetry CSV, or None values when unavailable."""
    temp = []
    util = []
    mem = []
    power = []
    try:
        rd = csv.reader(open(gpu_csv, encoding="utf-8", errors="replace"))
        next(rd, None)
        for row in rd:
            nums = []
            for s in row:
                z = re.search(r"-?\d+(?:\.\d+)?", s)
                nums.append(float(z.group()) if z else None)
            if len(nums) >= 7:
                if nums[2] is not None:
                    temp.append(nums[2])
                if nums[3] is not None:
                    util.append(nums[3])
                if nums[5] is not None:
                    mem.append(nums[5])
                if nums[6] is not None:
                    power.append(nums[6])
    except Exception:
        pass
    sampling_s = 0.5
    energy = (sum(power) * sampling_s) if power else None
    return (
        max(mem) if mem else None,
        max(power) if power else None,
        (sum(util) / len(util)) if util else None,
        max(temp) if temp else None,
        energy,
    )


def cell_result(arm, suite, isl, conc, rep, rc, artifact_dir, gpu_csv,
                max_error_rate):
    """Assemble one TSV row (dict) for a completed AIPerf cell."""
    summary = parse_aiperf_summary(artifact_dir)
    total, errors = parse_aiperf_records(artifact_dir)
    err_pct = (100.0 * errors / total) if total else None
    successful = (total - errors) if total else None
    success_rate = (100.0 * successful / total) if total else None

    parse_ok = bool(summary) and total > 0
    if int(rc) in (124, 137):
        status = "TIMEOUT"
    elif int(rc) != 0:
        status = "FAIL_AIPERF"
    elif not parse_ok:
        status = "FAIL_PARSE"
    elif err_pct is not None and err_pct > float(max_error_rate):
        status = "UNSTABLE"
    else:
        status = "PASS"

    peak_vram, peak_power, avg_util, peak_temp, energy = parse_gpu_csv(gpu_csv)
    avg_out = _metric(summary, "output_sequence_length") or _metric(summary, "output_token_count")
    total_out = (avg_out * successful) if (avg_out is not None and successful) else None
    j_per_req = (energy / successful) if (energy is not None and successful) else None
    j_per_tok = (energy / total_out) if (energy is not None and total_out) else None

    def f(x):
        return "" if x is None else f"{x:.4f}"

    return {
        "arm": arm, "suite": suite, "isl": isl, "concurrency": str(conc),
        "repeat": str(rep), "status": status, "error_rate_pct": f(err_pct),
        "attempted_requests": str(total), "successful_requests": str(successful),
        "failed_requests": str(errors), "success_rate_pct": f(success_rate),
        "input_tokens_avg": f(_metric(summary, "input_sequence_length")),
        "output_tokens_avg": f(_metric(summary, "output_sequence_length") or _metric(summary, "output_token_count")),
        "ttft_avg_ms": f(_metric(summary, "time_to_first_token")),
        "ttft_p50_ms": f(_metric(summary, "time_to_first_token", "p50")),
        "ttft_p95_ms": f(_metric(summary, "time_to_first_token", "p95")),
        "ttft_p99_ms": f(_metric(summary, "time_to_first_token", "p99")),
        "itl_avg_ms": f(_metric(summary, "inter_token_latency")),
        "itl_p50_ms": f(_metric(summary, "inter_token_latency", "p50")),
        "itl_p95_ms": f(_metric(summary, "inter_token_latency", "p95")),
        "itl_p99_ms": f(_metric(summary, "inter_token_latency", "p99")),
        "latency_avg_ms": f(_metric(summary, "request_latency")),
        "latency_p50_ms": f(_metric(summary, "request_latency", "p50")),
        "latency_p95_ms": f(_metric(summary, "request_latency", "p95")),
        "latency_p99_ms": f(_metric(summary, "request_latency", "p99")),
        "request_tps": f(_metric(summary, "request_throughput")),
        "output_tps": f(_metric(summary, "output_token_throughput")),
        "peak_vram_mib": f(peak_vram), "peak_power_w": f(peak_power),
        "avg_gpu_util_pct": f(avg_util), "peak_temp_c": f(peak_temp),
        "gpu_energy_j": f(energy), "gpu_j_per_request": f(j_per_req),
        "gpu_j_per_output_token": f(j_per_tok),
    }


def write_repeats_tsv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TSV_HEADER, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TSV_HEADER})


def _fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def aggregate(rows):
    """Aggregate repeats per (suite, arm, isl, concurrency) into mean + CI95."""
    from .stats import mean_median_stddev  # local import to avoid cycles
    metrics = ["error_rate_pct", "ttft_p50_ms", "ttft_p95_ms", "itl_p50_ms",
               "itl_p95_ms", "latency_p50_ms", "latency_p95_ms",
               "request_tps", "output_tps", "peak_vram_mib", "peak_power_w"]
    keys = sorted({(r["suite"], r["arm"], r["isl"], r["concurrency"]) for r in rows})
    out_rows = []
    for k in keys:
        rr = [r for r in rows
              if (r["suite"], r["arm"], r["isl"], r["concurrency"]) == k]
        passed = [r for r in rr if r["status"] == "PASS"]
        unstable = [r for r in rr if r["status"] == "UNSTABLE"]
        parsed = passed + unstable
        failed = [r for r in rr if r["status"] not in ("PASS", "UNSTABLE")]
        rec = {
            "suite": k[0], "arm": k[1], "isl": k[2], "concurrency": k[3],
            "pass_runs": len(passed), "unstable_runs": len(unstable),
            "failed_runs": len(failed), "parsed_runs": len(parsed),
        }
        for m in metrics:
            xs = [_fnum(r.get(m)) for r in parsed if r.get(m, "") not in ("", "NA")]
            xs = [x for x in xs if x is not None]
            if not xs:
                rec[m + "_mean"], rec[m + "_ci95"] = "", ""
                continue
            mean = statistics.mean(xs)
            if len(xs) == 1:
                ci = 0.0
            else:
                t95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571}
                sd = statistics.stdev(xs)
                ci = t95.get(len(xs), 1.96) * sd / math.sqrt(len(xs))
            rec[m + "_mean"] = f"{mean:.4f}"
            rec[m + "_ci95"] = f"{ci:.4f}"
        out_rows.append(rec)
    return out_rows


def write_aggregate_tsv(agg_rows, path):
    cols = ["suite", "arm", "isl", "concurrency", "pass_runs", "unstable_runs",
            "failed_runs", "parsed_runs"]
    metrics = ["error_rate_pct", "ttft_p50_ms", "ttft_p95_ms", "itl_p50_ms",
               "itl_p95_ms", "latency_p50_ms", "latency_p95_ms",
               "request_tps", "output_tps", "peak_vram_mib", "peak_power_w"]
    cols += [z for m in metrics for z in (m + "_mean", m + "_ci95")]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        for r in agg_rows:
            w.writerow({k: r.get(k, "") for k in cols})


_ERROR_CHECKS = [
    ("ServerDisconnectedError", "serverdisconnectederror"),
    ("ClientPayloadError", "clientpayloaderror"),
    ("TransferEncodingError", "transferencodingerror"),
    ("ConnectionReset", "connection reset by peer"),
    ("ClientOSError", "clientoserror"),
    ("TimeoutError", "timeouterror"),
    ("HTTPError", "http"),
    ("ConnectionError", "connection"),
]


def classify_error(msg):
    low = (msg or "").lower()
    for label, pat in _ERROR_CHECKS:
        if pat in low:
            return label
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))", msg or "")
    return m.group(1) if m else "OtherError"


def extract_error_types(artifact_dir):
    """Return a Counter of classified error types from profile_export.jsonl."""
    import collections
    path = os.path.join(artifact_dir, "profile_export.jsonl")
    counts = collections.Counter()
    if not os.path.exists(path):
        return counts
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        md = r.get("metadata") or {}
        if md.get("benchmark_phase") not in (None, "profiling"):
            continue
        e = r.get("error")
        if e is None:
            continue
        if isinstance(e, str):
            msg = e
        else:
            msg = json.dumps(e, ensure_ascii=False, sort_keys=True)
        counts[classify_error(msg[:500])] += 1
    return counts


def reliability_summary(rows):
    """Aggregate reliability cells into attempted/successful/failed + Wilson CI.

    Groups repeats by (arm, concurrency). `rows` are cell-result dicts that carry
    an `error_types` JSON string (a Counter serialized by the runner).
    """
    from .stats import wilson_interval
    keys = sorted({(r["arm"], r["concurrency"]) for r in rows})
    out = []
    for arm, conc in keys:
        rr = [r for r in rows if r["arm"] == arm and r["concurrency"] == conc]
        attempted = sum(int(r.get("attempted_requests") or 0) for r in rr)
        successful = sum(int(r.get("successful_requests") or 0) for r in rr)
        failed = attempted - successful
        rate = (successful / attempted) if attempted else None
        low, high = wilson_interval(successful, attempted)
        errors = {}
        for r in rr:
            try:
                for typ, n in json.loads(r.get("error_types") or "{}").items():
                    errors[typ] = errors.get(typ, 0) + n
            except Exception:
                pass
        out.append({
            "arm": arm, "concurrency": conc, "attempted": attempted,
            "successful": successful, "failed": failed,
            "success_rate_pct": "" if rate is None else f"{100 * rate:.4f}",
            "wilson_low_pct": f"{100 * low:.4f}",
            "wilson_high_pct": f"{100 * high:.4f}",
            "error_types": json.dumps(errors, sort_keys=True),
        })
    return out


def write_reliability_tsv(rows, path):
    cols = ["arm", "concurrency", "attempted", "successful", "failed",
            "success_rate_pct", "wilson_low_pct", "wilson_high_pct",
            "error_types"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
