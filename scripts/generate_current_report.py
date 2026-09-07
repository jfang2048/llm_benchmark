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
# (filesystem dir, registry cohort) for the current cohorts.
COHORTS = [("mainstream-8-9b", "mainstream_8_9b"),
           ("spark-reference", "spark_reference")]
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
        if m.get("enabled") and m.get("cohort") in ("mainstream_8_9b", "spark_reference"):
            meta[m["arm"]] = m
    return meta


def is_reference(meta, arm):
    return meta.get(arm, {}).get("role") == "reference"


def disp(meta, arm):
    """Display name; the Spark reference is labeled, never ranked as 8-9B."""
    m = meta.get(arm, {})
    name = m.get("display_name", arm)
    if m.get("role") == "reference":
        return name + " (REFERENCE / 4B)"
    return name


def cohort_of(arm):
    for m in config.models():
        if m.get("arm") == arm:
            return "spark" if m.get("role") == "reference" else "mainstream"
    return "mainstream"


def _cohort_attr(cohort):
    return f' data-cohort="{cohort}"'


def load_suite(suite, *globs):
    """Load TSV rows from a suite across cohorts, tagged with cohort + role."""
    out = []
    for cohort_dir, cohort_name in COHORTS:
        base = RESULT_ROOT / cohort_dir / suite
        for g in globs:
            for p in base.glob(g):
                for r in load_tsv(p):
                    r = dict(r)
                    r["_cohort_dir"] = cohort_dir
                    r["_cohort"] = cohort_name
                    out.append(r)
    return out


