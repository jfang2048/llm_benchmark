/* Local LLM Inference Benchmark — interactive dashboard.
 * Static: reads the embedded JSON dataset, renders with Plotly (plotly.min.js).
 * Every value comes from docs/data/current.json (generated). */
"use strict";

const RAW = document.getElementById("bench-data").textContent;
const D = JSON.parse(RAW);

const STATUS_COLOR = {
  PASS: "#2e7d32", UNSTABLE: "#f9a825", FAIL: "#c62828",
  TIMEOUT: "#c62828", EXCLUDED: "#9e9e9e",
};
const STATUS_SYMBOL = {
  PASS: "circle", UNSTABLE: "diamond", FAIL: "x", TIMEOUT: "x", EXCLUDED: "circle-open",
};

const modelByArm = {};
D.models.forEach((m) => { modelByArm[m.arm] = m; });

const state = {
  cohort: "all",
  models: new Set(D.models.map((m) => m.arm)),
  percentile: "p50",
  shapeMetric: "ttft_p50",
  shapeConcurrency: "all",
};

function m(arm) { return modelByArm[arm] || {}; }
function visible(arm) {
  const mm = m(arm);
  if (!state.models.has(arm)) return false;
  if (state.cohort === "mainstream" && mm.cohort !== "mainstream_8_9b") return false;
  if (state.cohort === "spark" && mm.cohort !== "spark_reference") return false;
  return true;
}
function name(arm) {
  const mm = m(arm);
  return mm.is_reference ? mm.display_name + " (REFERENCE / 4B)" : mm.display_name;
}
function color(arm) { return m(arm).color || "#888"; }
function dashFor(arm) { return m(arm).is_reference ? "dash" : "solid"; }
function markerFor(arm) { return m(arm).is_reference ? "circle-open" : "circle"; }
function shortName(arm) {
  const n = name(arm);
  return n.replace(" (REFERENCE / 4B)", " (ref)");
}

function fmt(v, d = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(d);
}

const BASE_LAYOUT = {
  paper_bgcolor: "#ffffff", plot_bgcolor: "#ffffff",
  font: { family: "-apple-system, Segoe UI, Roboto, sans-serif", size: 12, color: "#1f2933" },
  margin: { l: 60, r: 20, t: 30, b: 48 },
  hoverlabel: { bgcolor: "#ffffff", bordercolor: "#cbd5e1", font: { size: 12 } },
  legend: { orientation: "h", y: 1.08, x: 0, bgcolor: "rgba(0,0,0,0)" },
};
function axisGrid(axis) {
  axis.showgrid = true; axis.gridcolor = "#eef1f4"; axis.zeroline = false;
  axis.linecolor = "#cbd5e1"; axis.tickfont = { size: 11 };
  return axis;
}
function baseLayout(title, x, y) {
  const l = JSON.parse(JSON.stringify(BASE_LAYOUT));
  l.title = { text: title, font: { size: 14 }, x: 0, xanchor: "left" };
  l.xaxis = axisGrid({ title: { text: x, font: { size: 12 } }, automargin: true });
  l.yaxis = axisGrid({ title: { text: y, font: { size: 12 } }, automargin: true });
  return l;
}
const CONFIG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d"] };

