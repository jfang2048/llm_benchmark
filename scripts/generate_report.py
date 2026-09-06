#!/usr/bin/env python3
"""Reproducible report generator.

Reads the curated benchmark data in results/final/ and regenerates every
derived artifact — no numbers are hardcoded by hand:

    results/final/provenance.json      machine-readable provenance
    results/final/summary.md           clean textual summary
    results/final/model_comparison.md  side-by-side comparison tables
    docs/data/benchmark.json           data consumed by the dashboard
    docs/index.html                    interactive Plotly dashboard (static)
    docs/assets/*.svg                  static README charts

Usage:
    python3 scripts/generate_report.py
    # optional: python3 scripts/generate_report.py --source results/final --out docs

Requires plotly (see requirements-report.txt). Run inside the project venv.
"""
import csv
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "final"
DOCS = ROOT / "docs" / "history" / "v1"
DATA_DIR = DOCS / "data"
ASSETS_DIR = DOCS / "assets"

# ---------------------------------------------------------------------------
# Canonical metric table: (column_key, label, unit, direction)
# ---------------------------------------------------------------------------
METRICS = [
    ("error_rate_pct", "Error rate", "%", "lower"),
    ("ttft_p50_ms", "TTFT p50", "ms", "lower"),
    ("ttft_p95_ms", "TTFT p95", "ms", "lower"),
    ("itl_p50_ms", "Inter-token latency p50", "ms", "lower"),
    ("itl_p95_ms", "Inter-token latency p95", "ms", "lower"),
    ("latency_p50_ms", "E2E latency p50", "ms", "lower"),
    ("latency_p95_ms", "E2E latency p95", "ms", "lower"),
    ("request_tps", "Request throughput", "req/s", "higher"),
    ("output_tps", "Output token throughput", "tok/s", "higher"),
    ("peak_vram_mib", "Peak VRAM", "MiB", "lower"),
    ("peak_power_w", "Peak power", "W", "lower"),
]

ARMS = {
    "spark_llama": {"model": "Spark-X2.5-4B-Q4_K_M", "label": "Spark-X2.5-4B"},
    "qwen_llama": {"model": "Qwen3-4B-Q4_K_M", "label": "Qwen3-4B"},
}

# Verified experiment facts (captured from the run and the live machine).
PROVENANCE_FACTS = {
    "run_id": "20260904_192416",
    "source_directory": "benchmark/results-model/20260904_192416 (historical run ID)",
    "benchmark_script": "scripts/benchmark.sh",
    "original_script_version": "model_benchmark_v11_diag.sh",
    "models": ["Spark-X2.5-4B-Q4_K_M", "Qwen3-4B-Q4_K_M"],
    "backends": ["llama.cpp"],
    "benchmark_parameters": {
        "requests_per_cell": 80,
        "warmup_requests": 5,
        "repeats": 4,
        "output_token_cap": 128,
        "concurrency": [1, 2, 3, 4],
        "seed": 42,
        "temperature": 0,
        "ignore_eos": True,
        "cache_prompt": False,
        "input_sequence_length": "raw (unpadded prompts, identical across arms)",
    },
    "software": {
        "benchmark_tool": "AIPerf 0.12.0",
        "llama_cpp": "XHToken/llama.cpp fork (Spark-X2.5 support), CUDA 13.3.1 build",
        "vllm": "0.26.0 (engine-comparison context only)",
        "docker": "29.7.2",
    },
    "hardware": {
        "gpu": "NVIDIA GeForce RTX 3060 Laptop GPU",
        "vram_mib": 6144,
        "driver": "610.74",
        "cuda_umd": "13.3",
        "cpu": "AMD Ryzen 7 6800H with Radeon Graphics (16 logical CPUs)",
        "os": "WSL2 Ubuntu 24.04 (kernel 6.18.33.2-microsoft-standard-WSL2)",
    },
    "model_sha256": {
        "Spark-X2.5-4B-Q4_K_M.gguf": "7934660bfc5b9bf04be0a0ac6179a1d16e1d4331b448857c86b8b2801b3ef72c",
        "Qwen3-4B-Q4_K_M.gguf": "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
    },
    "serving_image_id": "sha256:28f81be4ba34412125fc6ca33a3629e65cb31741496f29f306d03c5a3ac80c52",
    "result_files": {
        "results.tsv": "per-cell raw results (2 models x 4 concurrency x 4 repeats + sanity)",
        "aggregate.tsv": "mean and 95% CI per arm/concurrency",
        "error_summary.tsv": "classified request errors per cell",
        "runtime_config.txt": "serving-control equivalence report",
        "workload.jsonl": "100 synthetic prompts (20 base x 5 variants)",
    },
}


