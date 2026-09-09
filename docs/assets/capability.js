/* Coding / software-engineering capability — rendered on top of the serving
 * dashboard. Static: reads the embedded capability dataset (docs/data/
 * capability.json) and reuses the serving dashboard's model colors/markers so
 * every model keeps ONE stable color across both halves of the site.
 *
 * This half of the dashboard is explicitly SEPARATE from serving throughput /
 * TTFT / VRAM / energy. No combined score is computed. */
"use strict";

const CAP = JSON.parse(document.getElementById("capability-data").textContent);

const BENCH_LABEL = {
  evalplus: "EvalPlus", livecodebench: "LiveCodeBench",
  "swe-verified": "SWE-bench Verified", deepswe: "DeepSWE",
  "swe-multilingual": "SWE-bench Multilingual",
  "terminal-bench": "Terminal-Bench", "swe-pro": "SWE-bench Pro",
  "swe-evo": "SWE-EVO",
};

function capColor(arm) {
  const mm = modelByArm[arm];
  return mm ? mm.color : "#888";
}
function capName(arm) {
  const mm = modelByArm[arm];
  return mm ? (mm.is_reference ? `${mm.display_name} (REFERENCE / 4B)` : mm.display_name) : arm;
}
function capArms() {
  return (CAP.models || []).map((m) => m.arm);
}

function capNote(text) {
  return `<p class="note">${text}</p>`;
}