// ---- filter UI -------------------------------------------------------------
function buildShell() {
  const navItems = [
    ["Overview", "overview"], ["Capacity", "capacity"], ["Trade-off", "tradeoff"],
    ["Open-loop", "openloop"], ["Workload shape", "shape"], ["Reliability", "reliability"],
    ["Resources", "resources"], ["Sessions", "sessions"], ["Startup / soak", "startup"],
    ["llama-bench", "llamabench"], ["Data", "data"],
  ];
  const nav = navItems.map(([t, id]) => `<a href="#${id}">${t}</a>`).join("");
  const chips = D.models.map((mm) =>
    `<span class="chip ${mm.is_reference ? "ref" : ""}" id="chip-${mm.arm}" data-arm="${mm.arm}">` +
    `<span class="dot" style="background:${mm.color}"></span>${mm.display_name}</span>`).join("");
  document.getElementById("app").innerHTML = `
  <div class="sticky-header">
  <div class="topbar">
    <h1>Local LLM Inference Benchmark</h1>
    <nav>${nav}</nav>
  </div>
  <div class="filterbar">
    <span><label>Cohort</label>
      <select id="f-cohort">
        <option value="all">All</option>
        <option value="mainstream">Mainstream 8-9B</option>
        <option value="spark">Spark reference</option>
      </select></span>
    <span><label>Models</label></span>
    <div class="modelchips">${chips}</div>
    <span><label>Percentile</label>
      <select id="f-pct"><option value="p50">p50</option><option value="p95">p95</option></select></span>
    <button id="f-reset">Reset</button>
  </div>
  </div>
  <main>
    <section id="overview"></section>
    <section id="capacity"></section>
    <section id="tradeoff"></section>
    <section id="openloop"></section>
    <section id="shape"></section>
    <section id="reliability"></section>
    <section id="resources"></section>
    <section id="sessions"></section>
    <section id="startup"></section>
    <section id="llamabench"></section>
    <section id="data"></section>
    <footer>Generated from results/current/ &middot; Plotly ${D.meta.plotly_version} (sha256 ${D.meta.plotly_sha256.slice(0, 12)}&hellip;) &middot; GPU-side energy is an estimate, not full-system power.</footer>
  </main>`;
  document.getElementById("f-cohort").addEventListener("change", (e) => { state.cohort = e.target.value; refresh(); });
  document.getElementById("f-pct").addEventListener("change", (e) => { state.percentile = e.target.value; refresh(); });
  document.getElementById("f-reset").addEventListener("click", () => {
    state.cohort = "all"; state.models = new Set(D.models.map((x) => x.arm)); state.percentile = "p50";
    document.getElementById("f-cohort").value = "all";
    document.getElementById("f-pct").value = "p50";
    refresh();
  });
  document.querySelectorAll(".chip").forEach((el) => {
    el.addEventListener("click", () => {
      const arm = el.dataset.arm;
      if (state.models.has(arm)) state.models.delete(arm); else state.models.add(arm);
      refresh();
    });
  });
}
function syncChips() {
  document.querySelectorAll(".chip").forEach((el) => {
    el.classList.toggle("off", !state.models.has(el.dataset.arm));
  });
}

function plot(id, traces, layout) {
  if (traces.length === 0) {
    document.getElementById(id).innerHTML = '<div class="note">No data for the current selection.</div>';
    return;
  }
  const el = document.createElement("div");
  el.id = id + "-chart"; el.className = "chart";
  const host = document.getElementById(id);
  host.innerHTML = ""; host.appendChild(el);
  Plotly.newPlot(el, traces, layout, CONFIG);
}

// ---- Overview --------------------------------------------------------------
function renderOverview() {
  const md = D.meta;
  const kpis = `
    <div class="kpis">
      <div class="kpi"><div class="v">${md.gpu.split(",")[0] || "—"}</div><div class="k">GPU</div></div>
      <div class="kpi"><div class="v">${md.gpu.split(",")[2] || ""} MiB</div><div class="k">VRAM</div></div>
      <div class="kpi"><div class="v">${md.quantization}</div><div class="k">Quantization</div></div>
      <div class="kpi"><div class="v">${md.aiperf_version}</div><div class="k">AIPerf</div></div>
      <div class="kpi"><div class="v">ctx ${md.context} / par ${md.parallel}</div><div class="k">Serving</div></div>
    </div>`;
  const cards = D.models.map((mm) => {
    const cap = (D.capacity.aggregate || [])
      .filter((c) => c.arm === mm.arm && c.concurrency === 1 && c.status === "PASS");
    const c1 = cap[0] || {};
    const peak = (D.capacity.aggregate || []).filter((c) => c.arm === mm.arm && c.status === "PASS")
      .reduce((best, c) => ((c.output_tps || 0) > (best.output_tps || 0) ? c : best), {});
    const rel = (D.reliability || []).filter((r) => r.arm === mm.arm);
    const relOk = rel.length && rel.every((r) => (r.success_rate_pct || 0) >= 99.5);
    const badge = mm.is_reference ? '<span class="badge">REFERENCE</span>' : "";
    return `<div class="card ${mm.is_reference ? "ref" : ""}">
      <h3>${mm.display_name}${badge}</h3>
      <div class="row"><span class="k">Parameters</span><span>${mm.params_b}B</span></div>
      <div class="row"><span class="k">Quantization</span><span>${mm.quantization}</span></div>
      <div class="row"><span class="k">TTFT p50 @ c=1</span><span>${fmt(c1.ttft_p50)} ms</span></div>
      <div class="row"><span class="k">Peak output tok/s</span><span>${fmt(peak.output_tps)}</span></div>
      <div class="row"><span class="k">Peak VRAM</span><span>${fmt(peak.peak_vram_mib)} MiB</span></div>
      <div class="row"><span class="k">Reliability gate</span><span>${relOk ? "PASS" : "FAIL"}</span></div>
    </div>`;
  }).join("");
  document.getElementById("overview").innerHTML =
    `<h2>Overview</h2><p class="note">Fixed-hardware deployment benchmark on ${md.gpu}. Primary cohort: 4 mainstream 8-9B models (${md.quantization}, upstream llama.cpp); Spark-X2.5-4B is a fixed-hardware reference baseline, never size-matched against the 8-9B cohort.</p>${kpis}<div class="cards">${cards}</div>`;
}