def load_aggregate():
    """Return list of dicts from results/final/aggregate.tsv (model suite only)."""
    rows = list(csv.DictReader(open(RESULTS / "aggregate.tsv", encoding="utf-8"), delimiter="\t"))
    return [r for r in rows if r["suite"] == "model"]


def build_records(agg):
    records = []
    for r in agg:
        arm = r["arm"]
        rec = {
            "arm": arm,
            "model": ARMS[arm]["model"],
            "label": ARMS[arm]["label"],
            "concurrency": int(r["concurrency"]),
            "valid_runs": int(r["valid_runs"]),
            "invalid_runs": int(r["invalid_runs"]),
        }
        for key, _label, _unit, _dir in METRICS:
            mean = r.get(f"{key}_mean", "")
            ci = r.get(f"{key}_ci95", "")
            rec[key] = float(mean) if mean not in ("", "NA") else None
            rec[f"{key}_ci95"] = float(ci) if ci not in ("", "NA") else None
        records.append(rec)
    # Order by arm then concurrency.
    records.sort(key=lambda x: (x["arm"], x["concurrency"]))
    return records


def write_benchmark_json(records):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "metrics": [{"key": k, "label": l, "unit": u, "direction": d} for k, l, u, d in METRICS],
        "arms": ARMS,
        "records": records,
        "generated_from": "results/final/aggregate.tsv",
    }
    (DATA_DIR / "benchmark.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_provenance(records):
    import datetime
    prov = dict(PROVENANCE_FACTS)
    prov["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (RESULTS / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")


def _fmt(mean, ci, unit):
    if mean is None:
        return "NA"
    if unit == "%":
        return f"{mean:.2f} ± {ci:.2f}"
    if unit in ("ms", "MiB", "W"):
        return f"{mean:.2f} ± {ci:.2f}"
    return f"{mean:.3f} ± {ci:.3f}"


def write_summary_md(records):
    lines = []
    lines.append("# Benchmark Summary\n")
    lines.append(f"- Run ID: `{PROVENANCE_FACTS['run_id']}`")
    lines.append("- Comparison: **Spark-X2.5-4B-Q4_K_M vs Qwen3-4B-Q4_K_M**")
    lines.append("- Engine fixed: **llama.cpp** (same binary and serving flags for both arms)")
    lines.append("- Quantization fixed: **Q4_K_M**")
    lines.append(f"- GPU: `{PROVENANCE_FACTS['hardware']['gpu']}` ({PROVENANCE_FACTS['hardware']['vram_mib']} MiB VRAM)")
    lines.append("- Workload: identical raw-text prompts, identical order, `temperature=0`, `ignore_eos=true`, `cache_prompt=false`")
    lines.append("- Per cell: 80 profiling requests, 5 warmup, 4 repeats, output cap 128 tokens")
    lines.append("- Concurrency: 1, 2, 3, 4\n")

    lines.append("## Headline results\n")
    lines.append("| Concurrency | Spark req/s | Qwen req/s | Spark TTFT p50 (ms) | Qwen TTFT p50 (ms) | Spark error | Qwen error |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    for c in sorted({r["concurrency"] for r in records}):
        s = next(r for r in records if r["arm"] == "spark_llama" and r["concurrency"] == c)
        q = next(r for r in records if r["arm"] == "qwen_llama" and r["concurrency"] == c)
        lines.append(
            f"| {c} | {s['request_tps']:.3f} | {q['request_tps']:.3f} "
            f"| {s['ttft_p50_ms']:.1f} | {q['ttft_p50_ms']:.1f} "
            f"| {s['error_rate_pct']:.1f}% | {q['error_rate_pct']:.1f}% |"
        )
    lines.append("\nSee `model_comparison.md` for the full side-by-side tables and the "
                 "interactive dashboard at `docs/index.html`.\n")
    (RESULTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_model_comparison_md(records):
    """Regenerate the human-readable comparison report from aggregate data."""
    agg = {arm: {r["concurrency"]: r for r in records if r["arm"] == arm} for arm in ARMS}
    concs = sorted({r["concurrency"] for r in records})
    out = []
    out.append("# Spark-X2.5-4B vs Qwen3-4B — Model Benchmark\n")
    out.append(f"- Run ID: `{PROVENANCE_FACTS['run_id']}`")
    out.append(f"- GPU: `{PROVENANCE_FACTS['hardware']['gpu']}`, "
               f"driver `{PROVENANCE_FACTS['hardware']['driver']}`, "
               f"{PROVENANCE_FACTS['hardware']['vram_mib']} MiB VRAM")
    out.append("- AIPerf profiling requests per cell: **80**; warmup: **5**; repeats: **4**; output cap: **128 tokens**")
    out.append("- Concurrency: **1 2 3 4**; engine fixed: **llama.cpp**; quantization fixed: **Q4_K_M**")
    out.append("- Workload fixed: identical raw-text prompts, identical order, `temperature=0`, `ignore_eos=true`, `cache_prompt=false`")
    out.append("- Independent variable: **model** (checkpoint/architecture/tokenizer treated as the model package)")
    out.append("- Spark GGUF SHA256: `7934660bfc5b9bf04be0a0ac6179a1d16e1d4331b448857c86b8b2801b3ef72c`")
    out.append("- Qwen GGUF SHA256: `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`\n")

    def delta(a, b, direction):
        if a is None or b is None or a == 0:
            return "NA"
        pct = (b - a) / abs(a) * 100.0
        improvement = -pct if direction == "lower" else pct
        return f"{'+' if improvement >= 0 else ''}{improvement:.1f}%"

    def winner(a, b, direction):
        if a is None or b is None:
            return "NA"
        tol = max(abs(a), abs(b), 1.0) * 0.005
        if abs(a - b) <= tol:
            return "Tie"
        if direction == "lower":
            return "Spark" if a < b else "Qwen"
        return "Spark" if a > b else "Qwen"

    out.append("## Run validity\n")
    out.append("| Concurrency | Spark PASS / total | Qwen PASS / total | Spark mean error | Qwen mean error |")
    out.append("|---:|---:|---:|---:|---:|")
    for c in concs:
        s = agg["spark_llama"][c]
        q = agg["qwen_llama"][c]
        out.append(f"| {c} | {s['valid_runs']}/{s['valid_runs'] + s['invalid_runs']} "
                   f"| {q['valid_runs']}/{q['valid_runs'] + q['invalid_runs']} "
                   f"| {s['error_rate_pct']:.2f}% | {q['error_rate_pct']:.2f}% |")

    out.append("\n## Side-by-side results\n")
    out.append("Values are mean ± 95% CI across successfully parsed repeats (PASS + UNSTABLE). "
               "`Δ Qwen vs Spark` is positive when Qwen is better for that metric.\n")
    for c in concs:
        out.append(f"### Concurrency {c}\n")
        out.append("| Metric | Spark | Qwen | Δ Qwen vs Spark | Winner |")
        out.append("|---|---:|---:|---:|---|")
        for key, label, unit, direction in METRICS:
            s = agg["spark_llama"][c]
            q = agg["qwen_llama"][c]
            out.append(f"| {label} | {_fmt(s[key], s[key + '_ci95'], unit)} | "
                       f"{_fmt(q[key], q[key + '_ci95'], unit)} | "
                       f"{delta(s[key], q[key], direction)} | {winner(s[key], q[key], direction)} |")
        out.append("")

    out.append("## Interpretation notes\n")
    out.append("- Treat **error rate as a hard gate**: a faster arm with materially higher request failures is not the better serving result.")
    out.append("- For interactive use, prioritize **TTFT p95** and **E2E p95**; for saturation behavior, prioritize **request throughput** together with error rate.")
    out.append("- `Output token throughput` is secondary across different models because their tokenizers differ; request-level latency/throughput is more directly comparable under identical raw prompts.")
    out.append("- Peak VRAM and power are efficiency metrics, not quality metrics; do not merge them into latency/throughput without an explicit weighting policy.\n")
    (RESULTS / "model_comparison.md").write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Static SVG charts (pure stdlib — no kaleido dependency)
# ---------------------------------------------------------------------------
def _svg_line_chart(title, ylabel, series, width=560, height=320):
    """series: list of (label, color, [(x, y), ...])"""
    xs = sorted({p[0] for s in series for p in s[2]})
    ys = [p[1] for s in series for p in s[2] if p[1] is not None]
    if not xs or not ys:
        return ""
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if ymin == ymax:
        ymin, ymax = ymin - 1, ymax + 1
    pad_y = (ymax - ymin) * 0.12
    ymin -= pad_y
    ymax += pad_y
    left, right, top, bottom = 60, 20, 30, 46
    pw = width - left - right
    ph = height - top - bottom

    def X(x):
        return left + (x - xmin) / (xmax - xmin) * pw if xmax != xmin else left + pw / 2

    def Y(y):
        return top + (ymax - y) / (ymax - ymin) * ph

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                 f'viewBox="0 0 {width} {height}" font-family="Helvetica,Arial,sans-serif">')
    parts.append(f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>')
    # title
    parts.append(f'<text x="{width/2}" y="18" font-size="14" font-weight="bold" text-anchor="middle">{title}</text>')
    # axes
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+ph}" stroke="#333" stroke-width="1"/>')
    parts.append(f'<line x1="{left}" y1="{top+ph}" x2="{left+pw}" y2="{top+ph}" stroke="#333" stroke-width="1"/>')
    # y ticks
    for i in range(5):
        yv = ymin + (ymax - ymin) * i / 4
        yp = Y(yv)
        parts.append(f'<line x1="{left-4}" y1="{yp}" x2="{left}" y2="{yp}" stroke="#333"/>')
        parts.append(f'<text x="{left-8}" y="{yp+3}" font-size="10" text-anchor="end">{yv:.4g}</text>')
    # x ticks
    for xv in xs:
        xp = X(xv)
        parts.append(f'<line x1="{xp}" y1="{top+ph}" x2="{xp}" y2="{top+ph+4}" stroke="#333"/>')
        parts.append(f'<text x="{xp}" y="{top+ph+16}" font-size="10" text-anchor="middle">{xv}</text>')
    # axis labels
    parts.append(f'<text x="{left-42}" y="{top+ph/2}" font-size="11" text-anchor="middle" '
                 f'transform="rotate(-90 {left-42} {top+ph/2})">{ylabel}</text>')
    parts.append(f'<text x="{left+pw/2}" y="{height-8}" font-size="11" text-anchor="middle">Concurrency</text>')
    # series
    for label, color, pts in series:
        pts = [p for p in pts if p[1] is not None]
        if not pts:
            continue
        d = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts)
        parts.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="3.5" fill="{color}"/>')
    # legend
    lx = left + pw - 4
    for label, color, _pts in series:
        parts.append(f'<circle cx="{lx-8}" cy="22" r="4" fill="{color}"/>')
        parts.append(f'<text x="{lx}" y="26" font-size="10" text-anchor="end">{label}</text>')
        lx -= (len(label) * 6 + 24)
    parts.append("</svg>")
    return "\n".join(parts)


def write_static_charts(records):
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    spark = [r for r in records if r["arm"] == "spark_llama"]
    qwen = [r for r in records if r["arm"] == "qwen_llama"]
    spark.sort(key=lambda r: r["concurrency"])
    qwen.sort(key=lambda r: r["concurrency"])

    def series(metric):
        return [
            ("Spark-X2.5-4B", "#e07b39", [(r["concurrency"], r[metric]) for r in spark]),
            ("Qwen3-4B", "#3a7bd5", [(r["concurrency"], r[metric]) for r in qwen]),
        ]

    (ASSETS_DIR / "throughput_summary.svg").write_text(
        _svg_line_chart("Request throughput vs concurrency", "req/s", series("request_tps")),
        encoding="utf-8",
    )
    (ASSETS_DIR / "latency_summary.svg").write_text(
        _svg_line_chart("E2E latency (p50) vs concurrency", "ms", series("latency_p50_ms")),
        encoding="utf-8",
    )
    (ASSETS_DIR / "ttft_summary.svg").write_text(
        _svg_line_chart("TTFT (p50) vs concurrency", "ms", series("ttft_p50_ms")),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Interactive Plotly dashboard (static HTML, no backend)
# ---------------------------------------------------------------------------
def write_index_html(records):
    try:
        import plotly.graph_objects as go
    except ImportError:
        print("plotly not installed — skipping docs/index.html. "
              "Install requirements-report.txt and re-run.", file=sys.stderr)
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Build one figure per metric (so the JS can switch without rebuilding).
    figs = {}
    for key, label, unit, direction in METRICS:
        fig = go.Figure()
        for arm, color in (("spark_llama", "#e07b39"), ("qwen_llama", "#3a7bd5")):
            pts = [r for r in records if r["arm"] == arm]
            pts.sort(key=lambda r: r["concurrency"])
            xs = [r["concurrency"] for r in pts]
            ys = [r[key] for r in pts]
            cis = [r[f"{key}_ci95"] for r in pts]
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines+markers", name=ARMS[arm]["label"],
                line=dict(color=color, width=2.5),
                marker=dict(size=9),
                error_y=dict(type="data", array=cis, visible=True, thickness=1.5, color=color),
                hovertemplate=f"{ARMS[arm]['label']}<br>concurrency=%{{x}}<br>{label}=%{{y:.3f}} {unit}"
                               f"<br>± %{{error_y.array:.3f}}<extra></extra>",
            ))
        fig.update_layout(
            title=dict(text=f"{label} vs concurrency", font=dict(size=16)),
            xaxis=dict(title="Concurrency", dtick=1, gridcolor="#eee"),
            yaxis=dict(title=unit, gridcolor="#eee", zeroline=False),
            margin=dict(l=60, r=20, t=60, b=45),
            template="plotly_white",
            height=430,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        figs[key] = json.loads(fig.to_json())

    benchmark_json = json.dumps({
        "metrics": [{"key": k, "label": l, "unit": u, "direction": d} for k, l, u, d in METRICS],
        "figs": figs,
        "arms": ARMS,
    })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local LLM Inference Benchmark — Interactive Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root {{ --bg:#0f1420; --panel:#171e2e; --text:#e6eaf2; --muted:#9aa4b8; --accent:#3a7bd5; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         background:var(--bg); color:var(--text); }}
  header {{ padding:22px 28px; border-bottom:1px solid #232c40; }}
  header h1 {{ margin:0 0 4px; font-size:20px; }}
  header p {{ margin:0; color:var(--muted); font-size:13px; }}
  .wrap {{ display:flex; }}
  .controls {{ width:260px; padding:20px; border-right:1px solid #232c40; flex-shrink:0; }}
  .controls label {{ display:block; font-size:12px; color:var(--muted); margin:14px 0 6px; }}
  .controls select, .controls button {{ width:100%; padding:8px; border-radius:6px; border:1px solid #2a3550;
      background:#1a2233; color:var(--text); font-size:13px; }}
  .model-toggles {{ display:flex; gap:8px; margin-top:4px; }}
  .model-toggles button {{ flex:1; }}
  .model-toggles button.off {{ opacity:0.4; }}
  .content {{ flex:1; padding:20px; }}
  .chart {{ background:var(--panel); border:1px solid #232c40; border-radius:10px;
            padding:10px; margin-bottom:18px; }}
  .note {{ color:var(--muted); font-size:12px; line-height:1.5; }}
  .metric-desc {{ color:var(--muted); font-size:12px; margin:6px 0 0; }}
</style>
</head>
<body>
<header>
  <h1>Local LLM Inference Benchmark — Interactive Dashboard</h1>
  <p>Spark-X2.5-4B-Q4_K_M vs Qwen3-4B-Q4_K_M on llama.cpp · RTX 3060 Laptop GPU (6 GiB VRAM)
     · 80 requests/cell · 4 repeats · output cap 128 tokens · error bars = 95% CI (n=4)</p>
  <div style="background:#3a2b12;border:1px solid #7a5a1e;border-radius:8px;padding:10px 14px;margin-top:10px;font-size:13px;">
    <strong>Historical diagnostic benchmark — transport instability observed.</strong>
    This run (20260904_192416) shows substantial <code>ServerDisconnectedError</code>
    rates and is retained as provenance, not as a final performance ranking. It
    motivated Benchmark v2, whose reliability gate must pass before any new
    ranking is published. See <code>BACKLOG.md</code>.
  </div>
</header>
<div class="wrap">
  <div class="controls">
    <label for="metric">Metric</label>
    <select id="metric"></select>
    <p class="metric-desc" id="metric-desc"></p>
    <label>Models</label>
    <div class="model-toggles">
      <button id="toggle-spark" onclick="toggleModel(0)">Spark</button>
      <button id="toggle-qwen" onclick="toggleModel(1)">Qwen</button>
    </div>
    <label>Concurrency filter</label>
    <div class="model-toggles" id="conc-filter"></div>
    <label>Actions</label>
    <button onclick="resetZoom()">Reset zoom</button>
  </div>
  <div class="content">
    <div class="chart" id="main-chart"></div>
    <div class="chart" id="grid-chart"></div>
    <p class="note">
      Each point is the mean across 4 repeats; error bars show the 95% confidence interval (t-distribution, n=4).
      Hover any point for exact values. Click legend entries to toggle traces; drag to zoom; double-click to reset.
      Lower is better for latency and error rate; higher is better for throughput. Data source:
      <code>results/final/aggregate.tsv</code>, rendered by <code>scripts/generate_report.py</code>.
    </p>
  </div>
</div>
<script>
const DATA = {benchmark_json};
const METRICS = DATA.metrics;
const FIGS = DATA.figs;
const sel = document.getElementById('metric');
METRICS.forEach((m, i) => {{
  const o = document.createElement('option');
  o.value = m.key; o.textContent = m.label + ' (' + m.unit + ')';
  sel.appendChild(o);
}});
sel.onchange = renderMain;
function metricDesc() {{
  const m = METRICS.find(x => x.key === sel.value);
  document.getElementById('metric-desc').textContent =
    (m.direction === 'lower' ? 'Lower is better.' : 'Higher is better.') +
    ' Unit: ' + m.unit + '.';
}}
function renderMain() {{
  const fig = FIGS[sel.value];
  Plotly.react('main-chart', fig.data, fig.layout, {{responsive:true}});
  metricDesc();
}}
function toggleModel(i) {{
  const btn = i === 0 ? document.getElementById('toggle-spark') : document.getElementById('toggle-qwen');
  btn.classList.toggle('off');
  const fig = FIGS[sel.value];
  const vis = !btn.classList.contains('off');
  const upd = {{visible: vis}};
  Plotly.restyle('main-chart', upd, [i]);
}}
function resetZoom() {{ Plotly.relayout('main-chart', {{'xaxis.autorange':true,'yaxis.autorange':true}}); }}

// Concurrency filter buttons.
const CONCS = [1,2,3,4];
const cf = document.getElementById('conc-filter');
CONCS.forEach(c => {{
  const b = document.createElement('button');
  b.textContent = c; b.dataset.c = c; b.onclick = () => toggleConc(c, b);
  cf.appendChild(b);
}});
function toggleConc(c, btn) {{
  btn.classList.toggle('off');
  const off = new Set([...document.querySelectorAll('#conc-filter button.off')].map(b => +b.dataset.c));
  const fig = FIGS[sel.value];
  const xs = fig.data[0].x;
  const inds = xs.map((v,i) => off.has(v) ? i : null).filter(v => v !== null);
  Plotly.restyle('main-chart', {{x:[xs.filter(v => !off.has(v))]}});
}}

// Mini-grid of fixed key metrics.
const gridKeys = ['request_tps','ttft_p50_ms','latency_p50_ms','error_rate_pct'];
const gridTitles = ['Request throughput (req/s)','TTFT p50 (ms)','E2E latency p50 (ms)','Error rate (%)'];
function renderGrid() {{
  const sub = gridKeys.map(k => {{ const f = FIGS[k]; return {{data:f.data, layout:Object.assign({{}}, f.layout,
      {{height:260, showlegend:false, title:{{text:''}}, margin:{{l:50,r:10,t:20,b:40}}}})}}; }});
  const container = document.getElementById('grid-chart');
  // Render as a single 2x2 subplot for simplicity.
  const rows = 2, cols = 2;
  const data = [];
  const layout = {{ grid:{{rows:rows, columns:cols, pattern:'independent'}}, height:560, margin:{{l:60,r:20,t:20,b:40}} }};
  gridKeys.forEach((k, idx) => {{
    const f = FIGS[k];
    f.data.forEach((tr, ti) => {{
      const tr2 = JSON.parse(JSON.stringify(tr));
      tr2.xaxis = 'x' + (idx+1); tr2.yaxis = 'y' + (idx+1);
      tr2.showlegend = (idx === 0 && ti === 0);
      tr2.name = tr.name;
      data.push(tr2);
    }});
    layout['xaxis' + (idx+1)] = {{title:'Concurrency', dtick:1}};
    layout['yaxis' + (idx+1)] = {{title:gridTitles[idx]}};
    layout['annotations'] = layout['annotations'] || [];
    layout['annotations'].push({{text:gridTitles[idx], xref:'x'+(idx+1)+' domain', yref:'y'+(idx+1)+' domain',
        x:0.5, y:1.15, showarrow:false, font:{{size:12}}}});
  }});
  Plotly.newPlot('grid-chart', data, layout, {{responsive:true}});
}}
renderMain();
renderGrid();
</script>
</body>
</html>
"""
    (DOCS / "index.html").write_text(html, encoding="utf-8")


def main():
    if not (RESULTS / "aggregate.tsv").exists():
        print(f"ERROR: {RESULTS}/aggregate.tsv not found. Curate results/final/ first.", file=sys.stderr)
        sys.exit(1)
    agg = load_aggregate()
    records = build_records(agg)
    if not records:
        print("ERROR: no 'model' suite records in aggregate.tsv", file=sys.stderr)
        sys.exit(1)

    write_benchmark_json(records)
    write_provenance(records)
    write_summary_md(records)
    write_model_comparison_md(records)
    write_static_charts(records)
    write_index_html(records)

    print("Report generation complete:")
    print(f"  results/final/provenance.json")
    print(f"  results/final/summary.md")
    print(f"  results/final/model_comparison.md")
    print(f"  docs/data/benchmark.json")
    print(f"  docs/index.html")
    print(f"  docs/assets/*.svg ({len(list(ASSETS_DIR.glob('*.svg')))} charts)")


if __name__ == "__main__":
    main()
