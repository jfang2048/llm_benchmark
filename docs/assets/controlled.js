/* Repeat-level changes for the single-factor Home Lab experiments. */
"use strict";

if (D.controlled) {
  const data = D.controlled;
  const host = document.getElementById("controlled");
  const names = {
    "size-small": ["Qwen3.5 · 0.8B → 2B", "0.8→2B"],
    "size-medium": ["Qwen3.5 · 2B → 4B", "2→4B"],
    context: ["Context · 4,096 → 16,384", "Context"],
    concurrency: ["Clients · 1 → 4", "Clients"],
    engine: ["Engine · upstream → XHToken", "Engine"],
  };
  const number = (v) => v === null ? "—" : v.toLocaleString("en-US", {maximumFractionDigits: 2});
  const signed = (v) => (v > 0 ? "+" : "") + number(v);
  host.innerHTML = `
    <div class="paired-heading">
      <div><h2>Paired inference experiments</h2>
        <p>${data.request_count.toLocaleString()} measured requests across five comparisons. Each comparison uses
          ${data.pair_count} launch pairs and ${data.task_count} cases per launch.</p>
        <a href="https://github.com/jfang2048/llm_benchmark/blob/main/docs/controlled.md">Methods and results</a> · <a href="data/controlled-pairs.tsv" download>Plot data (TSV)</a>
      </div>
      <label class="home-control" for="paired-metric">Metric
        <select id="paired-metric">${Object.entries(data.metrics).map(([key, [label]]) =>
          `<option value="${key}"${key === "goodput" ? " selected" : ""}>${label}</option>`).join("")}</select>
      </label>
    </div>
    <div id="paired-plot"></div>
    <div class="paired-key">
      <span><i class="paired-dot"></i>A first</span>
      <span><i class="paired-square"></i>B first</span>
      <span><i class="paired-diamond"></i>Paired median</span>
      <span><i class="paired-range"></i>Observed min–max</span>
    </div>
    <div class="datatable-wrap home-table" role="region" tabindex="0" aria-label="Paired comparisons summary">
      <table class="datatable">
        <thead><tr><th scope="col">Change</th><th scope="col">A median</th><th scope="col">B median</th>
          <th scope="col">Median B−A</th><th scope="col">Observed min–max</th><th scope="col">Pairs</th></tr></thead>
        <tbody id="paired-summary"></tbody>
      </table>
    </div>
    <p class="note">Each circle or square is one B−A difference within a launch pair.
      Vertical offsets separate observations. The reference line marks zero change.</p>`;

  const selector = document.getElementById("paired-metric");
  const plot = document.getElementById("paired-plot");
  function renderPairs() {
    const metric = selector.value;
    const unit = data.metrics[metric][1];
    const narrow = plot.clientWidth < 610;
    const labels = data.experiments.map(({id}) => names[id]?.[narrow ? 1 : 0] || id);
    const points = {x: [], y: [], customdata: []};
    const pairSymbols = [];
    const ranges = {x: [], y: []};
    const center = {x: [], y: [], customdata: []};
    document.getElementById("paired-summary").innerHTML = data.experiments.map((experiment, i) => {
      const stats = experiment.summary[metric];
      const label = names[experiment.id]?.[0] || experiment.id;
      const row = data.experiments.length - i;
      if (stats.pairs) {
        ranges.x.push(stats.min_delta, stats.max_delta, null);
        ranges.y.push(row, row, null);
        center.x.push(stats.median_delta);
        center.y.push(row);
        center.customdata.push(label);
      }
      for (const pair of experiment.pairs) {
        const a = pair.baseline[metric], b = pair.changed[metric];
        if (a === null || b === null) continue;
        points.x.push(b - a);
        pairSymbols.push(pair.order[0] === "baseline" ? "circle" : "square-open");
        const centered = pair.number - (data.pair_count + 1) / 2;
        points.y.push(row + 0.13 * (centered + 0.5 * Math.sign(centered)));
        points.customdata.push([label, pair.number, pair.order[0] === "baseline" ? "A then B" : "B then A", a, b]);
      }
      const span = stats.pairs ? signed(stats.min_delta) + " to " + signed(stats.max_delta) : "—";
      return `<tr><th scope="row">${label}</th><td>${number(stats.baseline)} ${unit}</td>
        <td>${number(stats.changed)} ${unit}</td><td><strong>${signed(stats.median_delta)}</strong></td>
        <td>${span}</td><td>${stats.pairs}</td></tr>`;
    }).join("");

    const layout = baseLayout("", "Paired change, B − A (" + unit + ")", "");
    layout.margin = {l: narrow ? 54 : 212, r: 22, b: 54, t: 12};
    layout.height = 290;
    layout.yaxis = {
      tickvals: labels.map((_, i) => labels.length - i),
      ticktext: labels, range: [0.5, labels.length + 0.5], fixedrange: true,
    };
    const limit = Math.max(1, ...points.x.map(Math.abs));
    layout.xaxis.range = [-1.15 * limit, 1.15 * limit];
    layout.xaxis.zeroline = true;
    layout.xaxis.zerolinecolor = "#83929c";
    const details = "%{customdata[0]}<br>Pair %{customdata[1]} · %{customdata[2]}" +
      "<br>A %{customdata[3]:.2f} · B %{customdata[4]:.2f}<br>Δ %{x:+.2f} " + unit + "<extra></extra>";
    Plotly.react(plot, [
      {...ranges, type: "scatter", mode: "lines", line: {color: "#666666", width: 1.5}, hoverinfo: "skip"},
      {...points, type: "scatter", mode: "markers", marker: {color: "#175a87", size: 6, symbol: pairSymbols, line: {width: 1.1}},
        hovertemplate: details},
      {...center, type: "scatter", mode: "markers", marker: {color: "#181818", size: 9, symbol: "diamond"},
        hovertemplate: "%{customdata}<br>Median Δ %{x:+.2f} " + unit + "<extra></extra>"},
    ], {...layout, showlegend: false}, {...CONFIG, displayModeBar: false});
  }
  selector.addEventListener("change", renderPairs);
  matchMedia("(max-width: 660px)").addEventListener("change", renderPairs);
  renderPairs();
}