// ---- Capacity --------------------------------------------------------------
function capSeries(metric, aggField) {
  // metric in {output_tps, request_tps, ttft_p50, ttft_p95, latency_p50, latency_p95}
  const traces = [];
  D.models.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = (D.capacity.aggregate || [])
      .filter((c) => c.arm === mm.arm)
      .sort((a, b) => a.concurrency - b.concurrency);
    const valid = rows.filter((c) => c.status === "PASS");
    const invalid = rows.filter((c) => c.status !== "PASS");
    if (valid.length) {
      const xs = valid.map((c) => c.concurrency);
      const ys = valid.map((c) => c[aggField]);
      const errs = valid.map((c) => (c[aggField + "_ci"] != null ? c[aggField + "_ci"] : null));
      traces.push({
        type: "scatter", mode: "lines+markers", name: name(mm.arm),
        x: xs, y: ys, line: { color: mm.color, dash: dashFor(mm.arm), width: 2 },
        marker: { color: mm.color, symbol: markerFor(mm.arm), size: 8 },
        error_y: { type: "data", array: errs, visible: true, thickness: 1, color: mm.color },
        hovertemplate: `<b>${name(mm.arm)}</b><br>c=%{x}<br>${aggField.replace("_", " ")}: %{y:.2f}<extra></extra>`,
      });
    }
    if (invalid.length) {
      traces.push({
        type: "scatter", mode: "markers", name: name(mm.arm) + " (invalid)",
        x: invalid.map((c) => c.concurrency), y: invalid.map((c) => c[aggField]),
        marker: { color: invalid.map((c) => STATUS_COLOR[c.status]), symbol: "x", size: 10 },
        showlegend: false,
        hovertemplate: `<b>${name(mm.arm)}</b><br>c=%{x}<br>status: %{customdata}<extra></extra>`,
        customdata: invalid.map((c) => c.status),
      });
    }
    // raw repeats
    const reps = (D.capacity.repeats || [])
      .filter((r) => r.arm === mm.arm && r.status === "PASS");
    if (reps.length) {
      const repField = { output_tps: "output_tps", request_tps: "request_tps",
        ttft_p50: "ttft_p50", ttft_p95: "ttft_p95", latency_p50: "latency_p50", latency_p95: "latency_p95" }[metric];
      traces.push({
        type: "scatter", mode: "markers", name: name(mm.arm) + " (repeats)",
        x: reps.map((r) => r.concurrency), y: reps.map((r) => r[repField]),
        marker: { color: mm.color, symbol: "circle-open", size: 5, opacity: 0.5 },
        showlegend: false,
        hovertemplate: `<b>${name(mm.arm)}</b><br>c=%{x} rep<br>${metric}: %{y:.2f}<extra></extra>`,
      });
    }
  });
  return traces;
}

function renderCapacity() {
  const p = state.percentile;
  const host = document.getElementById("capacity");
  const items = [
    ["cap-output", "Output throughput vs concurrency", "output_tps", "output tokens/s"],
    ["cap-request", "Request throughput vs concurrency", "request_tps", "requests/s"],
    ["cap-ttft", `TTFT ${p} vs concurrency`, `ttft_${p}`, "TTFT (ms)"],
    ["cap-lat", `E2E latency ${p} vs concurrency`, `latency_${p}`, "E2E latency (ms)"],
  ];
  host.innerHTML = `<h2>Capacity</h2>
    <p class="note">Mean with 95% CI error bars; open points show the individual repeats. Invalid (UNSTABLE/FAIL) cells are marked with &times;, not connected.</p>
    <div class="grid2">${items.map(([id, t, m, y]) => `<div id="${id}"></div>`).join("")}</div>`;
  items.forEach(([id, t, metric, y]) => {
    plot(id, capSeries(metric, metric), baseLayout(t, "concurrency", y));
  });
}

// ---- Trade-off -------------------------------------------------------------
function paretoFrontier(points) {
  // Pareto-optimal set where "better" = higher x (throughput) AND lower y (latency).
  // A dominates B iff A.x >= B.x AND A.y <= B.y, with at least one strict inequality.
  const pts = points.slice().sort((a, b) => a.x - b.x || b.y - a.y);
  const frontier = [];
  pts.forEach((p) => {
    const dominated = frontier.some((f) =>
      f.x >= p.x && f.y <= p.y && (f.x > p.x || f.y < p.y));
    if (!dominated) {
      const filtered = frontier.filter((f) =>
        !(p.x >= f.x && p.y <= f.y && (p.x > f.x || p.y < f.y)));
      filtered.push(p);
      frontier.length = 0;
      frontier.push(...filtered);
    }
  });
  frontier.sort((a, b) => a.x - b.x);
  return frontier;
}