// ---- 1. Overview matrix -----------------------------------------------------
function renderCapOverview() {
  const host = document.getElementById("cap-overview");
  if (!host) return;
  const arms = capArms();
  const cols = CAP.overview_columns || [];
  if (!arms.length || !cols.length) {
    host.innerHTML = `<h2>Capability overview</h2>${capNote("No capability results yet.")}`;
    return;
  }
  const rows = arms.map((arm) => {
    const cells = cols.map(([key, label]) => {
      const ov = (CAP.overview[arm] || {})[key];
      if (!ov || ov.value == null) {
        return `<td class="na" title="not run / N/A">N/A</td>`;
      }
      const val = fmt(ov.value, 1);
      const ci = ov.wilson_lo != null
        ? ` [${fmt(ov.wilson_lo, 1)}–${fmt(ov.wilson_hi, 1)}]` : "";
      return `<td title="${label}: ${val}%${ci} (n=${ov.n})">${val}%</td>`;
    }).join("");
    return `<tr><th>${capName(arm)}</th>${cells}</tr>`;
  }).join("");
  const head = cols.map(([, label]) => `<th>${label}</th>`).join("");
  host.innerHTML = `<h2>Capability overview</h2>
    ${capNote("Rows = models, columns = benchmarks. Cells show each benchmark's own metric; they are NOT averaged into any combined score. N/A = not run or ineligible.")}
    <div class="datatable-wrap"><table class="datatable"><thead><tr><th>Model</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

// ---- 2. Direct coding (EvalPlus) -------------------------------------------
function renderCapDirect() {
  const host = document.getElementById("cap-direct");
  if (!host) return;
  const b = CAP.benchmarks.evalplus;
  const arms = capArms();
  host.innerHTML = `<h2>Direct coding</h2>
    ${capNote("temperature=0, n=1, reasoning off, official EvalPlus prompt + executor. The base → plus drop flags solutions that only pass weak tests.")}
    <div id="cap-evalplus"></div>
    <div id="cap-lcb"></div>`;

  if (!b || !b.summary.length) return;

  // grouped bars: HumanEval / HumanEval+ / MBPP / MBPP+
  const rows = b.summary;
  const cats = ["HumanEval", "HumanEval+", "MBPP", "MBPP+"];
  const traces = cats.map((c) => {
    const vals = arms.map((arm) => {
      const r = rows.find((x) => x.model === arm && (c.startsWith("HumanEval")
        ? x.dataset === "humaneval" : x.dataset === "mbpp"));
      if (!r) return null;
      return c.endsWith("+") ? r.plus_pass_at_1 : r.base_pass_at_1;
    });
    return {
      type: "bar", name: c,
      x: arms.map(capName), y: vals,
      marker: { color: arms.map(capColor) },
      text: vals.map((v) => (v == null ? "" : v + "%")),
      textposition: "outside",
      hovertemplate: `<b>%{x}</b><br>${c} %{y:.1f}%<extra></extra>`,
    };
  });
  plot("cap-evalplus", traces, baseLayout("EvalPlus pass@1 (base vs plus)", "model", "pass@1 %"));

  // LiveCodeBench if present
  const lcb = CAP.benchmarks.livecodebench;
  if (lcb && lcb.summary.length) {
    const lr = lcb.summary;
    plot("cap-lcb", [{
      type: "bar", x: lr.map((r) => capName(r.model)), y: lr.map((r) => r.pass_at_1),
      marker: { color: lr.map((r) => capColor(r.model)) },
      text: lr.map((r) => r.pass_at_1 + "%"), textposition: "outside",
    }], baseLayout("LiveCodeBench pass@1 (LOCAL PROTOCOL, n=1)", "model", "pass@1 %"));
  }
}

// ---- 3. Generic agentic benchmark section -----------------------------------
function renderCapAgent(bench) {
  const host = document.getElementById(`cap-${bench}`);
  if (!host) return;
  const b = CAP.benchmarks[bench];
  const label = BENCH_LABEL[bench] || bench;
  if (!b || !b.summary.length) {
    host.innerHTML = `<h2>${label}</h2>${capNote("No results yet.")}`;
    return;
  }
  host.innerHTML = `<h2>${label}</h2>
    ${capNote("resolved % with Wilson 95% CI. Infrastructure failures are reported separately and do not count as model failures.")}
    <div id="cap-${bench}-res"></div>
    <div id="cap-${bench}-eff"></div>`;

  const arms = b.summary.map((r) => r.model);

  // resolution-rate dot plot with Wilson CI
  const srows = b.summary.filter((r) => r.n > 0);
  plot(`cap-${bench}-res`, [{
    type: "scatter", mode: "markers",
    x: srows.map((r) => capName(r.model)),
    y: srows.map((r) => (r.resolved != null ? r.resolved / r.n * 100 : r.value)),
    error_y: {
      type: "data", symmetric: false,
      array: srows.map((r) => r.wilson_hi != null ? (r.wilson_hi - r.value) : 0),
      arrayminus: srows.map((r) => r.wilson_lo != null ? (r.value - r.wilson_lo) : 0),
      visible: true,
    },
    marker: { color: srows.map((r) => capColor(r.model)),
      symbol: srows.map((r) => markerFor(r.model)), size: 13 },
    text: srows.map((r) => `${r.resolved}/${r.n}`),
    textposition: "top center",
    hovertemplate: `<b>%{x}</b><br>resolved %{y:.1f}% (%{text})<extra></extra>`,
  }], baseLayout(`${label} resolved rate`, "model", "resolved %"));

  // efficiency: wall time vs resolved
  const t = b.tasks || [];
  const eff = arms.map((arm) => {
    const tr = t.filter((x) => x.model === arm && x.wall_time !== "");
    const wt = tr.map((x) => parseFloat(x.wall_time)).filter((v) => !isNaN(v));
    const median = wt.length ? wt.sort((a, b) => a - b)[Math.floor(wt.length / 2)] : null;
    const resolved = t.filter((x) => x.model === arm && x.resolved).length;
    return { arm, median, resolved, n: tr.length };
  }).filter((x) => x.median != null && x.n > 0);
  if (eff.length) {
    plot(`cap-${bench}-eff`, [{
      type: "scatter", mode: "markers+text",
      x: eff.map((x) => x.median), y: eff.map((x) => x.resolved / x.n * 100),
      text: eff.map((x) => shortName(x.arm)), textposition: "top center",
      marker: { color: eff.map((x) => capColor(x.arm)),
        symbol: eff.map((x) => markerFor(x.arm)), size: 13 },
      hovertemplate: `<b>%{text}</b><br>median %{x:.0f}s/task<br>resolved %{y:.1f}%<extra></extra>`,
    }], baseLayout(`${label}: median wall time vs resolved`, "median wall time (s)", "resolved %"));
  }
}

// ---- 4. Failure taxonomy ----------------------------------------------------
function renderCapFailures() {
  const host = document.getElementById("cap-failures");
  if (!host) return;
  const ft = CAP.failure_taxonomy || {};
  const arms = Object.keys(ft);
  if (!arms.length) {
    host.innerHTML = `<h2>Failure analysis</h2>${capNote("No task-level failure data yet.")}`;
    return;
  }
  const cats = [...new Set(arms.flatMap((a) => Object.keys(ft[a])))];
  const traces = cats.map((c) => ({
    type: "bar", name: c,
    x: arms.map(capName),
    y: arms.map((a) => ft[a][c] || 0),
  }));
  plot("cap-failures-plot", traces, Object.assign(baseLayout("Failure taxonomy", "model", "task count"), { barmode: "stack" }));
  host.innerHTML = `<h2>Failure analysis</h2>
    ${capNote("Stacked task counts by failure category. Infrastructure failures (OOM / verifier / environment) are kept separate from model/agent failures.")}
    <div id="cap-failures-plot"></div>`;
}

// ---- 5. Task explorer -------------------------------------------------------
function renderCapExplorer() {
  const host = document.getElementById("cap-explorer");
  if (!host) return;
  const tasks = CAP.tasks || [];
  host.innerHTML = `<h2>Task explorer</h2>
    ${capNote("Task-level outcomes. Filters: benchmark / model. Raw trajectories are not embedded.")}
    <p class="filterline">
      <select id="capf-bench"><option value="all">All benchmarks</option></select>
      <select id="capf-model"><option value="all">All models</option></select>
    </p>
    <div class="datatable-wrap"><table class="datatable" id="captable"><thead></thead><tbody></tbody></table></div>`;

  const benches = [...new Set(tasks.map((t) => t.benchmark))];
  const models = [...new Set(tasks.map((t) => t.model))];
  document.getElementById("capf-bench").innerHTML += benches.map((b) => `<option value="${b}">${BENCH_LABEL[b] || b}</option>`).join("");
  document.getElementById("capf-model").innerHTML += models.map((m) => `<option value="${m}">${capName(m)}</option>`).join("");

  const draw = () => {
    const fb = document.getElementById("capf-bench").value;
    const fm = document.getElementById("capf-model").value;
    const rows = tasks.filter((t) => (fb === "all" || t.benchmark === fb) &&
      (fm === "all" || t.model === fm));
    const cols = ["benchmark", "task_id", "model", "repo", "language", "resolved",
      "steps", "wall_time", "input_tokens", "output_tokens", "failure_category"];
    const thead = `<tr>${cols.map((c) => `<th>${c.replace(/_/g, " ")}</th>`).join("")}</tr>`;
    const body = rows.map((t) => `<tr>${cols.map((c) => {
      if (c === "benchmark") return `<td>${BENCH_LABEL[t.benchmark] || t.benchmark}</td>`;
      if (c === "model") return `<td>${capName(t.model)}</td>`;
      if (c === "resolved") return `<td class="${t.resolved ? "st-PASS" : "st-FAIL"}">${t.resolved ? "✓" : "✗"}</td>`;
      return `<td>${t[c] ?? ""}</td>`;
    }).join("")}</tr>`).join("");
    document.querySelector("#captable thead").innerHTML = thead;
    document.querySelector("#captable tbody").innerHTML = body;
  };
  document.getElementById("capf-bench").addEventListener("change", draw);
  document.getElementById("capf-model").addEventListener("change", draw);
  draw();
}

// ---- 3b. Frontier pilots (SWE-bench Pro + SWE-EVO) --------------------------
function renderCapFrontier() {
  const host = document.getElementById("cap-frontier");
  if (!host) return;
  const hasPro = CAP.benchmarks["swe-pro"] && CAP.benchmarks["swe-pro"].summary.length;
  const hasEvo = CAP.benchmarks["swe-evo"] && CAP.benchmarks["swe-evo"].summary.length;
  host.innerHTML = `<h2>Frontier pilots</h2>
    ${capNote("Much harder than SWE-bench Verified; treated as a frontier diagnostic, not a full run.")}
    <div id="cap-swe-pro"></div><div id="cap-swe-evo"></div>`;
  if (hasPro) renderCapAgentInto("swe-pro", "cap-swe-pro");
  if (hasEvo) renderCapAgentInto("swe-evo", "cap-swe-evo");
  if (!hasPro && !hasEvo) host.innerHTML += capNote("Not run (or not yet feasible on this hardware).");
}

function renderCapAgentInto(bench, divId) {
  const b = CAP.benchmarks[bench];
  if (!b || !b.summary.length) return;
  const label = BENCH_LABEL[bench] || bench;
  const srows = b.summary.filter((r) => r.n > 0);
  plot(divId, [{
    type: "scatter", mode: "markers",
    x: srows.map((r) => capName(r.model)),
    y: srows.map((r) => (r.resolved != null ? r.resolved / r.n * 100 : r.value)),
    error_y: { type: "data", symmetric: false,
      array: srows.map((r) => r.wilson_hi != null ? (r.wilson_hi - r.value) : 0),
      arrayminus: srows.map((r) => r.wilson_lo != null ? (r.value - r.wilson_lo) : 0) },
    marker: { color: srows.map((r) => capColor(r.model)),
      symbol: srows.map((r) => markerFor(r.model)), size: 13 },
    text: srows.map((r) => `${r.resolved}/${r.n}`), textposition: "top center",
    hovertemplate: `<b>%{x}</b><br>resolved %{y:.1f}% (%{text})<extra></extra>`,
  }], baseLayout(`${label} resolved rate`, "model", "resolved %"));
}

// ---- render all -------------------------------------------------------------
function renderCapability() {
  renderCapOverview();
  renderCapDirect();
  ["swe-verified", "deepswe", "swe-multilingual", "terminal-bench"].forEach(renderCapAgent);
  renderCapFrontier();
  renderCapFailures();
  renderCapExplorer();
}

if (document.getElementById("capability-data")) {
  renderCapability();
}
