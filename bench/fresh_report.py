"""Summarize the expanded corpus and estimate matched case-level differences."""
import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from . import config, fresh, home_report
from .stats import percentile

ANALYSIS = config.ROOT / "configs/fresh_analysis.json"
SOURCES = {"llmstructbench2": "LLMStructBench2", "home_holdout": "Home Lab holdout"}


def observations(rows, budget, context_per_slot):
    statuses = Counter(row["status"] for row in rows)
    completed = [row for row in rows if row["status"] != "transport_error"]
    visible = [float(row["first_answer_ms"]) for row in completed if row["first_answer_ms"]]
    finishing = [float(row["complete_ms"]) for row in completed]
    masking = [int(row["redaction_leak"]) for row in rows if row["redaction_leak"]]
    input_tokens = [int(row["input_tokens"]) for row in completed if row["input_tokens"]]
    return {
        "n": len(rows), "correct": statuses["correct"],
        "timely": sum(home_report.timely(row, budget) for row in rows),
        "valid_json": statuses["correct"] + statuses["wrong_value"],
        "fence_recovered": sum(int(row["fence_correct"]) for row in rows),
        "statuses": dict(sorted(statuses.items())), "visible_n": len(visible),
        "completed_n": len(completed), "first_p95_ms": percentile(visible, 95),
        "complete_p95_ms": percentile(finishing, 95),
        "mask_leaks": sum(masking), "mask_visible": len(masking),
        "max_input_tokens": max(input_tokens, default=None),
        "context_limit_rows": sum(
            int(row["input_tokens"]) + int(row["output_tokens"]) >= context_per_slot - 1
            for row in completed if row["input_tokens"] and row["output_tokens"]
        ),
    }


def bootstrap(groups, replicates, seed, level):
    """Resample matched cases within the frozen stratum sizes."""
    rng = random.Random(seed)
    n = sum(map(len, groups))
    draws = [100 * sum(sum(rng.choices(group, k=len(group))) for group in groups) / n
             for _ in range(replicates)]
    tail = 50 * (1 - level)
    return {
        "delta_pp": 100 * sum(map(sum, groups)) / n, "n": n,
        "lo_pp": percentile(draws, tail), "hi_pp": percentile(draws, 100 - tail),
        "discordant": sum(value != 0 for group in groups for value in group),
    }


def wins(row, outcome, budget):
    return int(row["status"] == "correct") if outcome == "correct" else int(home_report.timely(row, budget))


def summarize(path):
    manifest, groups, _ = home_report.read_run(path)
    settings = manifest["settings"]
    analysis = json.loads(ANALYSIS.read_text())
    scenario, budget = next(iter(settings["scenarios"].items()))
    if len(settings["scenarios"]) != 1 or settings["repeats"] != 1:
        raise ValueError("the expanded study uses one measured request per case and model")
    tasks = {task["id"]: task for task in map(json.loads, (path / "tasks.jsonl").read_text().splitlines())}
    by_source = {key: [task for task in tasks.values() if task["source"] == key] for key in SOURCES}
    if set(tasks) != {task["id"] for group in by_source.values() for task in group}:
        raise ValueError("invalid task-source coverage")
    source_counts = {key: len(group) for key, group in by_source.items()}
    arms, case_rows = [], {}
    for run in manifest["arms"]:
        arm = run["arm"]
        rows = groups[arm, scenario]
        case_rows[arm] = {row["task"]: row for row in rows}
        context = run["context_per_slot"]
        if context != settings["context"] // settings["slots"] or run["offloaded_layers"] <= 0:
            raise ValueError(f"unexpected launch settings for {arm}")
        source_scores, strata = {}, {}
        for source, source_tasks in by_source.items():
            source_rows = [case_rows[arm][task["id"]] for task in source_tasks]
            source_scores[source] = observations(source_rows, budget, context)
            strata[source] = {
                label: observations([case_rows[arm][task["id"]] for task in source_tasks
                                     if task["stratum"] == label], budget, context)
                for label in sorted({task["stratum"] for task in source_tasks})
            }
        seconds = run["windows"][0]["seconds"]
        mixed = observations(rows, budget, context)
        mixed["goodput_per_min"] = 60 * mixed["timely"] / seconds
        output = [int(row["output_tokens"]) for row in rows if row["output_tokens"]]
        mixed["output_tps"] = sum(output) / seconds if len(output) == len(rows) else None
        arms.append({"arm": arm, "name": run["name"], "engine": run["engine_image"],
                     "peak_mib": run["peak_vram_mib"], "scores": source_scores,
                     "strata": strata, "mixed": mixed})
    effects = []
    for comparison in analysis["comparisons"]:
        left, right = (case_rows[comparison[side]] for side in ("baseline", "changed"))
        results = {}
        for source, cases in by_source.items():
            strata_fields = analysis["strata"][source]
            strata = defaultdict(list)
            for case in cases:
                strata[tuple(case[field] for field in strata_fields)].append(case["id"])
            results[source] = {}
            for outcome in analysis["outcomes"]:
                differences = [[wins(right[task], outcome, budget) - wins(left[task], outcome, budget)
                                for task in group] for group in strata.values()]
                results[source][outcome] = bootstrap(differences, analysis["bootstrap_replicates"],
                                                      analysis["bootstrap_seed"], analysis["confidence_level"])
        effects.append(comparison | {"results": results})
    return {
        "sources": SOURCES, "source_counts": source_counts, "task_count": len(tasks),
        "n_requests": sum(arm["mixed"]["n"] for arm in arms),
        "budget": budget, "analysis": analysis, "effects": effects, "models": arms,
        "gpu": manifest["gpu"], "platform": manifest["platform"],
        "started_utc": manifest["started_utc"], "finished_utc": manifest["finished_utc"],
    }