function renderTradeoff() {
  const host = document.getElementById("tradeoff");
  const primary = D.models.filter((mm) => mm.cohort === "mainstream_8_9b");
  const traces = [];
  D.models.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = (D.capacity.aggregate || []).filter((c) => c.arm === mm.arm && c.status === "PASS");
    const x = rows.map((c) => c.request_tps);
    const y = rows.map((c) => c.ttft_p50);
    traces.push({
      type: "scatter", mode: "markers+lines", name: name(mm.arm),
      x, y, line: { color: mm.color, dash: dashFor(mm.arm), width: 1.5 },
      marker: { color: mm.color, symbol: markerFor(mm.arm), size: 10 },
      customdata: rows.map((c) => [c.concurrency, c.output_tps, c.ttft_p50, c.ttft_p95,
        c.latency_p50, c.latency_p95, c.peak_vram_mib, c.pass_runs, c.status]),
      hovertemplate: `<b>${name(mm.arm)}</b><br>c=%{customdata[0]}<br>req/s=%{x:.3f}<br>output tok/s=%{customdata[1]:.1f}<br>TTFT p50=%{customdata[2]:.1f} ms p95=%{customdata[3]:.1f} ms<br>E2E p50=%{customdata[4]:.1f} p95=%{customdata[5]:.1f}<br>VRAM=%{customdata[6]:.0f} MiB<br>repeats=%{customdata[7]}<extra></extra>`,
    });
  });
  // Pareto frontier per primary model
  primary.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = (D.capacity.aggregate || []).filter((c) => c.arm === mm.arm && c.status === "PASS")
      .map((c) => ({ x: c.request_tps, y: c.ttft_p50 })).filter((p) => p.x != null && p.y != null);
    const fr = paretoFrontier(rows);
    if (fr.length > 1) {
      traces.push({
        type: "scatter", mode: "lines", name: mm.display_name + " Pareto",
        x: fr.map((p) => p.x), y: fr.map((p) => p.y),
        line: { color: mm.color, dash: "dot", width: 1 }, showlegend: false,
      });
    }
  });
  const lay = baseLayout("TTFT p50 vs request throughput (further right = higher throughput; lower = lower latency)",
    "request throughput (req/s)", "TTFT p50 (ms)");
  const host2 = document.createElement("div"); host2.innerHTML =
    `<h2>Latency / throughput trade-off</h2>
    <p class="note">Each point is one concurrency level. Further right = higher throughput; lower = lower latency. Dotted line: Pareto frontier of the 8-9B cohort only — Spark is excluded from size-matched ranking and shown as an open/dashed reference.</p>
    <div id="tradeoff-ttft"></div>`;
  host.innerHTML = host2.innerHTML;
  plot("tradeoff-ttft", traces, lay);
}

// ---- Open-loop -------------------------------------------------------------
function renderOpenloop() {
  const host = document.getElementById("openloop");
  const hasSLO = Object.keys(D.config.slo_profiles || {}).length > 0;
  const sloNote = hasSLO ? ""
    : "No SLO profiles are configured, so these show transport-level request throughput and transport success rate (not SLO goodput).";
  host.innerHTML = `<h2>Open-loop</h2>
    <p class="note">Offered Poisson load vs achieved request throughput. y=x is ideal. Achieved below the offer near/above 1.0 shows saturation. ${sloNote}</p>
    <div class="grid2"><div id="ol-offered"></div><div id="ol-achieved"></div></div>
    <div class="grid2"><div id="ol-frac"></div><div id="ol-ttft"></div></div>`;
  const ol = D.open_loop || [];
  const traces1 = [], traces2 = [], traces3 = [], traces4 = [];
  D.models.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = ol.filter((r) => r.arm === mm.arm).sort((a, b) => a.load_fraction - b.load_fraction);
    if (!rows.length) return;
    traces1.push({
      type: "scatter", mode: "lines+markers", name: name(mm.arm),
      x: rows.map((r) => r.offered_rps), y: rows.map((r) => r.achieved_rps),
      line: { color: mm.color, dash: dashFor(mm.arm) },
      marker: { color: mm.color, symbol: markerFor(mm.arm) },
    });
    traces2.push({
      type: "scatter", mode: "lines+markers", name: name(mm.arm),
      x: rows.map((r) => r.load_fraction), y: rows.map((r) => r.achieved_rps),
      line: { color: mm.color, dash: dashFor(mm.arm) },
      marker: { color: mm.color, symbol: markerFor(mm.arm) },
    });
    traces3.push({
      type: "scatter", mode: "lines+markers", name: name(mm.arm),
      x: rows.map((r) => r.load_fraction),
      y: rows.map((r) => (r.error_rate_pct == null ? null : 100 - r.error_rate_pct)),
      line: { color: mm.color, dash: dashFor(mm.arm) },
      marker: { color: mm.color, symbol: markerFor(mm.arm) },
    });
    traces4.push({
      type: "scatter", mode: "lines+markers", name: name(mm.arm),
      x: rows.map((r) => r.load_fraction), y: rows.map((r) => r.ttft_p95),
      line: { color: mm.color, dash: dashFor(mm.arm) },
      marker: { color: mm.color, symbol: markerFor(mm.arm) },
    });
  });
  const maxx = Math.max(0, ...ol.filter((r) => visible(r.arm)).map((r) => r.offered_rps || 0));
  const ideal = { type: "scatter", mode: "lines", name: "ideal (y=x)",
    x: [0, maxx], y: [0, maxx], line: { color: "#9ca3af", dash: "dot", width: 1 },
    hoverinfo: "skip" };
  const l1 = baseLayout("Offered vs achieved request throughput", "offered RPS", "achieved RPS");
  plot("ol-offered", [ideal, ...traces1], l1);
  plot("ol-achieved", traces2, baseLayout("Achieved request throughput vs load fraction", "load fraction (x capacity)", "achieved RPS"));
  const l3 = baseLayout("Transport success rate vs offered load", "load fraction", "transport success (%)");
  l3.yaxis.range = [0, 105];
  plot("ol-frac", traces3, l3);
  plot("ol-ttft", traces4, baseLayout("TTFT p95 vs offered load", "load fraction", "TTFT p95 (ms)"));
}

