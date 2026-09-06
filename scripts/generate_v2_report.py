#!/usr/bin/env python3
"""Benchmark v2 report generator.

Reads Benchmark v2 run data under results/v2/runs/ (one directory per run,
each carrying a manifest.json with its mode) and regenerates:

    docs/data/v2_benchmark.json   normalized v2 records
    docs/v2/index.html            interactive Plotly dashboard (static)

Views, in order:
    1. Capacity curve   — throughput + error rate vs concurrency
    2. Shape sweep      — ISL/OSL scatter (token-shape workload)
    3. Open-loop SLO    — goodput / SLO compliance vs load
    4. Session latency  — TTFT by turn number
    5. Pareto / energy  — throughput vs energy-per-output-token

Run validity is surfaced explicitly: pass / unstable / failed run counts come
straight from the aggregate tables, never inferred from a successful parse.

Usage:
    python3 scripts/generate_v2_report.py [--runs results/v2/runs] [--out docs/v2]

Requires plotly (see requirements-report.txt). Run inside the project venv.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bench.config import shape_profiles  # noqa: E402  (canonical config)

RUNS = ROOT / "results" / "v2" / "runs"
FINAL_RUNS = ROOT / "results" / "v2" / "final"
DOCS = ROOT / "docs" / "history" / "v2"
DATA_DIR = DOCS / "data"

ARM_LABELS = {
    "spark_llama": "Spark-X2.5-4B (llama.cpp)",
    "qwen_llama": "Qwen3-4B (llama.cpp)",
    "qwen_vllm_gguf": "Qwen3-4B (vLLM+GGUF)",
}
ARM_COLORS = {
    "spark_llama": "#e07b39",
    "qwen_llama": "#3a7bd5",
    "qwen_vllm_gguf": "#2fa36b",
}

# Token-shape profiles come from the canonical config (configs/benchmark.json)
# so the report cannot drift from scripts/benchmark.sh.
SHAPE_PROFILES = shape_profiles()


def _num(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if s in ("", "NA", "nan", "None"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def read_tsv(path):
    if not Path(path).exists():
        return []
    return list(csv.DictReader(open(path, encoding="utf-8"), delimiter="\t"))


def discover_runs(base):
    """Return {mode: run_dir} using the latest run directory per mode."""
    runs = {}
    for manifest in sorted(Path(base).glob("*/manifest.json")):
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        mode = m.get("mode")
        if mode:
            runs[mode] = manifest.parent
    return runs


# ---------------------------------------------------------------------------
# Data loaders — each returns a small normalized dict for the JSON payload.
# ---------------------------------------------------------------------------
def load_capacity(run_dir):
    agg = [r for r in read_tsv(run_dir / "aggregate.tsv") if r["suite"] == "capacity"]
    out = []
    for r in agg:
        out.append({
            "arm": r["arm"],
            "concurrency": int(_num(r["concurrency"]) or 0),
            "pass_runs": int(_num(r["pass_runs"]) or 0),
            "unstable_runs": int(_num(r["unstable_runs"]) or 0),
            "failed_runs": int(_num(r["failed_runs"]) or 0),
            "request_tps": _num(r.get("request_tps_mean")),
            "error_rate_pct": _num(r.get("error_rate_pct_mean")),
            "ttft_p50_ms": _num(r.get("ttft_p50_ms_mean")),
        })
    return out


def load_shape(run_dir):
    agg = [r for r in read_tsv(run_dir / "aggregate.tsv") if r["suite"].startswith("shape_")]
    out = []
    for r in agg:
        profile = r["suite"].replace("shape_", "")
        # ISL is taken from the data (what was actually run); OSL is not recorded
        # per-cell in aggregate.tsv, so it comes from the canonical config.
        isl = _num(r["isl"])
        osl = SHAPE_PROFILES.get(profile, (None, None))[1]
        out.append({
            "arm": r["arm"],
            "profile": profile,
            "isl": int(isl or 0),
            "osl": int(osl or 0),
            "output_tps": _num(r.get("output_tps_mean")),
            "ttft_p50_ms": _num(r.get("ttft_p50_ms_mean")),
            "itl_p95_ms": _num(r.get("itl_p95_ms_mean")),
        })
    return out


def load_openloop(run_dir):
    rows = read_tsv(run_dir / "slo_summary.tsv")
    out = []
    for r in rows:
        out.append({
            "arm": r["arm"],
            "load_fraction": _num(r["load_fraction"]) or _num(r["target_rate_rps"]) or 0,
            "target_rate_rps": _num(r["target_rate_rps"]),
            "slo_profile": r["slo_profile"],
            "attempted": int(_num(r["attempted"]) or 0),
            "slo_compliant": int(_num(r["slo_compliant"]) or 0),
            "good_request_fraction": _num(r["good_request_fraction"]),
        })
    return out


def load_sessions(run_dir):
    rows = read_tsv(run_dir / "sessions.tsv")
    out = []
    for r in rows:
        if r.get("cache_prompt", "false") != "false":
            continue  # no-cache comparison only; cache experiment is separate
        out.append({
            "arm": r["arm"],
            "turn": int(_num(r["turn"]) or 0),
            "requests": int(_num(r["requests"]) or 0),
            "ttft_mean_ms": _num(r["ttft_mean_ms"]),
            "ttft_p50_ms": _num(r["ttft_p50_ms"]),
        })
    return out


def load_pareto(run_dir):
    """Efficiency frontier from per-cell repeats (throughput vs energy)."""
    rows = [r for r in read_tsv(run_dir / "repeats.tsv")
            if r.get("suite") in ("capacity", "model", "backend")]
    out = []
    for r in rows:
        tps = _num(r.get("output_tps"))
        jpt = _num(r.get("gpu_j_per_output_token"))
        if tps is None or jpt is None:
            continue
        out.append({
            "arm": r["arm"],
            "concurrency": int(_num(r["concurrency"]) or 0),
            "output_tps": tps,
            "gpu_j_per_output_token": jpt,
        })
    return out


def load_soak(run_dir):
    rows = read_tsv(run_dir / "soak_summary.tsv")
    out = []
    for r in rows:
        out.append({
            "arm": r["arm"],
            "temp_max_c": _num(r.get("temp_max_c")),
            "power_max_w": _num(r.get("power_max_w")),
            "util_max_pct": _num(r.get("util_max_pct")),
            "throttled": r.get("throttled"),
        })
    return out


def load_startup(run_dir):
    rows = read_tsv(run_dir / "startup.tsv")
    out = []
    for r in rows:
        out.append({
            "arm": r["arm"],
            "first_token_ms": _num(r.get("first_token_ms")),
            "load_ms": _num(r.get("load_ms")),
        })
    return out


def arm_label(arm):
    return ARM_LABELS.get(arm, arm)


def arm_color(arm):
    return ARM_COLORS.get(arm, "#888")


# ---------------------------------------------------------------------------
# Plotly figures
# ---------------------------------------------------------------------------
def fig_capacity(records):
    import plotly.graph_objects as go
    fig = go.Figure()
    for arm in sorted({r["arm"] for r in records}):
        pts = sorted([r for r in records if r["arm"] == arm], key=lambda r: r["concurrency"])
        fig.add_trace(go.Scatter(
            x=[p["concurrency"] for p in pts],
            y=[p["request_tps"] for p in pts],
            mode="lines+markers", name=f"{arm_label(arm)} — throughput",
            line=dict(color=arm_color(arm), width=2.5),
            yaxis="y1",
            hovertemplate="%{y:.3f} req/s<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[p["concurrency"] for p in pts],
            y=[p["error_rate_pct"] for p in pts],
            mode="lines+markers", name=f"{arm_label(arm)} — error rate",
            line=dict(color=arm_color(arm), width=2, dash="dot"),
            yaxis="y2",
            hovertemplate="%{y:.2f}%<extra></extra>",
        ))
    fig.update_layout(
        title="Capacity curve — throughput and error rate vs concurrency",
        xaxis=dict(title="Concurrency", dtick=1, gridcolor="#eee"),
        yaxis=dict(title="Request throughput (req/s)", gridcolor="#eee", zeroline=False),
        yaxis2=dict(title="Error rate (%)", overlaying="y", side="right", gridcolor="#eee",
                    showgrid=False, zeroline=False),
        template="plotly_white", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def fig_shape(records):
    import plotly.graph_objects as go
    fig = go.Figure()
    for arm in sorted({r["arm"] for r in records}):
        pts = [r for r in records if r["arm"] == arm]
        fig.add_trace(go.Scatter(
            x=[p["isl"] for p in pts], y=[p["osl"] for p in pts],
            mode="markers+text", name=arm_label(arm),
            text=[p["profile"] for p in pts], textposition="top center",
            marker=dict(size=[max(10, (p["output_tps"] or 0) * 0.4) for p in pts],
                        color=arm_color(arm), opacity=0.75),
            hovertemplate=("<b>%{text}</b><br>ISL=%{x}<br>OSL=%{y}<br>"
                           "output_tps=%{customdata:.1f}<extra></extra>"),
            customdata=[p["output_tps"] or 0 for p in pts],
        ))
    fig.update_layout(
        title="Token-shape sweep — ISL vs OSL (marker size = output throughput)",
        xaxis=dict(title="Input sequence length (tokens)", type="log",
                   gridcolor="#eee"),
        yaxis=dict(title="Output sequence length (tokens)", type="log",
                   gridcolor="#eee"),
        template="plotly_white", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def fig_openloop(records):
    import plotly.graph_objects as go
    fig = go.Figure()
    profiles = sorted({r["slo_profile"] for r in records})
    for arm in sorted({r["arm"] for r in records}):
        for profile in profiles:
            pts = sorted([r for r in records
                          if r["arm"] == arm and r["slo_profile"] == profile],
                         key=lambda r: r["load_fraction"])
            if not pts:
                continue
            fig.add_trace(go.Scatter(
                x=[p["target_rate_rps"] for p in pts],
                y=[p["good_request_fraction"] for p in pts],
                mode="lines+markers", name=f"{arm_label(arm)} · {profile}",
                line=dict(color=arm_color(arm), width=2,
                          dash="solid" if profile == "interactive" else "dash"),
                hovertemplate="rate=%{x:.2f} req/s<br>SLO-compliant=%{y:.2f}<extra></extra>",
            ))
    fig.update_layout(
        title="Open-loop SLO compliance vs offered load (Poisson)",
        xaxis=dict(title="Offered request rate (req/s)", gridcolor="#eee"),
        yaxis=dict(title="SLO-compliant fraction", range=[0, 1.05], gridcolor="#eee"),
        template="plotly_white", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def fig_sessions(records):
    import plotly.graph_objects as go
    fig = go.Figure()
    for arm in sorted({r["arm"] for r in records}):
        pts = sorted([r for r in records if r["arm"] == arm], key=lambda r: r["turn"])
        fig.add_trace(go.Scatter(
            x=[p["turn"] for p in pts], y=[p["ttft_mean_ms"] for p in pts],
            mode="lines+markers", name=arm_label(arm),
            line=dict(color=arm_color(arm), width=2.5),
            marker=dict(size=9),
            hovertemplate="turn=%{x}<br>TTFT mean=%{y:.1f} ms<extra></extra>",
        ))
    fig.update_layout(
        title="Session latency by turn (multi-turn, cache_prompt=false)",
        xaxis=dict(title="Turn index (0 = first user turn)", dtick=1, gridcolor="#eee"),
        yaxis=dict(title="TTFT mean (ms)", gridcolor="#eee", zeroline=False),
        template="plotly_white", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def fig_pareto(records):
    import plotly.graph_objects as go
    fig = go.Figure()
    for arm in sorted({r["arm"] for r in records}):
        pts = [r for r in records if r["arm"] == arm]
        fig.add_trace(go.Scatter(
            x=[p["gpu_j_per_output_token"] for p in pts],
            y=[p["output_tps"] for p in pts],
            mode="markers", name=arm_label(arm),
            marker=dict(color=arm_color(arm), size=10, opacity=0.8),
            hovertemplate="energy=%{x:.3f} J/tok<br>throughput=%{y:.1f} tok/s<extra></extra>",
        ))
    fig.update_layout(
        title="Pareto frontier — throughput vs GPU-side energy per output token",
        xaxis=dict(title="GPU energy per output token (J/tok, estimate)", gridcolor="#eee"),
        yaxis=dict(title="Output token throughput (tok/s)", gridcolor="#eee",
                   zeroline=False),
        template="plotly_white", height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def fig_validity(records):
    """Pass / unstable / failed run counts per arm and concurrency (capacity)."""
    import plotly.graph_objects as go
    arms = sorted({r["arm"] for r in records})
    concs = sorted({r["concurrency"] for r in records})
    data = []
    for arm in arms:
        for kind, color in (("pass_runs", "#2fa36b"), ("unstable_runs", "#d9a13c"),
                            ("failed_runs", "#c0392b")):
            vals = [next((r[kind] for r in records
                          if r["arm"] == arm and r["concurrency"] == c), 0)
                    for c in concs]
            data.append(go.Bar(name=f"{arm_label(arm)} · {kind.replace('_', ' ')}",
                               x=concs, y=vals, marker_color=color))
    fig = go.Figure(data=data)
    fig.update_layout(
        title="Run validity — pass / unstable / failed per concurrency",
        barmode="stack",
        xaxis=dict(title="Concurrency", dtick=1, gridcolor="#eee"),
        yaxis=dict(title="Runs", gridcolor="#eee"),
        template="plotly_white", height=360,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# ---------------------------------------------------------------------------
# Dashboard HTML
# ---------------------------------------------------------------------------
def write_dashboard(out_dir, figs):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig_json = {k: json.loads(f.to_json()) for k, f in figs.items()}

    sections = [
        ("capacity", "Capacity curve",
         "Closed-loop sweep: request throughput and error rate vs concurrency. "
         "Error rate is the hard gate — a faster arm with more failures is not better."),
        ("shape", "Token-shape sweep",
         "Synthetic token-controlled workload across ISL/OSL profiles. "
         "Marker size encodes output throughput; hover for exact values."),
        ("openloop", "Open-loop SLO / goodput",
         "Poisson offered load from 25% to 110% of stable capacity. "
         "SLO-compliant fraction under two reference profiles (interactive / server)."),
        ("sessions", "Session latency by turn",
         "Multi-turn conversations with growing context; TTFT by turn number "
         "(cache_prompt=false — no prefix-cache reuse)."),
        ("pareto", "Pareto / energy",
         "Throughput vs GPU-side energy per output token. Energy is an estimate "
         "integrated from 500 ms nvidia-smi sampling — not full-system, not MLPerf."),
        ("validity", "Run validity",
         "Stacked pass / unstable / failed run counts per concurrency. "
         "A parsed-but-unstable run is never counted as pass."),
    ]

    panels = "\n".join(
        f'<div class="chart" id="chart-{key}"></div>'
        f'<p class="note">{desc}</p>'
        for key, _title, desc in sections
    )
    nav = "\n".join(
        f'<button class="nav-btn" onclick="scrollToChart(\'{key}\')">{title}</button>'
        for key, title, _desc in sections
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Benchmark v2 — Interactive Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root {{ --bg:#0f1420; --panel:#171e2e; --text:#e6eaf2; --muted:#9aa4b8; --accent:#3a7bd5; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
         background:var(--bg); color:var(--text); }}
  header {{ padding:22px 28px; border-bottom:1px solid #232c40; }}
  header h1 {{ margin:0 0 4px; font-size:20px; }}
  header p {{ margin:0; color:var(--muted); font-size:13px; }}
  .banner {{ background:#12273a; border:1px solid #2a5a8a; border-radius:8px; padding:10px 14px;
            margin-top:10px; font-size:13px; }}
  .nav {{ padding:14px 28px; display:flex; gap:8px; flex-wrap:wrap; border-bottom:1px solid #232c40; }}
  .nav-btn {{ background:#1a2233; color:var(--text); border:1px solid #2a3550; border-radius:6px;
             padding:8px 12px; font-size:13px; cursor:pointer; }}
  .nav-btn:hover {{ background:#223048; }}
  .content {{ padding:22px 28px; max-width:1080px; }}
  .chart {{ background:var(--panel); border:1px solid #232c40; border-radius:10px;
            padding:10px; margin-bottom:6px; }}
  .note {{ color:var(--muted); font-size:12px; line-height:1.5; margin:0 0 26px; }}
</style>
</head>
<body>
<header>
  <h1>Benchmark v2 — Interactive Dashboard</h1>
  <p>Reliability-gated local LLM inference benchmark · llama.cpp · RTX 3060 Laptop GPU (6 GiB VRAM)</p>
  <div class="banner">
    <strong>Methodology:</strong> transport success &ge; 99.5% required before any ranking;
    latency is reported over successful requests only; pass / unstable / failed runs are
    distinguished explicitly. See <code>results/v2/README.md</code>.
  </div>
</header>
<div class="nav">{nav}</div>
<div class="content">
{panels}
</div>
<script>
const FIGS = {fig_json};
const KEYS = ['capacity','shape','openloop','sessions','pareto','validity'];
KEYS.forEach(k => {{
  if (FIGS[k]) {{ Plotly.newPlot('chart-' + k, FIGS[k].data, FIGS[k].layout, {{responsive:true}}); }}
}});
function scrollToChart(k) {{
  document.getElementById('chart-' + k).scrollIntoView({{behavior:'smooth'}});
}}
</script>
</body>
</html>
"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=None,
                    help="runs directory (default: results/v2/final if curated, else results/v2/runs)")
    ap.add_argument("--out", default=str(DOCS))
    args = ap.parse_args()

    runs_base = args.runs
    if runs_base is None:
        runs_base = str(FINAL_RUNS) if list(FINAL_RUNS.glob("*/manifest.json")) else str(RUNS)
    runs = discover_runs(runs_base)
    if not runs:
        print(f"NOTE: no v2 runs found under {runs_base} — skipping v2 dashboard.",
              file=sys.stderr)
        sys.exit(0)

    payload = {
        "schema_version": 1,
        "runs": {mode: str(d.name) for mode, d in sorted(runs.items())},
        "arm_labels": ARM_LABELS,
    }
    figs = {}

    # canonical dashboard key -> (manifest mode, loader, figure builder)
    loaders = {
        "capacity": ("capacity", load_capacity, fig_capacity),
        "shape": ("shape", load_shape, fig_shape),
        "openloop": ("open-loop", load_openloop, fig_openloop),
        "sessions": ("sessions", load_sessions, fig_sessions),
        "pareto": ("capacity", load_pareto, fig_pareto),
    }
    for key, (manifest_mode, loader, figfn) in loaders.items():
        run_dir = runs.get(manifest_mode)
        if run_dir is None and key == "pareto":
            run_dir = runs.get("backend")
        if run_dir is None:
            continue
        try:
            records = loader(run_dir)
        except Exception as e:
            print(f"WARN: could not load {key}: {e}", file=sys.stderr)
            continue
        if records:
            payload[key] = records
            figs[key] = figfn(records)

    # Run validity from the capacity run (or backend).
    cap_dir = runs.get("capacity") or runs.get("backend")
    if cap_dir:
        cap = load_capacity(cap_dir)
        if cap:
            payload["validity"] = cap
            figs["validity"] = fig_validity(cap)

    # Soak / startup are supplementary; include raw records if present.
    for mode in ("soak", "startup"):
        run_dir = runs.get(mode)
        if run_dir:
            loader = load_soak if mode == "soak" else load_startup
            records = loader(run_dir)
            if records:
                payload[mode] = records

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "v2_benchmark.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8")

    write_dashboard(args.out, figs)

    print("Benchmark v2 report generation complete:")
    print(f"  docs/data/v2_benchmark.json")
    print(f"  docs/v2/index.html")
    print(f"  views: {', '.join(sorted(figs))}")


if __name__ == "__main__":
    main()