def manifest():
    p = RESULT_ROOT / "mainstream-8-9b" / "capacity" / "manifest.json"
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
    rows = load_suite("capacity", "aggregate.tsv")
    out = []
    for r in rows:
        if r.get("suite") != "capacity":
            continue
        arm = r["arm"]
        out.append({
            "model": disp(meta, arm),
            "cohort": cohort_of(arm),
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
    return load_suite("capacity", "repeats.tsv")


def reliability_view():
    return load_suite("reliability", "reliability.tsv")


def model_table(meta, manifest):
    rows = []
    for arm, m in sorted(meta.items(), key=lambda kv: kv[1].get("port", 0)):
        pc = m.get("actual_parameter_count")
        role = "Reference (4B)" if m.get("role") == "reference" else "Primary (8-9B)"
        cls = ' class="ref"' if m.get("role") == "reference" else ""
        cohort = "spark" if m.get("role") == "reference" else "mainstream"
        rows.append(
            f"<tr{cls}{_cohort_attr(cohort)}><td>{html_escape(m.get('display_name', arm))}</td>"
            f"<td>{role}</td>"
            f"<td>{html_escape(m.get('upstream_repo', ''))}</td>"
            f"<td>{pc / 1e9:.2f}B</td>"
            f"<td>{html_escape(m.get('quantization', ''))}</td>"
            f"<td>{html_escape(m.get('license', '') or '')}</td></tr>"
        )
    engine = manifest.get("engine", "")
    gpu = manifest.get("gpu", "")
    return f"""
    <h2>Models</h2>
    <table><thead><tr><th>Model</th><th>Role</th><th>Upstream</th><th>Params</th>
    <th>Quant</th><th>License</th></tr></thead><tbody>
    {''.join(rows)}</tbody></table>
    <p class="meta">Engine: {html_escape(engine)} &middot; GPU: {html_escape(gpu)}</p>
    """


def capacity_table(cells):
    if not cells:
        return "<h2>Capacity</h2><p>No capacity data yet.</p>"
    models = sorted({c["model"] for c in cells})
    concs = sorted({c["concurrency"] for c in cells})
    model_cohort = {c["model"]: c["cohort"] for c in cells}
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
        body.append(f"<tr{_cohort_attr(model_cohort.get(model, 'mainstream'))}>"
                    f"<td>{html_escape(model)}</td>{''.join(tts)}</tr>")
    return (f"<h2>Capacity &mdash; TTFT p50 (ms) vs concurrency</h2>"
            f"<table><thead><tr><th>Model</th>{head}</tr></thead><tbody>"
            f"{''.join(body)}</tbody></table>")


def output_tps_table(cells):
    if not cells:
        return ""
    models = sorted({c["model"] for c in cells})
    concs = sorted({c["concurrency"] for c in cells})
    model_cohort = {c["model"]: c["cohort"] for c in cells}
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
        body.append(f"<tr{_cohort_attr(model_cohort.get(model, 'mainstream'))}>"
                    f"<td>{html_escape(model)}</td>{''.join(tds)}</tr>")
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


def reliability_table(rows, meta):
    if not rows:
        return "<h2>Reliability</h2><p>No reliability data yet.</p>"
    body = []
    for r in rows:
        body.append(
            f"<tr{_cohort_attr(cohort_of(r['arm']))}><td>{html_escape(disp(meta, r['arm']))}</td><td>{r['concurrency']}</td>"
            f"<td>{r['attempted']}</td><td>{r['successful']}</td>"
            f"<td>{r['failed']}</td><td>{r['success_rate_pct']}%</td>"
            f"<td>[{r['wilson_low_pct']}, {r['wilson_high_pct']}]</td>"
            f"<td>{html_escape(r.get('error_types', ''))}</td></tr>")
    return (f"<h2>Reliability (Wilson 95% CI)</h2>"
            f"<table><thead><tr><th>Model</th><th>Concurrency</th>"
            f"<th>Attempted</th><th>Successful</th><th>Failed</th>"
            f"<th>Success %</th><th>Wilson 95% CI</th><th>Errors</th>"
            f"</tr></thead><tbody>{''.join(body)}</tbody></table>")


def repeats_table(rows, meta):
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
            f"<tr{cls}{_cohort_attr(cohort_of(r.get('arm')))}><td>{html_escape(disp(meta, r.get('arm'))) }</td>"
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
    rows = load_suite("shape", "aggregate.tsv")
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


def shape_table(rows, meta):
    if not rows:
        return "<h2>Workload shape</h2><p>No shape data yet.</p>"
    order = config.shape_order()
    profiles = [p for p in order if any(r["profile"] == p for r in rows)]
    profiles += sorted({r["profile"] for r in rows if r["profile"] not in order})
    arms = sorted({r["arm"] for r in rows})
    body = []
    for arm in arms:
        name = disp(meta, arm)
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
            body.append(f"<tr{_cohort_attr(cohort_of(arm))}><td>{html_escape(name)}</td><td>c={c}</td>"
                        f"{''.join(cells)}</tr>")
    head = "".join(f"<th>{html_escape(p)}</th>" for p in profiles)
    return (f"<h2>Workload shape &mdash; TTFT p50 (ms) by ISL/OSL profile</h2>"
            f"<table><thead><tr><th>Model</th><th>Concurrency</th>{head}</tr>"
            f"</thead><tbody>{''.join(body)}</tbody></table>"
            f"<p class='meta'>Profiles: short_chat 128/128, balanced 256/256, "
            f"summarization 512/128, rag_medium 768/128, generation 128/512. "
            f"rag_medium is marked UNSTABLE/TIMEOUT for models that dropped "
            f"streams at ISL 768.</p>")


def startup_table(meta):
    rows = load_suite("startup", "startup.tsv")
    if not rows:
        return ""
    by_arm = {}
    for r in rows:
        v = _num(r.get("cold_start_ms"))
        if v is not None:
            by_arm.setdefault(r["arm"], []).append(v)
    body = []
    for arm, vals in sorted(by_arm.items()):
        mean = sum(vals) / len(vals)
        name = disp(meta, arm)
        body.append(f"<tr{_cohort_attr(cohort_of(arm))}><td>{html_escape(name)}</td>"
                    f"<td>{min(vals):.0f}</td><td>{mean:.0f}</td>"
                    f"<td>{max(vals):.0f}</td></tr>")
    return (f"<h2>Startup &mdash; cold start to first token (ms)</h2>"
            f"<table><thead><tr><th>Model</th><th>min</th><th>mean</th>"
            f"<th>max</th></tr></thead><tbody>{''.join(body)}</tbody></table>"
            f"<p class='meta'>First repeat is slower (cold CUDA graph compile).</p>")


def openloop_table(meta):
    rows = load_suite("open-loop", "aggregate.tsv")
    if not rows:
        return ""
    arms = sorted({r["arm"] for r in rows})
    fracs = sorted({r["isl"] for r in rows}, key=lambda x: float(x))
    head = "".join(f"<th>{f}</th>" for f in fracs)
    body = []
    for arm in arms:
        name = disp(meta, arm)
        tds = []
        for f in fracs:
            r = next((x for x in rows if x["arm"] == arm and x["isl"] == f), None)
            if r:
                tds.append(f"<td>{_num(r.get('request_tps_mean')):.2f}</td>")
            else:
                tds.append("<td>-</td>")
        body.append(f"<tr{_cohort_attr(cohort_of(arm))}><td>{html_escape(name)}</td>{''.join(tds)}</tr>")
    return (f"<h2>Open-loop &mdash; achieved goodput (req/s) vs load fraction</h2>"
            f"<table><thead><tr><th>Model</th><th>load fraction x capacity</th></tr>"
            f"<tr><th></th>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
            f"</table><p class='meta'>Offered Poisson load as a fraction of each "
            f"model's measured stable capacity; achieved throughput below the "
            f"fraction near/above 1.0 shows saturation.</p>")


def sessions_table(meta):
    rows = load_suite("sessions", "aggregate.tsv")
    if not rows:
        return ""
    body = []
    for arm in sorted({r["arm"] for r in rows}):
        name = disp(meta, arm)
        nc = next((r for r in rows if r["arm"] == arm and r["isl"] == "nocache"), None)
        ca = next((r for r in rows if r["arm"] == arm and r["isl"] == "cache"), None)
        body.append(
            f"<tr{_cohort_attr(cohort_of(arm))}><td>{html_escape(name)}</td>"
            f"<td>{_num(nc['ttft_p50_ms_mean']) if nc else ''}</td>"
            f"<td>{_num(ca['ttft_p50_ms_mean']) if ca else ''}</td>"
            f"<td>{_num(nc['itl_p50_ms_mean']) if nc else ''}</td>"
            f"<td>{_num(ca['itl_p50_ms_mean']) if ca else ''}</td></tr>")
    return (f"<h2>Sessions &mdash; multi-turn TTFT/ITL p50 (ms), 3 turns</h2>"
            f"<table><thead><tr><th>Model</th><th>TTFT nocache</th>"
            f"<th>TTFT cache</th><th>ITL nocache</th><th>ITL cache</th></tr>"
            f"</thead><tbody>{''.join(body)}</tbody></table>"
            f"<p class='meta'>cache_prompt=true avoids re-prefilling the "
            f"conversation history, reducing per-turn TTFT.</p>")


def build_html(meta, manifest):
    cells = capacity_view(meta)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Local LLM Inference Benchmark</title>
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
.ref {{ background: #f3f6fb; }}
.badge {{ display: inline-block; font-size: .72rem; padding: .1rem .45rem;
         border-radius: 3px; background: #3a7bd5; color: #fff; vertical-align: middle; }}
.meta {{ color: #555; font-size: .85rem; }}
.filter {{ margin: 1rem 0; font-size: .9rem; }}
</style></head><body>
<h1>Local LLM Inference Benchmark</h1>
<p class="meta">Fixed-hardware deployment benchmark on RTX 3060 Laptop (6 GiB).
Primary cohort: 4 mainstream 8-9B models, same pinned upstream llama.cpp,
IQ4_XS, identical serving policy. <span class="badge">REFERENCE / 4B</span>
marks Spark-X2.5-4B, a fixed-hardware reference baseline served on the
XHToken llama.cpp fork (Q4_K_M); it is never ranked against the 8-9B cohort.</p>
<div class="filter">Cohort:
<select id="cohortFilter" onchange="applyFilter()">
<option value="all">All</option>
<option value="mainstream">Mainstream 8-9B</option>
<option value="spark">Spark reference</option>
</select></div>
{model_table(meta, manifest)}
{capacity_table(cells)}
{output_tps_table(cells)}
{capacity_chart(cells)}
{repeats_table(repeats_view(), meta)}
{shape_table(shape_view(), meta)}
{openloop_table(meta)}
{startup_table(meta)}
{sessions_table(meta)}
{reliability_table(reliability_view(), meta)}
<script>
function applyFilter() {{
  const v = document.getElementById('cohortFilter').value;
  document.querySelectorAll('tr[data-cohort]').forEach(tr => {{
    tr.style.display = (v === 'all' || tr.dataset.cohort === v) ? '' : 'none';
  }});
}}
</script>
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