// ---- Workload shape --------------------------------------------------------
function renderShape() {
  const host = document.getElementById("shape");
  const concs = [...new Set((D.shape || []).map((r) => r.concurrency))].sort((a, b) => a - b);
  const cOptions = concs.map((c) => `<option value="${c}">c=${c}</option>`).join("");
  host.innerHTML = `<h2>Workload shape</h2>
    <p class="note">Heatmap of metric by workload profile at one concurrency level. Invalid cells (UNSTABLE/TIMEOUT/FAIL, e.g. Spark at ISL &ge; 256) are overlaid with their status symbol.</p>
    <p>
      <label>Metric</label>
      <select id="shape-metric">
        <option value="ttft_p50">TTFT p50 (ms)</option>
        <option value="output_tps">Output tok/s</option>
        <option value="latency_p50">E2E latency p50 (ms)</option>
        <option value="peak_vram_mib">Peak VRAM (MiB)</option>
      </select>
      <label style="margin-left:1rem">Concurrency</label>
      <select id="shape-c">${cOptions}</select>
    </p>
    <div id="shape-heat"></div>`;
  const draw = () => {
    const metric = document.getElementById("shape-metric").value;
    const c = document.getElementById("shape-c").value;
    const arms = D.models.filter((mm) => visible(mm.arm)).map((mm) => mm.arm);
    const profOrder = Object.keys(D.config.shape_profiles || {});
    const rows = (D.shape || []).filter((r) => arms.includes(r.arm)
      && String(r.concurrency) === c);
    if (!rows.length) { document.getElementById("shape-heat").innerHTML = '<div class="note">No data.</div>'; return; }
    // one cell = one (arm, profile, concurrency); no averaging.
    const cell = {};
    rows.forEach((r) => {
      cell[r.arm + "|" + r.profile] = { v: r[metric], st: r.status };
    });
    const yLabels = arms.map((a) => name(a));
    const z = [], text = [], status = [];
    arms.forEach((arm) => {
      const zr = [], tr = [], sr = [];
      profOrder.forEach((prof) => {
        const cc = cell[arm + "|" + prof];
        if (!cc) { zr.push(null); tr.push(""); sr.push(null); return; }
        zr.push(cc.v);
        tr.push(`${name(arm)}<br>${prof} (ISL ${D.config.shape_profiles[prof].isl}/OSL ${D.config.shape_profiles[prof].osl})<br>c=${c}<br>${metric}: ${fmt(cc.v)}<br>status: ${cc.st}`);
        sr.push(cc.st);
      });
      z.push(zr); text.push(tr); status.push(sr);
    });
    // invalid-cell overlays use categorical profile + model names (no index coords).
    const ix = [], iy = [], isym = [], icol = [];
    arms.forEach((arm, i) => profOrder.forEach((prof, j) => {
      const st = status[i][j];
      if (st && st !== "PASS") {
        ix.push(prof); iy.push(name(arm));
        isym.push(STATUS_SYMBOL[st] || "x"); icol.push(STATUS_COLOR[st] || "#c62828");
      }
    }));
    const traces = [{
      type: "heatmap", z, x: profOrder, y: yLabels, text,
      hoverinfo: "text", colorscale: "YlGnBu", showscale: true,
      colorbar: { title: { text: metric } },
    }];
    if (ix.length) {
      traces.push({
        type: "scatter", mode: "markers",
        x: ix, y: iy,
        marker: { color: icol, symbol: isym, size: 13,
          line: { color: "#fff", width: 1 } },
        showlegend: false, hoverinfo: "skip",
      });
    }
    const lay = baseLayout("Workload shape heatmap", "profile", "model");
    lay.xaxis.tickangle = -25;
    plot("shape-heat", traces, lay);
  };
  document.getElementById("shape-metric").addEventListener("change", draw);
  document.getElementById("shape-c").addEventListener("change", draw);
  document.getElementById("shape-c").value = String(concs[0]);
  draw();
}

