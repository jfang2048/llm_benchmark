#!/usr/bin/env python3
"""Current-benchmark dashboard generator.

Reads configs/models.json + configs/benchmark.json + the curated results under
results/current/ and produces:

  docs/data/current.json   - one normalized dashboard dataset (all charts read it)
  docs/index.html          - static shell that loads plotly.min.js + dashboard.js
  docs/assets/figures/*.svg - 2 static summary figures for the README

Every rendered number comes from the machine-readable data above; nothing is
hand-authored. The interactive rendering lives in docs/assets/dashboard.js
(Plotly, static GitHub Pages, no server).

Usage:
    python3 scripts/generate_current_report.py [--out docs/index.html]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bench import config  # noqa: E402

RESULT_ROOT = ROOT / "results" / "current"
DOCS = ROOT / "docs"
DATA_PATH = DOCS / "data" / "current.json"
FIG_DIR = DOCS / "assets" / "figures"

# (filesystem dir, registry cohort) for the current cohorts.
COHORT_DIRS = [("mainstream-8-9b", "mainstream_8_9b"),
               ("spark-reference", "spark_reference")]

# Colorblind-safe palette (Okabe-Ito). One stable, unique color per model arm.
MODEL_COLOR = {
    "qwen3_8b": "#0072B2",
    "deepseek_r1_8b": "#D55E00",
    "glm4_9b": "#009E73",
    "yi_15_9b": "#E69F00",
    "spark_llama": "#CC79A7",
}
# Fallback palette for any model not in MODEL_COLOR.
_FALLBACK = ["#0072B2", "#D55E00", "#009E73", "#E69F00", "#CC79A7", "#56B4E9"]
STATUS_COLOR = {
    "PASS": "#2e7d32",
    "UNSTABLE": "#f9a825",
    "FAIL": "#c62828",
    "TIMEOUT": "#c62828",
    "EXCLUDED": "#9e9e9e",
}


def load_tsv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def load_suite(suite, *globs):
    rows = []
    for cdir, cname in COHORT_DIRS:
        base = RESULT_ROOT / cdir / suite
        for g in globs:
            for p in base.glob(g):
                for r in load_tsv(p):
                    r = dict(r)
                    r["_cohort"] = cname
                    rows.append(r)
    return rows


def cell_status(r):
    if int(r.get("failed_runs") or 0) > 0:
        return "FAIL"
    if int(r.get("unstable_runs") or 0) > 0:
        return "UNSTABLE"
    if int(r.get("pass_runs") or 0) == 0:
        return "EXCLUDED"
    return "PASS"


# --------------------------------------------------------------------------
# Model metadata
# --------------------------------------------------------------------------
def models_meta():
    out = []
    for i, m in enumerate(config.models()):
        if not m.get("enabled"):
            continue
        if m.get("cohort") not in ("mainstream_8_9b", "spark_reference"):
            continue
        pc = m.get("actual_parameter_count")
        arm = m.get("arm")
        out.append({
            "arm": arm,
            "id": m.get("id"),
            "display_name": m.get("display_name", arm),
            "params_b": round((pc or 0) / 1e9, 2),
            "quantization": m.get("quantization"),
            "cohort": m.get("cohort"),
            "role": m.get("role"),
            "is_reference": m.get("role") == "reference",
            "license": m.get("license"),
            "upstream_repo": m.get("upstream_repo"),
            "color": MODEL_COLOR.get(arm, _FALLBACK[i % len(_FALLBACK)]),
        })
    return out


def manifest():
    p = RESULT_ROOT / "mainstream-8-9b" / "capacity" / "manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


# --------------------------------------------------------------------------
# Suite normalizers
# --------------------------------------------------------------------------
def capacity():
    agg = [r for r in load_suite("capacity", "aggregate.tsv")
           if r.get("suite") == "capacity"]
    rep = [r for r in load_suite("capacity", "repeats.tsv")
           if r.get("suite") == "capacity"]
    agg_out = []
    for r in agg:
        agg_out.append({
            "arm": r["arm"], "concurrency": int(r["concurrency"]),
            "status": cell_status(r),
            "ttft_p50": fnum(r.get("ttft_p50_ms_mean")),
            "ttft_p50_ci": fnum(r.get("ttft_p50_ms_ci95")),
            "ttft_p95": fnum(r.get("ttft_p95_ms_mean")),
            "ttft_p95_ci": fnum(r.get("ttft_p95_ms_ci95")),
            "latency_p50": fnum(r.get("latency_p50_ms_mean")),
            "latency_p50_ci": fnum(r.get("latency_p50_ms_ci95")),
            "latency_p95": fnum(r.get("latency_p95_ms_mean")),
            "latency_p95_ci": fnum(r.get("latency_p95_ms_ci95")),
            "request_tps": fnum(r.get("request_tps_mean")),
            "request_tps_ci": fnum(r.get("request_tps_ci95")),
            "output_tps": fnum(r.get("output_tps_mean")),
            "output_tps_ci": fnum(r.get("output_tps_ci95")),
            "peak_vram_mib": fnum(r.get("peak_vram_mib_mean")),
            "peak_power_w": fnum(r.get("peak_power_w_mean")),
            "error_rate_pct": fnum(r.get("error_rate_pct_mean")),
            "pass_runs": int(r.get("pass_runs") or 0),
            "unstable_runs": int(r.get("unstable_runs") or 0),
            "failed_runs": int(r.get("failed_runs") or 0),
        })
    rep_out = []
    for r in rep:
        rep_out.append({
            "arm": r["arm"], "concurrency": int(r["concurrency"]),
            "repeat": int(r["repeat"]), "status": r.get("status"),
            "ttft_p50": fnum(r.get("ttft_p50_ms")),
            "ttft_p95": fnum(r.get("ttft_p95_ms")),
            "latency_p50": fnum(r.get("latency_p50_ms")),
            "latency_p95": fnum(r.get("latency_p95_ms")),
            "request_tps": fnum(r.get("request_tps")),
            "output_tps": fnum(r.get("output_tps")),
            "peak_vram_mib": fnum(r.get("peak_vram_mib")),
            "peak_power_w": fnum(r.get("peak_power_w")),
            "avg_gpu_util_pct": fnum(r.get("avg_gpu_util_pct")),
            "peak_temp_c": fnum(r.get("peak_temp_c")),
            "gpu_energy_j": fnum(r.get("gpu_energy_j")),
            "gpu_j_per_request": fnum(r.get("gpu_j_per_request")),
            "gpu_j_per_output_token": fnum(r.get("gpu_j_per_output_token")),
        })
    return {"aggregate": agg_out, "repeats": rep_out}


def reliability():
    out = []
    for r in load_suite("reliability", "reliability.tsv"):
        out.append({
            "arm": r["arm"], "concurrency": int(r["concurrency"]),
            "attempted": int(r["attempted"]), "successful": int(r["successful"]),
            "failed": int(r["failed"]),
            "success_rate_pct": fnum(r["success_rate_pct"]),
            "wilson_low": fnum(r["wilson_low_pct"]),
            "wilson_high": fnum(r["wilson_high_pct"]),
            "error_types": r.get("error_types", ""),
        })
    return out


def open_loop(cap_agg):
    # base rate per arm = max achieved request throughput at capacity.
    base = {}
    for r in cap_agg:
        tps = r.get("request_tps")
        if tps is not None:
            base[r["arm"]] = max(base.get(r["arm"], 0.0), tps)
    out = []
    for r in load_suite("open-loop", "aggregate.tsv"):
        if r.get("suite") != "openloop":
            continue
        frac = fnum(r.get("isl"))
        out.append({
            "arm": r["arm"], "load_fraction": frac,
            "concurrency": int(r["concurrency"]),
            "status": cell_status(r),
            "offered_rps": round(base.get(r["arm"], 0.0) * frac, 4) if frac else None,
            "achieved_rps": fnum(r.get("request_tps_mean")),
            "error_rate_pct": fnum(r.get("error_rate_pct_mean")),
            "ttft_p50": fnum(r.get("ttft_p50_ms_mean")),
            "ttft_p95": fnum(r.get("ttft_p95_ms_mean")),
            "output_tps": fnum(r.get("output_tps_mean")),
        })
    return out


def shape(profiles):
    out = []
    for r in load_suite("shape", "aggregate.tsv"):
        suite = r.get("suite", "")
        if not suite.startswith("shape_"):
            continue
        profile = suite[len("shape_"):]
        p = profiles.get(profile, {})
        out.append({
            "arm": r["arm"], "profile": profile,
            "isl": int(fnum(r.get("isl")) or p.get("isl", 0)),
            "osl": p.get("osl", 0),
            "concurrency": int(r["concurrency"]),
            "status": cell_status(r),
            "ttft_p50": fnum(r.get("ttft_p50_ms_mean")),
            "output_tps": fnum(r.get("output_tps_mean")),
            "latency_p50": fnum(r.get("latency_p50_ms_mean")),
            "peak_vram_mib": fnum(r.get("peak_vram_mib_mean")),
            "error_rate_pct": fnum(r.get("error_rate_pct_mean")),
        })
    return out


def sessions():
    out = []
    for r in load_suite("sessions", "aggregate.tsv"):
        if r.get("suite") != "sessions":
            continue
        out.append({
            "arm": r["arm"], "cache_mode": r["isl"],
            "ttft_p50": fnum(r.get("ttft_p50_ms_mean")),
            "itl_p50": fnum(r.get("itl_p50_ms_mean")),
        })
    return out


def startup():
    out = []
    for r in load_suite("startup", "startup.tsv"):
        out.append({
            "arm": r["arm"], "repeat": int(r["repeat"]),
            "ready_ms": fnum(r["ready_ms"]),
            "first_token_ms": fnum(r["first_token_ms"]),
            "cold_start_ms": fnum(r["cold_start_ms"]),
        })
    return out


def soak():
    agg = [r for r in load_suite("soak", "aggregate.tsv") if r.get("suite") == "soak"]
    rep = [r for r in load_suite("soak", "repeats.tsv") if r.get("suite") == "soak"]
    temps = {}
    for r in rep:
        t = fnum(r.get("peak_temp_c"))
        if t is not None:
            temps[r["arm"]] = t
    out = []
    for r in agg:
        out.append({
            "arm": r["arm"],
            "status": cell_status(r),
            "ttft_p50": fnum(r.get("ttft_p50_ms_mean")),
            "request_tps": fnum(r.get("request_tps_mean")),
            "output_tps": fnum(r.get("output_tps_mean")),
            "error_rate_pct": fnum(r.get("error_rate_pct_mean")),
            "peak_vram_mib": fnum(r.get("peak_vram_mib_mean")),
            "peak_power_w": fnum(r.get("peak_power_w_mean")),
            "peak_temp_c": temps.get(r["arm"]),
        })
    return out


def llama_bench(id_to_arm):
    out = []
    for cdir, _cname in COHORT_DIRS:
        base = RESULT_ROOT / cdir / "llama-bench"
        for p in base.glob("*.txt"):
            arm = id_to_arm.get(p.stem, p.stem)
            pp = tg = None
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "pp512" in line:
                    tok = line.split("|")[-2].strip().split()[0]
                    pp = fnum(tok)
                elif "tg128" in line:
                    tok = line.split("|")[-2].strip().split()[0]
                    tg = fnum(tok)
            out.append({"arm": arm, "pp512": pp, "tg128": tg})
    return out


# --------------------------------------------------------------------------
# Static summary figures (README)
# --------------------------------------------------------------------------
def _svg_line(title, series, xlabel, ylabel, w=760, h=380, yfmt="{:.0f}"):
    """Minimal clean line chart. series = list of (label, color, [(x,y),...], dashed)."""
    pad_l, pad_r, pad_t, pad_b = 60, 20, 40, 50
    xs = [p[0] for _l, _c, pts, _d in series for p in pts if p[1] is not None]
    ys = [p[1] for _l, _c, pts, _d in series for p in pts if p[1] is not None]
    if not xs or not ys:
        return ""
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xspan = (xmax - xmin) or 1.0
    yspan = (ymax - ymin) or 1.0
    xmin, xmax = xmin - 0.05 * xspan, xmax + 0.05 * xspan
    ymin, ymax = ymin - 0.08 * yspan, ymax + 0.08 * yspan
    px = lambda v: pad_l + (v - xmin) / (xmax - xmin) * (w - pad_l - pad_r)
    py = lambda v: h - pad_b - (v - ymin) / (ymax - ymin) * (h - pad_t - pad_b)
    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
                 f'viewBox="0 0 {w} {h}" font-family="-apple-system,Segoe UI,Roboto,sans-serif">')
    parts.append(f'<rect width="{w}" height="{h}" fill="#ffffff"/>')
    parts.append(f'<text x="{pad_l}" y="24" font-size="14" font-weight="600" fill="#222">{title}</text>')
    # grid + axes
    for i in range(6):
        gy = pad_t + (h - pad_t - pad_b) * i / 5
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" stroke="#ececec"/>')
        parts.append(f'<text x="{pad_l-8}" y="{gy+4:.1f}" font-size="10" text-anchor="end" fill="#777">{yfmt.format(ymax-(ymax-ymin)*i/5)}</text>')
    for i in range(6):
        gx = pad_l + (w - pad_l - pad_r) * i / 5
        parts.append(f'<line x1="{gx:.1f}" y1="{pad_t}" x2="{gx:.1f}" y2="{h-pad_b}" stroke="#f2f2f2"/>')
        parts.append(f'<text x="{gx:.1f}" y="{h-pad_b+16}" font-size="10" text-anchor="middle" fill="#777">{xmin+(xmax-xmin)*i/5:.0f}</text>')
    parts.append(f'<text x="{w/2}" y="{h-8}" font-size="11" text-anchor="middle" fill="#555">{xlabel}</text>')
    parts.append(f'<text x="16" y="{h/2}" font-size="11" fill="#555" transform="rotate(-90 16 {h/2})" text-anchor="middle">{ylabel}</text>')
    for label, color, pts, dashed in series:
        pts = [p for p in pts if p[1] is not None]
        if not pts:
            continue
        d = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in pts)
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        parts.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
        for x, y in pts:
            parts.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3" fill="{color}"/>')
    # legend
    lx = pad_l
    for label, color, _pts, dashed in series:
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        parts.append(f'<line x1="{lx}" y1="{h-34}" x2="{lx+16}" y2="{h-34}" stroke="{color}" stroke-width="2"{dash}/>')
        parts.append(f'<text x="{lx+20}" y="{h-30}" font-size="10" fill="#444">{label}</text>')
        lx += 20 + len(label) * 6.2 + 24
    parts.append("</svg>")
    return "".join(parts)


def readme_figures(models, cap):
    # 1. Output tok/s vs concurrency (primary cohort only, aggregate line).
    series = []
    for m in models:
        if m["is_reference"]:
            continue
        pts = [(c["concurrency"], c["output_tps"])
               for c in sorted(cap["aggregate"], key=lambda x: x["concurrency"])
               if c["arm"] == m["arm"] and c["output_tps"] is not None]
        if pts:
            series.append((m["display_name"], m["color"], pts, False))
    fig1 = _svg_line("Output throughput vs concurrency (IQ4_XS, upstream llama.cpp)",
                     series, "concurrency", "output tokens/s", yfmt="{:.0f}")

    # 2. TTFT p50 vs request throughput trade-off (scatter, one point per c).
    series = []
    for m in models:
        pts = [(c["request_tps"], c["ttft_p50"])
               for c in sorted(cap["aggregate"], key=lambda x: x["concurrency"])
               if c["arm"] == m["arm"] and c["request_tps"] is not None and c["ttft_p50"] is not None]
        if pts:
            series.append((m["display_name"] + (" (reference)" if m["is_reference"] else ""),
                           m["color"], pts, m["is_reference"]))
    fig2 = _svg_line("TTFT p50 vs request throughput trade-off",
                     series, "request throughput (req/s)", "TTFT p50 (ms)", yfmt="{:.0f}")
    return fig1, fig2


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def _plotly_meta():
    """Record the vendored Plotly bundle version + SHA256 for provenance."""
    import hashlib
    import re
    p = DOCS / "assets" / "plotly.min.js"
    sha = ""
    version = ""
    if p.exists():
        raw = p.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        m = re.search(rb"plotly\.js v([\d.]+)", raw[:400])
        version = m.group(1).decode() if m else ""
    return {"plotly_version": version, "plotly_sha256": sha,
            "plotly_file": "assets/plotly.min.js"}


def build_data():
    m = manifest()
    models = models_meta()
    id_to_arm = {mm["id"]: mm["arm"] for mm in models}
    bench = config.load_benchmark()
    profiles = bench.get("shape_profiles", {}).get("profiles", {})
    cap = capacity()
    data = {
        "meta": {
            "gpu": m.get("gpu", ""),
            "engine": m.get("engine", ""),
            "image": m.get("image", ""),
            "quantization": m.get("quantization", "IQ4_XS"),
            "aiperf_version": m.get("aiperf_version", ""),
            "serving_flags": m.get("serving_flags", []),
            "context": 4096,
            "parallel": 2,
            "git_commit": m.get("git_commit", ""),
            "generated_at": "",
            **_plotly_meta(),
        },
        "config": {
            "reliability_threshold_pct": bench.get("reliability", {}).get("min_success_pct", 99.5),
            "shape_profiles": profiles,
            "concurrency_capacity": bench.get("concurrency", {}).get("capacity", [1, 2, 4, 6, 8]),
            "slo_profiles": bench.get("slo", bench.get("goodput", {})) or {},
        },
        "models": models,
        "capacity": cap,
        "reliability": reliability(),
        "open_loop": open_loop(cap["aggregate"]),
        "shape": shape(profiles),
        "sessions": sessions(),
        "startup": startup(),
        "soak": soak(),
        "llama_bench": llama_bench(id_to_arm),
    }
    return data, models, cap


def render_html(data):
    payload = json.dumps(data, ensure_ascii=False)
    cap_payload = "{}"
    cap_path = DOCS / "data" / "capability.json"
    if cap_path.exists():
        cap_payload = cap_path.read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local LLM Inference Benchmark</title>
<link rel="stylesheet" href="assets/dashboard.css">
<script src="assets/plotly.min.js"></script>
</head>
<body>
<div id="app"><div class="loading">Loading benchmark data&hellip;</div></div>
<script id="bench-data" type="application/json">{payload}</script>
<script id="capability-data" type="application/json">{cap_payload}</script>
<script src="assets/dashboard.js"></script>
<script src="assets/capability.js"></script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DOCS / "index.html"))
    args = ap.parse_args()

    data, models, cap = build_data()

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(data), encoding="utf-8")

    # README static figures
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig1, fig2 = readme_figures(models, cap)
    (FIG_DIR / "throughput-vs-concurrency.svg").write_text(fig1, encoding="utf-8")
    (FIG_DIR / "ttft-vs-throughput.svg").write_text(fig2, encoding="utf-8")

    print(f"wrote {out} ({len(models)} models)")
    print(f"wrote {DATA_PATH}")
    print(f"wrote 2 README figures under {FIG_DIR}")


if __name__ == "__main__":
    main()