def markdown(data):
    """Render the technical report's tables and figure captions from the archive."""
    pair = next(item for item in data["effects"]
                if item["baseline"] == "qwen3_5_2b_light" and item["changed"] == "qwen3_5_4b_compact")
    gains = pair["results"]

    def interval(source):
        result = gains[source]["correct"]
        return (f"{result['delta_pp']:+.1f} percentage points "
                f"(95% case-bootstrap interval {result['lo_pp']:+.1f} to {result['hi_pp']:+.1f})")

    lines = [
        "For Qwen3.5-2B → 4B, strict exact match increased by",
        f"{interval('llmstructbench2')} on the public corpus and by",
        f"{interval('home_holdout')} on the bilingual holdout.",
        "",
        "![Exact match and on-time request share by corpus and deployment](assets/figures/fresh.svg)",
        "",
        "**Figure 1 | Deployment outcomes by corpus.** Each marker summarizes 96",
        "distinct cases. Panel (a) uses strict exact JSON match. Panel (b) also",
        "requires a visible reply within 1 s and completion within 12 s.",
        "Marker shapes distinguish corpora. Vertical offsets separate the markers.",
        "",
        "**Table 2 | Exact and on-time counts.** Every cell has a denominator of",
        "96 cases. Spark uses the XHToken build. The other deployments use upstream llama.cpp.",
        "",
        "| Deployment | Public exact | Public on time | Holdout exact | Holdout on time |",
        "|---|---:|---:|---:|---:|",
    ]
    models = sorted(data["models"], key=lambda model: (
        -model["scores"]["llmstructbench2"]["correct"], -model["scores"]["home_holdout"]["correct"],
        model["name"]))
    for model in models:
        values = [model["name"]] + [str(model["scores"][source][outcome])
                                    for source in data["sources"] for outcome in ("correct", "timely")]
        lines.append("| " + " | ".join(values) + " |")
    lines += [
        "",
        "**Table 3 | Timing and memory.** Latency values are p95 in milliseconds,",
        "with the exact number of observations in parentheses. The mixed run’s",
        "usable job rate and peak VRAM cover both corpora.",
        "",
        "| Deployment | Public first visible | Holdout first visible | Public completion | Holdout completion | Mixed usable jobs/min | Peak VRAM (MiB) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    def latency(score, key, n):
        value = score[key]
        return f"{value:.0f} ({score[n]})" if value is not None else "— (0)"

    for model in models:
        cells = [model["name"]]
        for key, n in (("first_p95_ms", "visible_n"), ("complete_p95_ms", "completed_n")):
            cells.extend(latency(model["scores"][source], key, n) for source in data["sources"])
        cells += [f"{model['mixed']['goodput_per_min']:.1f}", f"{model['peak_mib']:.0f}"]
        lines.append("| " + " | ".join(cells) + " |")

    lines += [
        "",
        "**Table 4 | Failure modes.** Counts out of 96 per corpus. The columns",
        "distinguish completed but mismatched JSON, JSON parse failures and truncated streams.",
        "",
        "| Deployment | Public wrong value | Public invalid JSON | Public truncated | Holdout wrong value | Holdout invalid JSON | Holdout truncated |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in models:
        cells = [model["name"]]
        cells.extend(str(model["scores"][source]["statuses"].get(status, 0))
                     for source in data["sources"]
                     for status in ("wrong_value", "invalid_json", "truncated"))
        lines.append("| " + " | ".join(cells) + " |")
    statuses = Counter()
    for model in models:
        statuses.update(model["mixed"]["statuses"])
    lines += [
        "",
        f"Across {data['n_requests']:,} measured requests, "
        f"{statuses['transport_error']} had a transport failure, "
        f"{statuses['truncated']} were marked truncated and "
        f"{sum(model['mixed']['context_limit_rows'] for model in models)} reached the vicinity "
        "of the context boundary (reported input plus output ≥ slot context minus one token).",
        "",
        "![Paired exact-match and on-time differences with pointwise bootstrap intervals](assets/figures/fresh-effects.svg)",
        "",
        "**Figure 2 | Matched case-level contrasts.** Markers represent changes from",
        "the first deployment in each label to the second, based on 96 matched",
        "cases per corpus. Horizontal segments are pointwise 95% stratified",
        "case-bootstrap intervals (5,000 resamples). The vertical reference is zero.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=fresh.PUBLISHED)
    parser.add_argument("--markdown", action="store_true", help="Emit the publication tables and captions")
    args = parser.parse_args()
    data = summarize(args.directory)
    print(markdown(data) if args.markdown else json.dumps(data, ensure_ascii=False, indent=2))