// ---- Reliability -----------------------------------------------------------
function renderReliability() {
  const host = document.getElementById("reliability");
  host.innerHTML = `<h2>Reliability</h2>
    <p class="note">Observed success rate with Wilson 95% interval. The operational threshold (${D.config.reliability_threshold_pct}%) is shown as a vertical line. 200/200 does not prove true reliability is exactly 100%.</p>
    <div id="rel-dot"></div>`;
  const rows = (D.reliability || []).filter((r) => visible(r.arm));
  const labels = rows.map((r) => `${shortName(r.arm)} · c=${r.concurrency}`);
  const x = rows.map((r) => r.success_rate_pct);
  const low = rows.map((r) => r.wilson_low);
  const high = rows.map((r) => r.wilson_high);
  const traces = [{
    type: "scatter", mode: "markers", x, y: labels,
    error_x: { type: "data", symmetric: false, array: high.map((h, i) => h - x[i]),
      arrayminus: x.map((xx, i) => xx - low[i]), color: "#9ca3af", thickness: 1.5 },
    marker: { color: rows.map((r) => color(r.arm)), symbol: rows.map((r) => markerFor(r.arm)), size: 9 },
    customdata: rows.map((r) => [r.attempted, r.successful, r.failed, r.error_types]),
    hovertemplate: `<b>%{y}</b><br>success %{x:.2f}%<br>attempted=%{customdata[0]} successful=%{customdata[1]} failed=%{customdata[2]}<br>errors=%{customdata[3]}<extra></extra>`,
  }];
  const lay = baseLayout("Reliability (Wilson 95% CI)", "observed success %", "");
  lay.xaxis.range = [Math.min(...low.map((v) => v - 0.5)), 100.5];
  const thresh = D.config.reliability_threshold_pct;
  lay.shapes = [{
    type: "line", x0: thresh, x1: thresh, y0: -0.5, y1: labels.length - 0.5,
    line: { color: "#b91c1c", dash: "dash", width: 1.5 },
  }];
  lay.annotations = [{ x: thresh, y: labels.length - 0.2, xref: "x", yref: "y",
    text: `threshold ${thresh}%`, showarrow: false, font: { size: 11, color: "#b91c1c" }, xanchor: "left" }];
  plot("rel-dot", traces, lay);
}

