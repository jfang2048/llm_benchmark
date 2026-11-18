/* Home Lab scorecard, drawn from the normalized run in bench-data. */
"use strict";

if (D.home_lab) {
  const home = D.home_lab;
  const homePlotOptions = {...CONFIG, displayModeBar: false};
  const host = document.getElementById("home-lab");
  const metricsFor = (scenario, allowFence = false, cohort = "") => home.models
    .filter((model) => !cohort || model.cohort === cohort)
    .map((model) => {
      const raw = model.scenarios[scenario];
      return {...model, ...(allowFence ? raw.with_fence : raw)};
    });
  const deskOrder = (a, b) => b.timely - a.timely || b.correct - a.correct ||
    (a.answer_p95_ms ?? Infinity) - (b.answer_p95_ms ?? Infinity);
  const batchOrder = (a, b) => b.goodput_per_min - a.goodput_per_min;
  const card = (label, model, detail) => `<div class="home-choice">
    <span>${label}</span><strong>${model.name}</strong><p>${detail}</p>
  </div>`;

  const storage = home.storage;
  const lightweightOption = home.models.some((model) => model.cohort === "lightweight_1_3b")
    ? '<span class="home-control"><label for="home-cohort">Models</label> <select id="home-cohort"><option value="">All deployments</option><option value="lightweight_1_3b">Lightweight additions</option></select></span>'
    : "";
  const storageBar = (label, milliseconds) => `<div class="home-storage-row">
    <span>${label}</span><span class="home-storage-track"><i style="width:${100 * milliseconds / Math.max(storage.linux.ready_ms, storage.windows_mount.ready_ms)}%"></i></span>
    <strong>${fmt(milliseconds / 1000, 2)} s</strong>
  </div>`;
  const storageChart = storage ? `<aside class="home-storage">
    <div><h3>Same model, two storage paths</h3>
      <p class="note">Median time to a healthy endpoint over three pre-read launches per path. Both used the same WSL2 GPU and container.</p></div>
    <div>${storageBar("WSL Linux filesystem", storage.linux.ready_ms)}
      ${storageBar("Windows mount", storage.windows_mount.ready_ms)}</div>
  </aside>` : "";
  const fit = home.fit;
  const fitChart = fit ? `<section class="home-fit" aria-labelledby="home-fit-title">
    <div class="fit-heading">
      <h3 id="home-fit-title">How much context fits in 6 GiB?</h3>
      <span class="home-control"><label for="home-fit-context">Total context</label>
        <select id="home-fit-context">${fit.contexts.map((ctx, i) =>
          `<option value="${ctx}"${i === fit.contexts.length - 1 ? " selected" : ""}>${ctx.toLocaleString()} tokens</option>`).join("")}</select></span>
    </div>
    <p class="note" id="home-fit-note"></p>
    <div id="home-fit-bars" class="home-fit-bars"></div>
    <p class="note">Peak device VRAM during startup and one short streamed reply. The probe checks layer offload and context allocation.</p>
  </section>` : "";
  host.innerHTML = `<div class="home-lead">
    <div>
      <p class="home-kicker">RTX 3060 Laptop · 6 GiB · WSL2</p>
      <h2>What would you run at home?</h2>
      <p>${home.models.length} local deployments take on the same synthetic notes, masking jobs and archive lookups.
        A usable result has to return the correct JSON within both time budgets.</p>
      <a href="https://github.com/jfang2048/llm_benchmark/blob/main/docs/home-lab.md">Read the test and setup</a>
    </div>
    <div class="home-choices" aria-live="polite"></div>
  </div>
  <div class="home-controls">
    <span class="home-control"><label for="home-scenario">Workload</label>
    <select id="home-scenario">${Object.entries(home.scenarios).map(([id, item]) =>
      `<option value="${id}">${item.label}</option>`).join("")}</select></span>
    <label class="home-fence"><input type="checkbox" id="home-fence"> Allow one JSON code fence</label>
    <span class="home-control"><label for="home-breakdown">Breakdown</label>
    <select id="home-breakdown"><option value="by_kind">Task</option><option value="by_language">Language</option></select></span>
    ${lightweightOption}<p class="note" id="home-budget"></p>
  </div>
  <div class="grid2 home-charts">
    <div><div id="home-ready-plot"></div><div class="home-key" aria-label="Chart legend">
      <span><i style="background:#08796f"></i>Correct on time</span>
      <span><i style="background:#8eb7b2"></i>Correct, late</span>
      <span><i style="background:#dce4e8"></i>Other outcomes</span>
    </div></div>
    <div id="home-tasks-plot"></div>
  </div>
  <div class="datatable-wrap home-table" role="region" tabindex="0" aria-label="Home Lab scorecard">
    <table class="datatable">
      <thead><tr><th scope="col">Deployment</th><th scope="col">Correct</th><th scope="col">Correct on time</th>
        <th scope="col">Usable/min</th><th scope="col">Output tok/s</th><th scope="col">First answer p95 (ms)</th>
        <th scope="col">Finish p95 (ms)</th><th scope="col">Peak VRAM (MiB)</th>
        <th scope="col">Masking misses / replies</th></tr></thead><tbody></tbody>
    </table>
  </div>
  ${storageChart}
  ${fitChart}
  <p class="note home-footnote">Latency percentiles use correct replies. A masking miss is a visible reply that repeated a planted identifier. The GPU peak covers the full run for each model.</p>`;

  function renderHome(scenario) {
    const settings = home.scenarios[scenario];
    const allowFence = document.getElementById("home-fence").checked;
    const cohort = document.getElementById("home-cohort")?.value || "";
    const desktop = metricsFor("desk", allowFence, cohort).sort(deskOrder)[0];
    const batch = metricsFor("burst", allowFence, cohort).sort(batchOrder)[0];
    host.querySelector(".home-choices").innerHTML =
      card("One person", desktop, `${desktop.timely}/${desktop.n} correct on time · ${fmt(desktop.peak_vram_mib, 0)} MiB peak`) +
      card("Small batch", batch, `${fmt(batch.goodput_per_min)} correct on time per minute · ${batch.timely}/${batch.n} on time`);
    const rows = metricsFor(scenario, allowFence, cohort).sort(scenario === "burst" ? batchOrder : deskOrder);
    const displayRows = [...rows].reverse();
    const names = displayRows.map((r) => r.name.replace(" (text-only)", ""));
    document.getElementById("home-budget").textContent =
      `${settings.concurrency} in flight · first answer ≤ ${settings.first_answer_ms} ms · finished ≤ ${settings.complete_ms} ms · ${home.cases * home.repeats} requests per deployment`;

    const layout = baseLayout("Jobs that fit the budget", "Requests", "");
    layout.barmode = "stack";
    layout.height = Math.max(310, rows.length * 31 + 116);
    layout.showlegend = false;
    layout.margin = {l: 145, r: 10, t: 38, b: 47};
    layout.xaxis.range = [0, home.cases * home.repeats + 0.5];
    layout.yaxis = {automargin: true, tickfont: {size: 10}, showgrid: false};
    const stack = [
      ["Correct on time", "#08796f", (r) => r.timely],
      ["Correct, late", "#8eb7b2", (r) => r.correct - r.timely],
      ["Other outcomes", "#dce4e8", (r) => r.n - r.correct],
    ];
    plot("home-ready-plot", stack.map(([label, color, value]) => ({
      name: label, marker: {color}, x: displayRows.map(value), y: names, type: "bar", orientation: "h",
      hovertemplate: "%{y}<br>%{x} requests<extra>%{fullData.name}</extra>",
    })), layout, homePlotOptions);

    const breakdown = document.getElementById("home-breakdown").value;
    const groups = breakdown === "by_language"
      ? [["en", "English"], ["zh", "Chinese"]]
      : [["extract", "Extract"], ["redact", "Mask"], ["lookup", "Find in notes"]];
    const counts = displayRows.map((r) => groups.map(([key]) => r[breakdown][key]));
    const grid = baseLayout(breakdown === "by_language" ? "Correct by language" : "Correct by task", "", "");
    grid.height = layout.height;
    grid.margin = {l: 145, r: 12, t: 38, b: 43};
    grid.yaxis = {automargin: true, tickfont: {size: 10}, showgrid: false};
    grid.xaxis = {side: "bottom", automargin: true};
    plot("home-tasks-plot", [{
      type: "heatmap", x: groups.map(([, label]) => label), y: names,
      z: counts.map((line) => line.map(({correct, n}) => correct / n)),
      text: counts.map((line) => line.map(({correct, n}) => `${correct}/${n}`)),
      texttemplate: "%{text}", textfont: {color: "#142c38", size: 11},
      hovertemplate: "%{y}<br>%{x}: %{text} correct<extra></extra>",
      zmin: 0, zmax: 1, showscale: false, xgap: 4, ygap: 3,
      colorscale: [[0, "#f7e7df"], [.5, "#e8eeeb"], [1, "#75c8b4"]],
    }], grid, homePlotOptions);

    host.querySelector("tbody").innerHTML = rows.map((r) => `<tr>
      <th scope="row">${r.name}<small>${r.quantization} · ${r.cohort === "spark_reference" ? "XHToken fork" : "upstream llama.cpp"}</small></th>
      <td>${r.correct}/${r.n}</td><td class="home-ontime">${r.timely}/${r.n}</td><td>${fmt(r.goodput_per_min)}</td>
      <td>${fmt(r.output_tok_per_s)}</td><td>${fmt(r.answer_p95_ms, 0)}</td><td>${fmt(r.complete_p95_ms, 0)}</td>
      <td>${fmt(r.peak_vram_mib, 0)}</td><td>${r.redaction_outputs ? `${r.redaction_leaks}/${r.redaction_outputs}` : "—"}</td>
    </tr>`).join("");
  }

  function renderFit(context) {
    const target = document.getElementById("home-fit-bars");
    const rows = fit.rows.filter((r) => r.context === context)
      .sort((a, b) => (a.peak_vram_mib ?? Infinity) - (b.peak_vram_mib ?? Infinity));
    document.getElementById("home-fit-note").textContent =
      `${(context / fit.slots).toLocaleString()} tokens per slot · ${fit.slots} slots · ${fit.vram_total_mib.toLocaleString()} MiB device VRAM · auto-fit off`;
    target.innerHTML = rows.map((r) => {
      const peak = r.peak_vram_mib;
      const name = r.name.replace(" (text-only)", "");
      const label = !r.fully_offloaded ? (r.status === "streamed" ? "Offload or slots unverified" : r.status.replaceAll("_", " ")) :
        `${peak?.toLocaleString() ?? "—"} MiB · ${r.offloaded_layers}/${r.total_layers} layers`;
      const ratio = r.fully_offloaded && peak !== null ? Math.min(100, 100 * peak / fit.vram_total_mib) : 0;
      return `<div class="home-fit-row">
        <span>${name}</span><span class="home-storage-track" aria-hidden="true">
          <i style="width:${ratio}%" class="${ratio >= 90 ? "near-limit" : ""}"></i></span><strong>${label}</strong>
      </div>`;
    }).join("");
  }

  const context = document.getElementById("home-fit-context");
  if (context) {
    const updateFit = () => renderFit(Number(context.value));
    context.addEventListener("change", updateFit);
    updateFit();
  }
  const scenario = document.getElementById("home-scenario");
  const rerender = () => renderHome(scenario.value);
  scenario.addEventListener("change", rerender);
  document.getElementById("home-fence").addEventListener("change", rerender);
  document.getElementById("home-breakdown").addEventListener("change", rerender);
  document.getElementById("home-cohort")?.addEventListener("change", rerender);
  rerender();
}
