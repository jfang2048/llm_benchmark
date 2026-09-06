#!/usr/bin/env python3
"""Current-benchmark dashboard generator.

Reads the 8-9B cohort registry (configs/models.json) plus the curated results
under results/current/ and renders a single self-contained HTML dashboard with
no external CDN dependencies. Model names, parameter counts, quantization and
licenses come from the registry; suite tables come from the machine-readable
TSVs. FAILED / UNSTABLE cells are marked explicitly and never presented as
valid ranking points.

Usage:
    python3 scripts/generate_current_report.py [--out docs/current/index.html]
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
PALETTE = ["#3a7bd5", "#e07b39", "#2fa36b", "#8e44ad", "#c0392b", "#16a085"]


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def load_tsv(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def registry_meta():
    meta = {}
    for m in config.models():
        if m.get("cohort") != "mainstream_8_9b":
            continue
        meta[m["arm"]] = m
    return meta


def manifest():
    p = RESULT_ROOT / "capacity" / "manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def html_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def capacity_view(meta):
    rows = load_tsv(RESULT_ROOT / "capacity" / "aggregate.tsv")
    out = []
    for r in rows:
        if r.get("suite") != "capacity":
            continue
        arm = r["arm"]
        m = meta.get(arm, {})
        out.append({
            "model": m.get("display_name", arm),
            "concurrency": int(r["concurrency"]),
            "ttft_p50": _num(r.get("ttft_p50_ms_mean")),
            "lat_p50": _num(r.get("latency_p50_ms_mean")),
            "lat_p95": _num(r.get("latency_p95_ms_mean")),
            "output_tps": _num(r.get("output_tps_mean")),
            "vram": _num(r.get("peak_vram_mib_mean")),
            "pass_runs": int(r.get("pass_runs") or 0),
            "unstable_runs": int(r.get("unstable_runs") or 0),
            "failed_runs": int(r.get("failed_runs") or 0),
        })
    return out


def repeats_view():
    return load_tsv(RESULT_ROOT / "capacity" / "repeats.tsv")


def reliability_view():
    return load_tsv(RESULT_ROOT / "reliability" / "reliability.tsv")


def model_table(meta, manifest):
    rows = []
    for arm, m in sorted(meta.items(), key=lambda kv: kv[1].get("port", 0)):
        pc = m.get("actual_parameter_count")
        rows.append(
            f"<tr><td>{html_escape(m.get('display_name', arm))}</td>"
            f"<td>{html_escape(m.get('upstream_repo', ''))}</td>"
            f"<td>{pc / 1e9:.2f}B</td>"
            f"<td>{html_escape(m.get('quantization', ''))}</td>"
            f"<td>{html_escape(m.get('license', '') or '')}</td></tr>"
        )
    engine = manifest.get("engine", "")
    gpu = manifest.get("gpu", "")
    return f"""
    <h2>Models</h2>
    <table><thead><tr><th>Model</th><th>Upstream</th><th>Params</th>
    <th>Quant</th><th>License</th></tr></thead><tbody>
    {''.join(rows)}</tbody></table>
    <p class="meta">Engine: {html_escape(engine)} &middot; GPU: {html_escape(gpu)}</p>
    """


def capacity_table(cells):
    if not cells:
        return "<h2>Capacity</h2><p>No capacity data yet.</p>"
    models = sorted({c["model"] for c in cells})
    concs = sorted({c["concurrency"] for c in cells})
    head = "".join(f"<th>c={c}</th>" for c in concs)
    body = []
    for model in models:
        tts = []
        for c in concs:
            cell = next((x for x in cells
                         if x["model"] == model and x["concurrency"] == c), None)
            if cell is None:
                tts.append("<td>-</td>")
                continue
            if cell["failed_runs"] > 0:
                tts.append('<td class="fail">FAIL</td>')
            elif cell["unstable_runs"] > 0:
                tts.append('<td class="unstable">UNSTABLE</td>')
            elif cell["pass_runs"] == 0:
                tts.append('<td class="excluded">EXCLUDED</td>')
            else:
                tts.append(f"<td>{cell['ttft_p50']:.1f} ms</td>")
        body.append(f"<tr><td>{html_escape(model)}</td>{''.join(tts)}</tr>")
    return (f"<h2>Capacity &mdash; TTFT p50 (ms) vs concurrency</h2>"
            f"<table><thead><tr><th>Model</th>{head}</tr></thead><tbody>"
            f"{''.join(body)}</tbody></table>")


def output_tps_table(cells):
    if not cells:
        return ""
    models = sorted({c["model"] for c in cells})
    concs = sorted({c["concurrency"] for c in cells})
    head = "".join(f"<th>c={c}</th>" for c in concs)
    body = []
    for model in models:
        tds = []
        for c in concs:
            cell = next((x for x in cells
                         if x["model"] == model and x["concurrency"] == c), None)
            if cell and cell["output_tps"] is not None and cell["failed_runs"] == 0:
                tds.append(f"<td>{cell['output_tps']:.1f}</td>")
            else:
                tds.append('<td class="fail">-</td>')
        body.append(f"<tr><td>{html_escape(model)}</td>{''.join(tds)}</tr>")
    return (f"<h2>Capacity &mdash; output tokens/s vs concurrency</h2>"
            f"<table><thead><tr><th>Model</th>{head}</tr></thead><tbody>"
            f"{''.join(body)}</tbody></table>")


def capacity_chart(cells):
    if not cells:
        return ""
    models = sorted({c["model"] for c in cells})
    concs = sorted({c["concurrency"] for c in cells})
    max_tps = max((c["output_tps"] for c in cells
                   if c["output_tps"] is not None), default=1) or 1
    w, h = 720, 360
    px = lambda c: 60 + (c - concs[0]) / max(concs[-1] - concs[0], 1) * (w - 100)
    py = lambda v: h - 40 - (v / max_tps) * (h - 70)
    polylines = []
    for i, model in enumerate(models):
        pts = []
        for c in concs:
            cell = next((x for x in cells
                         if x["model"] == model and x["concurrency"] == c), None)
            if cell and cell["output_tps"] is not None:
                pts.append(f"{px(c):.0f},{py(cell['output_tps']):.0f}")
        if pts:
            polylines.append(
                f'<polyline fill="none" stroke="{PALETTE[i % len(PALETTE)]}" '
                f'stroke-width="2" points="{" ".join(pts)}"/>')
    xlabels = "".join(
        f'<text x="{px(c):.0f}" y="{h - 12}" font-size="11" text-anchor="middle">{c}</text>'
        for c in concs)
    legend = "".join(
        f'<text x="80" y="{20 + i * 16}" font-size="11" fill="{PALETTE[i % len(PALETTE)]}">{html_escape(m)}</text>'
        for i, m in enumerate(models))
    return (f'<h2>Capacity &mdash; throughput curve</h2>'
            f'<svg viewBox="0 0 {w} {h}" style="max-width:760px">'
            f'<line x1="60" y1="{h - 40}" x2="{w - 40}" y2="{h - 40}" stroke="#666"/>'
            f'<line x1="60" y1="30" x2="60" y2="{h - 40}" stroke="#666"/>'
            f'{xlabels}{legend}{"".join(polylines)}</svg>')


def reliability_table(rows):
    if not rows:
        return "<h2>Reliability</h2><p>No reliability data yet.</p>"
    body = []
    for r in rows:
        body.append(
            f"<tr><td>{html_escape(r['arm'])}</td><td>{r['concurrency']}</td>"
            f"<td>{r['attempted']}</td><td>{r['successful']}</td>"
            f"<td>{r['failed']}</td><td>{r['success_rate_pct']}%</td>"
            f"<td>[{r['wilson_low_pct']}, {r['wilson_high_pct']}]</td>"
            f"<td>{html_escape(r.get('error_types', ''))}</td></tr>")
    return (f"<h2>Reliability (Wilson 95% CI)</h2>"
            f"<table><thead><tr><th>Model</th><th>Concurrency</th>"
            f"<th>Attempted</th><th>Successful</th><th>Failed</th>"
            f"<th>Success %</th><th>Wilson 95% CI</th><th>Errors</th>"
            f"</tr></thead><tbody>{''.join(body)}</tbody></table>")


def repeats_table(rows):
    if not rows:
        return ""
    body = []
    for r in rows:
        cls = ""
        if r.get("status") == "FAIL_AIPERF":
            cls = ' class="fail"'
        elif r.get("status") == "UNSTABLE":
            cls = ' class="unstable"'
        body.append(
            f"<tr{cls}><td>{html_escape(r.get('arm'))}</td>"
            f"<td>{r.get('concurrency')}</td><td>{r.get('repeat')}</td>"
            f"<td>{r.get('status')}</td>"
            f"<td>{r.get('ttft_p50_ms') or '-'}</td>"
            f"<td>{r.get('latency_p50_ms') or '-'}</td>"
            f"<td>{r.get('output_tps') or '-'}</td>"
            f"<td>{r.get('peak_vram_mib') or '-'}</td>"
            f"<td>{r.get('successful_requests')}/{r.get('attempted_requests')}</td></tr>")
    return (f"<h2>Capacity &mdash; raw repeats</h2>"
            f"<table><thead><tr><th>Model</th><th>c</th><th>rep</th>"
            f"<th>status</th><th>TTFT p50</th><th>lat p50</th><th>out t/s</th>"
            f"<th>VRAM</th><th>ok/total</th></tr></thead><tbody>"
            f"{''.join(body)}</tbody></table>")


def shape_view():
    rows = load_tsv(RESULT_ROOT / "shape" / "aggregate.tsv")
    out = []
    for r in rows:
        if not r.get("suite", "").startswith("shape_"):
            continue
        profile = r["suite"][len("shape_"):]
        failed = int(r.get("failed_runs") or 0)
        unstable = int(r.get("unstable_runs") or 0)
        passed = int(r.get("pass_runs") or 0)
        if failed > 0:
            status = "FAIL"
        elif unstable > 0:
            status = "UNSTABLE"
        elif passed == 0:
            status = "EXCLUDED"
        else:
            status = "PASS"
        out.append({
            "profile": profile, "arm": r["arm"],
            "concurrency": r["concurrency"], "status": status,
            "ttft_p50": _num(r.get("ttft_p50_ms_mean")),
            "lat_p50": _num(r.get("latency_p50_ms_mean")),
            "output_tps": _num(r.get("output_tps_mean")),
        })
    return out


def shape_table(rows):
    if not rows:
        return "<h2>Workload shape</h2><p>No shape data yet.</p>"
    order = config.shape_order()
    profiles = [p for p in order if any(r["profile"] == p for r in rows)]
    profiles += sorted({r["profile"] for r in rows if r["profile"] not in order})
    arms = sorted({r["arm"] for r in rows})
    body = []
    for arm in arms:
        for c in sorted({r["concurrency"] for r in rows}):
            cells = []
            for p in profiles:
                cell = next((x for x in rows
                             if x["arm"] == arm and x["profile"] == p
                             and x["concurrency"] == c), None)
                if cell is None:
                    cells.append("<td>-</td>")
                elif cell["status"] == "PASS":
                    cells.append(f"<td>{cell['ttft_p50']:.0f} ms</td>")
                else:
                    cells.append(f'<td class="fail">{cell["status"]}</td>')
            body.append(f"<tr><td>{html_escape(arm)}</td><td>c={c}</td>"
                        f"{''.join(cells)}</tr>")
    head = "".join(f"<th>{html_escape(p)}</th>" for p in profiles)
    return (f"<h2>Workload shape &mdash; TTFT p50 (ms) by ISL/OSL profile</h2>"
            f"<table><thead><tr><th>Model</th><th>Concurrency</th>{head}</tr>"
            f"</thead><tbody>{''.join(body)}</tbody></table>"
            f"<p class='meta'>Profiles: short_chat 128/128, balanced 256/256, "
            f"summarization 512/128, rag_medium 768/128, generation 128/512. "
            f"rag_medium is marked UNSTABLE/TIMEOUT for models that dropped "
            f"streams at ISL 768.</p>")


def build_html(meta, manifest):
    cells = capacity_view(meta)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local LLM Inference Benchmark &mdash; Mainstream 8-9B</title>
<style>
body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; color: #222; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: .3rem; }}
h2 {{ margin-top: 2rem; }}
table {{ border-collapse: collapse; margin: .5rem 0 1.5rem; font-size: .9rem; }}
th, td {{ border: 1px solid #ccc; padding: .35rem .6rem; text-align: right; }}
th {{ background: #f2f2f2; }}
td:first-child, th:first-child {{ text-align: left; }}
.fail {{ background: #fdecea; color: #b3261e; font-weight: 600; }}
.unstable {{ background: #fff4e5; color: #b26a00; font-weight: 600; }}
.excluded {{ background: #eee; color: #777; }}
.meta {{ color: #555; font-size: .85rem; }}
</style></head><body>
<h1>Local LLM Inference Benchmark &mdash; Mainstream 8-9B</h1>
<p class="meta">Fixed-hardware deployment benchmark: RTX 3060 Laptop (6 GiB),
llama.cpp pinned upstream, IQ4_XS, identical serving policy across models.</p>
{model_table(meta, manifest)}
{capacity_table(cells)}
{output_tps_table(cells)}
{capacity_chart(cells)}
{repeats_table(repeats_view())}
{shape_table(shape_view())}
{reliability_table(reliability_view())}
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "docs" / "index.html"))
    args = ap.parse_args()
    meta = registry_meta()
    html = build_html(meta, manifest())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html)} bytes, {len(meta)} models)")


if __name__ == "__main__":
    main()