// ---- Resources -------------------------------------------------------------
function renderResources() {
  const host = document.getElementById("resources");
  host.innerHTML = `<h2>Resource / efficiency</h2>
    <p class="note">GPU-side energy is an estimate (integral of nvidia-smi power sampling), not full-system energy. Spark appears here as a fixed-hardware cross-cohort reference.</p>
    <div class="grid2"><div id="res-vram"></div><div id="res-eff"></div></div>
    <div class="grid2"><div id="res-energy"></div><div id="res-power"></div></div>`;
  const cap = D.capacity.aggregate || [];
  // peak VRAM per model (max over concurrency, PASS cells)
  const vramRows = [];
  D.models.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = cap.filter((c) => c.arm === mm.arm && c.status === "PASS");
    if (!rows.length) return;
    const peak = rows.reduce((b, c) => ((c.peak_vram_mib || 0) > (b.peak_vram_mib || 0) ? c : b));
    vramRows.push({ arm: mm.arm, vram: peak.peak_vram_mib });
  });
  const vramTrace = {
    type: "bar", x: vramRows.map((r) => name(r.arm)), y: vramRows.map((r) => r.vram),
    marker: { color: vramRows.map((r) => color(r.arm)) },
    hovertemplate: `<b>%{x}</b><br>peak VRAM %{y:.0f} MiB<extra></extra>`,
  };
  plot("res-vram", [vramTrace], baseLayout("Peak VRAM", "model", "MiB"));

  // efficiency scatter: x=VRAM, y=peak output tok/s
  const effRows = [];
  D.models.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = cap.filter((c) => c.arm === mm.arm && c.status === "PASS");
    if (!rows.length) return;
    const peak = rows.reduce((b, c) => ((c.output_tps || 0) > (b.output_tps || 0) ? c : b));
    effRows.push({ arm: mm.arm, vram: peak.peak_vram_mib, tps: peak.output_tps,
      concurrency: peak.concurrency, params_b: mm.params_b, quantization: mm.quantization,
      role: mm.is_reference ? "reference (4B)" : "primary (8-9B)" });
  });
  const effTrace = {
    type: "scatter", mode: "markers+text", textposition: "top center",
    x: effRows.map((r) => r.vram), y: effRows.map((r) => r.tps),
    text: effRows.map((r) => shortName(r.arm)),
    marker: { color: effRows.map((r) => color(r.arm)),
      symbol: effRows.map((r) => markerFor(r.arm)), size: 13 },
    customdata: effRows.map((r) => [r.params_b, r.concurrency, r.quantization, r.role]),
    hovertemplate: `<b>${"%{text}"}</b><br>VRAM %{x:.0f} MiB<br>output %{y:.1f} tok/s @ c=%{customdata[1]}<br>params %{customdata[0]}B · %{customdata[2]} · %{customdata[3]}<extra></extra>`,
  };
  plot("res-eff", [effTrace], baseLayout("Output tok/s vs peak VRAM (efficiency)", "VRAM (MiB)", "output tokens/s"));

  // energy per output token (from repeats, PASS)
  const rep = D.capacity.repeats || [];
  const enRows = [];
  D.models.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = rep.filter((r) => r.arm === mm.arm && r.status === "PASS" && r.gpu_j_per_output_token != null);
    if (!rows.length) return;
    const v = rows.reduce((a, b) => a + b.gpu_j_per_output_token, 0) / rows.length;
    enRows.push({ arm: mm.arm, v });
  });
  if (enRows.length) {
    plot("res-energy", [{
      type: "bar", x: enRows.map((r) => name(r.arm)), y: enRows.map((r) => r.v),
      marker: { color: enRows.map((r) => color(r.arm)) },
      hovertemplate: `<b>%{x}</b><br>%{y:.3f} J/output token<extra></extra>`,
    }], baseLayout("GPU-side energy per output token (estimate)", "model", "J/token"));
  } else {
    document.getElementById("res-energy").innerHTML = '<div class="note">No energy telemetry.</div>';
  }
  // power
  const powRows = [];
  D.models.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = cap.filter((c) => c.arm === mm.arm && c.status === "PASS" && c.peak_power_w != null);
    if (!rows.length) return;
    powRows.push({ arm: mm.arm, v: Math.max(...rows.map((r) => r.peak_power_w)) });
  });
  plot("res-power", [{
    type: "bar", x: powRows.map((r) => name(r.arm)), y: powRows.map((r) => r.v),
    marker: { color: powRows.map((r) => color(r.arm)) },
    hovertemplate: `<b>%{x}</b><br>peak %{y:.1f} W<extra></extra>`,
  }], baseLayout("Peak GPU power", "model", "W"));
}

// ---- Sessions --------------------------------------------------------------
function renderSessions() {
  const host = document.getElementById("sessions");
  host.innerHTML = `<h2>Sessions</h2>
    <p class="note">Multi-turn TTFT p50 by prompt caching (3-turn sessions, 64-token outputs). cache_prompt=true avoids re-prefilling the history.</p>
    <div id="ses"></div>`;
  const traces = [];
  ["nocache", "cache"].forEach((cm) => {
    const xs = [], ys = [], colors = [];
    D.models.forEach((mm) => {
      if (!visible(mm.arm)) return;
      const r = (D.sessions || []).find((s) => s.arm === mm.arm && s.cache_mode === cm);
      if (r && r.ttft_p50 != null) { xs.push(mm.arm); ys.push(r.ttft_p50); colors.push(mm.color); }
    });
    traces.push({
      type: "bar", name: cm === "cache" ? "cache_prompt=true" : "cache_prompt=false",
      x: xs.map((a) => name(a)), y: ys, marker: { color: colors },
      hovertemplate: `<b>%{x}</b><br>${cm} TTFT p50 %{y:.1f} ms<extra></extra>`,
    });
  });
  plot("ses", traces, Object.assign(baseLayout("Multi-turn TTFT p50", "model", "TTFT p50 (ms)"), { barmode: "group" }));
}

