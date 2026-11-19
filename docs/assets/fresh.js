/* The two corpora retain their own denominators and latency populations. */
"use strict";

if (D.fresh) {
  const data = D.fresh;
  const host = document.getElementById("fresh");
  host.innerHTML = `
    <div class="home-lead"><div>
      <h2>Expanded Home Lab tests</h2>
      <p>${data.task_count} distinct cases × ${data.models.length} deployments.
         Two clients and two server slots. An on-time reply starts within
         ${data.budget.first_answer_ms / 1000} s and finishes within ${data.budget.complete_ms / 1000} s.</p>
      <a href="https://github.com/jfang2048/llm_benchmark/blob/main/docs/fresh.md">Methods, figures and raw data</a>${data.extension ?
        ' · <a href="https://github.com/jfang2048/llm_benchmark/blob/main/docs/model-refresh.md">Model refresh and bridge run</a>' : ""}
    </div></div>
    <div class="home-controls">
      <label class="home-control" for="fresh-source">Corpus
        <select id="fresh-source">${Object.entries(data.sources).map(([id, name]) =>
          `<option value="${id}">${name} (n = ${data.source_counts[id]})</option>`).join("")}</select>
      </label>
      <label class="home-control" for="fresh-outcome">Outcome
        <select id="fresh-outcome"><option value="correct">Exact JSON match</option>
          <option value="timely">Correct and on time</option></select>
      </label>
      <label class="home-control" for="fresh-stratum">Stratum
        <select id="fresh-stratum"></select>
      </label>
    </div>
    <div id="fresh-plot"></div>
    <div class="datatable-wrap home-table" role="region" tabindex="0" aria-label="Expanded tests model results">
      <table class="datatable"><thead><tr>
        <th scope="col">Deployment</th>${data.extension ? '<th scope="col">Sweep</th>' : ""}<th scope="col">Exact match</th>
        <th scope="col">Correct on time</th><th scope="col">First visible p95 (ms)</th>
        <th scope="col">Completion p95 (ms)</th><th scope="col">Peak VRAM (MiB)</th>
      </tr></thead><tbody id="fresh-rows"></tbody></table>
    </div>
    <p class="note">Latency percentiles use completed streams. First visible p95 also requires visible text.
      Each VRAM peak comes from the full mixed-corpus run. † Spark uses the XHToken build.
      ${data.extension ? "Open squares mark refresh models." : ""}</p>`;
  const corpus = document.getElementById("fresh-source");
  const metric = document.getElementById("fresh-outcome");
  const slice = document.getElementById("fresh-stratum");
  const chart = document.getElementById("fresh-plot");
  const table = document.getElementById("fresh-rows");
  const label = (model) => model.name.replace(" (text-only)", " (text)") + (model.arm === "spark_llama" ? " †" : "");
  const pretty = (value) => value === null ? "—" : Math.round(value).toLocaleString("en-US");
  const share = (count, n) => 100 * count / n;

  function populateStrata() {
    slice.replaceChildren(new Option("All cases", ""));
    for (const key of Object.keys(data.models[0].strata[corpus.value])) {
      slice.add(new Option(key.replaceAll("_", " "), key));
    }
  }

  function renderFresh() {
    const source = corpus.value;
    const key = metric.value;
    const rows = data.models.map((model) => ({
      model, score: slice.value ? model.strata[source][slice.value] : model.scores[source],
    })).sort((a, b) => b.score[key] - a.score[key] || label(a.model).localeCompare(label(b.model)));
    table.innerHTML = rows.map(({model, score}) => `<tr>
      <th scope="row">${label(model)}</th>${data.extension ? `<td>${model.batch === "refresh" ? "Refresh" : "Original"}</td>` : ""}
      <td>${score.correct}/${score.n}</td>
      <td>${score.timely}/${score.n}</td><td>${pretty(score.first_p95_ms)}</td>
      <td>${pretty(score.complete_p95_ms)}</td><td>${pretty(model.peak_mib)}</td>
    </tr>`).join("");
    const layout = baseLayout("", "Requests (%)", "");
    layout.margin = {l: chart.clientWidth < 640 ? 128 : 212, r: 24, t: 8, b: 58};
    layout.height = 385;
    layout.xaxis.range = [-3, 103];
    layout.xaxis.dtick = 25;
    layout.yaxis.autorange = "reversed";
    layout.yaxis.tickfont = {size: chart.clientWidth < 640 ? 9 : 11};
    const names = rows.map(({model}) => label(model));
    const compact = chart.clientWidth < 640;
    const shortNames = names.map((name) => name.replace("DeepSeek-R1-Distill-Llama-8B", "DeepSeek-R1 8B")
      .replace("LFM2.5-1.2B-Instruct", "LFM2.5-1.2B").replace("Phi-4-mini-instruct", "Phi-4-mini"));
    layout.yaxis.tickmode = "array";
    layout.yaxis.tickvals = names;
    layout.yaxis.ticktext = compact ? shortNames : names;
    Plotly.react(chart, [{
      type: "scatter", mode: "markers", y: names, x: rows.map(({score}) => share(score[key], score.n)),
      customdata: rows.map(({score}) => [score[key], score.n]),
      marker: {color: "#175a87", size: 8, symbol: rows.map(({model}) => model.arm === "spark_llama" ? "diamond-open" : model.batch === "refresh" ? "square-open" : "circle")},
      hovertemplate: "%{y}<br>%{customdata[0]}/%{customdata[1]} (%{x:.1f}%)<extra></extra>",
    }], layout, {...CONFIG, displayModeBar: false});
  }
  corpus.addEventListener("change", () => {populateStrata(); renderFresh();});
  slice.addEventListener("change", renderFresh);
  metric.addEventListener("change", renderFresh);
  matchMedia("(max-width: 700px)").addEventListener("change", renderFresh);
  populateStrata();
  renderFresh();
}