// ---- Startup / soak --------------------------------------------------------
function renderStartup() {
  const host = document.getElementById("startup");
  host.innerHTML = `<h2>Startup / soak</h2>
    <p class="note">Startup: cold start to first token, all 3 repeats (not statistics from 3 samples). Soak: 600 s sustained-load summary.</p>
    <div class="grid2"><div id="start-dot"></div><div id="soak-sum"></div></div>`;
  // startup strip
  const traces = [];
  D.models.forEach((mm) => {
    if (!visible(mm.arm)) return;
    const rows = (D.startup || []).filter((s) => s.arm === mm.arm);
    traces.push({
      type: "scatter", mode: "markers", name: name(mm.arm),
      x: rows.map((r) => r.cold_start_ms),
      y: rows.map(() => name(mm.arm)),
      marker: { color: mm.color, symbol: markerFor(mm.arm), size: 10 },
      hovertemplate: `<b>${name(mm.arm)}</b><br>rep %{customdata[0]}: cold start %{x:.0f} ms (ready %{customdata[1]:.0f}, first token %{customdata[2]:.0f})<extra></extra>`,
      customdata: rows.map((r) => [r.repeat, r.ready_ms, r.first_token_ms]),
    });
  });
  plot("start-dot", traces, baseLayout("Cold start to first token (3 repeats)", "ms", "model"));

  // soak summary
  const soakRows = (D.soak || []).filter((s) => visible(s.arm));
  const soakTrace = {
    type: "bar", x: soakRows.map((s) => name(s.arm)),
    y: soakRows.map((s) => s.output_tps),
    marker: { color: soakRows.map((s) => color(s.arm)) },
    customdata: soakRows.map((s) => [s.error_rate_pct, s.peak_power_w, s.peak_temp_c]),
    hovertemplate: `<b>%{x}</b><br>sustained output %{y:.1f} tok/s<br>error %{customdata[0]}%<br>power %{customdata[1]:.1f} W, temp %{customdata[2]:.0f} C<extra></extra>`,
  };
  plot("soak-sum", [soakTrace], baseLayout("Soak: sustained output tok/s (600 s @ 0.75x)", "model", "output tokens/s"));
}

// ---- llama-bench -----------------------------------------------------------
function renderLlamaBench() {
  const host = document.getElementById("llamabench");
  const rows = (D.llama_bench || []).filter((r) => visible(r.arm));
  if (!rows.length) { host.innerHTML = "<h2>llama-bench</h2><p class='note'>No microbenchmark data (Spark fork has no llama-bench binary).</p>"; return; }
  host.innerHTML = `<h2>llama-bench (raw engine microbenchmark)</h2>
    <p class="note"><b>Raw engine microbenchmark — not AIPerf end-to-end serving.</b></p>
    <div id="lb"></div>`;
  const names = rows.map((r) => name(r.arm));
  plot("lb", [
    { type: "bar", name: "pp512 (prompt processing)", orientation: "h",
      x: rows.map((r) => r.pp512), y: names, marker: { color: "#0072b2" } },
    { type: "bar", name: "tg128 (generation)", orientation: "h",
      x: rows.map((r) => r.tg128), y: names, marker: { color: "#009e73" } },
  ], Object.assign(baseLayout("llama-bench pp512 / tg128", "tokens/s", "model"), { barmode: "group" }));
}

// ---- Raw data --------------------------------------------------------------
function renderData() {
  const host = document.getElementById("data");
  const cap = D.capacity.aggregate || [];
  host.innerHTML = `<h2>Data</h2>
    <p class="note">Curated aggregate. Raw repeats live in <code>results/current/&lt;cohort&gt;/&lt;suite&gt;/repeats.tsv</code>. Downloads: <a href="data/current.json">current.json</a>.</p>
    <div class="datatable-wrap"><table class="datatable" id="dtable"><thead></thead><tbody></tbody></table></div>`;
  const cols = ["arm", "concurrency", "status", "ttft_p50", "ttft_p95", "latency_p50", "latency_p95",
    "request_tps", "output_tps", "peak_vram_mib", "error_rate_pct"];
  const thead = `<tr><th>Model</th>${cols.slice(1).map((c) => `<th>${c}</th>`).join("")}</tr>`;
  document.querySelector("#dtable thead").innerHTML = thead;
  const rows = cap.filter((c) => visible(c.arm));
  const body = rows.map((c) =>
    `<tr><td>${name(c.arm)}</td>${cols.slice(1).map((k) =>
      k === "status" ? `<td class="st-${c.status}">${c.status}</td>` : `<td>${fmt(c[k])}</td>`).join("")}</tr>`).join("");
  document.querySelector("#dtable tbody").innerHTML = body;
}

// ---- render all ------------------------------------------------------------
function refresh() {
  syncChips();
  renderOverview();
  renderCapacity();
  renderTradeoff();
  renderOpenloop();
  renderShape();
  renderReliability();
  renderResources();
  renderSessions();
  renderStartup();
  renderLlamaBench();
  renderData();
}

buildShell();
refresh();
