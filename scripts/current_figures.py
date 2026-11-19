"""Generate the current study's editable vector figures and paired plot data."""
import csv
from io import StringIO
from math import copysign
from statistics import median

import matplotlib as mpl

mpl.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

COMPARISONS = {
    "size-small": "Qwen3.5 0.8B → 2B",
    "size-medium": "Qwen3.5 2B → 4B",
    "context": "Context 4,096 → 16,384",
    "concurrency": "Clients 1 → 4",
    "engine": "Upstream → XHToken",
}
PANELS = (
    ("on_time", "Correct on-time replies", "replies"),
    ("goodput", "Usable job rate", "jobs/min"),
    ("first_ms", "First visible answer p95", "ms"),
    ("peak_mib", "Peak device VRAM", "MiB"),
)
INK, BLUE, RANGE = "#181818", "#175a87", "#666666"
STYLE = {
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.linewidth": 0.65,
    "xtick.major.width": 0.65,
    "ytick.major.size": 0,
    "svg.fonttype": "none",
    "svg.hashsalt": "home-lab-current",
}


def marker_style(baseline_first):
    return dict(marker="o" if baseline_first else "s", markerfacecolor=BLUE if baseline_first else "white",
                markeredgecolor=BLUE, markeredgewidth=0.8, markersize=2.8, linestyle="none")


def legend_marker(label, **style):
    return Line2D([], [], label=label, **style)


def save_svg(fig, path, title, description):
    svg = StringIO()
    fig.savefig(svg, format="svg", metadata={"Date": None, "Title": title, "Description": description})
    path.write_text("\n".join(line.rstrip() for line in svg.getvalue().splitlines()) + "\n", encoding="utf-8")
    plt.close(fig)


def paired_figure(run, path):
    """Four effect-size panels with one observation per matched launch pair."""
    experiments = run["experiments"]
    names = [COMPARISONS[e["id"]] for e in experiments]
    with mpl.rc_context(STYLE):
        fig, axes = plt.subplots(2, 2, figsize=(7.4, 4.55), sharey=True)
        fig.subplots_adjust(left=0.235, right=0.97, bottom=0.18, top=0.93, hspace=0.62, wspace=0.28)
        for index, (ax, (key, title, unit)) in enumerate(zip(axes.flat, PANELS, strict=True)):
            ax.set_title(f"{chr(ord('a') + index)}   {title}", loc="left", fontsize=9, fontweight="bold", pad=8)
            ax.axvline(0, color="#b5b5b5", linewidth=0.85, zorder=0)
            ax.set_yticks(range(len(names)), labels=names)
            ax.set_ylim(len(names) - 0.5, -0.5)
            ax.set_xlabel(f"Paired change, B − A ({unit})")
            ax.xaxis.set_major_locator(MaxNLocator(5, integer=key == "on_time"))
            ax.margins(x=0.12)
            for row, experiment in enumerate(experiments):
                pairs = experiment["pairs"]
                deltas = []
                for pair in pairs:
                    a, b = pair["baseline"][key], pair["changed"][key]
                    if a is None or b is None:
                        continue
                    delta = b - a
                    deltas.append(delta)
                    centered = pair["number"] - (len(pairs) + 1) / 2
                    offset = 0.14 * (centered + copysign(0.5, centered))
                    ax.plot(delta, row + offset, zorder=3, **marker_style(pair["order"][0] == "baseline"))
                if deltas:
                    ax.hlines(row, min(deltas), max(deltas), colors=RANGE, linewidth=0.9)
                    ax.plot(median(deltas), row, "D", color=INK, markersize=3.5, zorder=4)
        handles = [
            legend_marker("A first", **marker_style(True)),
            legend_marker("B first", **marker_style(False)),
            legend_marker("Paired median", marker="D", color=INK, markersize=3.5, linestyle="none"),
            legend_marker("Observed min–max", color=RANGE, linewidth=0.9),
        ]
        fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.51, 0.015), ncols=4, frameon=False)
        save_svg(fig, path, "Single-factor Home Lab trials",
                 "Four panels show individual paired changes, paired medians and observed ranges. "
                 "Circles indicate A first and open squares indicate B first.")


def home_figure(run, path):
    """On-time desk counts for the two scoring rules applied to the same replies."""
    ranked = sorted(run["models"], key=lambda model: (
        -model["scenarios"]["desk"]["timely"],
        -model["scenarios"]["desk"]["with_fence"]["timely"], model["name"]))
    names = [m["name"].replace(" (text-only)", " (text)") for m in ranked]
    n = run["cases"] * run["repeats"]
    with mpl.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.4, 4.4))
        fig.subplots_adjust(left=0.34, right=0.96, bottom=0.20, top=0.98)
        for i, model in enumerate(ranked):
            desk = model["scenarios"]["desk"]
            raw, fence = desk["timely"], desk["with_fence"]["timely"]
            ax.plot([raw, fence], [i - 0.12, i + 0.12], color=RANGE, linewidth=0.7)
            ax.plot(raw, i - 0.12, **marker_style(True))
            ax.plot(fence, i + 0.12, **marker_style(False))
        ax.set_yticks(range(len(names)), labels=names)
        ax.set_ylim(len(names) - 0.5, -0.5)
        ax.set_xlim(-0.025 * n, 1.025 * n)
        ax.set_xticks([round(n * fraction / 6) for fraction in range(7)])
        ax.set_xlabel(f"Correct on-time replies (out of {n})")
        fig.legend(handles=[legend_marker("Raw JSON", **marker_style(True)),
                            legend_marker("One JSON fence accepted", **marker_style(False))],
                   loc="lower center", bbox_to_anchor=(0.63, 0.02), ncols=2, frameon=False)
        save_svg(fig, path, "Home Lab deployment scorecard",
                 "Correct on-time desk replies per deployment with two parsing rules applied to the same streams.")


def write_paired_tsv(run, path):
    """Export one row per comparison, launch pair and metric."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["comparison", "pair", "first_arm", "metric", "unit", "a", "b", "b_minus_a"])
        for experiment in run["experiments"]:
            for pair in experiment["pairs"]:
                for metric, (_, unit) in run["metrics"].items():
                    a, b = pair["baseline"][metric], pair["changed"][metric]
                    delta = b - a if a is not None and b is not None else None
                    writer.writerow([experiment["id"], pair["number"], pair["order"][0], metric, unit, a, b, delta])


def fresh_figure(run, path):
    """Correctness and deadline attainment, split by corpus."""
    models = sorted(run["models"], key=lambda model: (
        -model["scores"]["llmstructbench2"]["correct"],
        -model["scores"]["home_holdout"]["correct"], model["name"]))
    names = [model["name"].replace(" (text-only)", " (text)") for model in models]
    with mpl.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(7.4, 4.35), sharey=True)
        fig.subplots_adjust(left=0.33, right=0.97, bottom=0.19, top=0.92, wspace=0.25)
        for ax, (key, title) in zip(axes, (("correct", "a   Exact JSON match"),
                                          ("timely", "b   Correct and on time")), strict=True):
            ax.set_title(title, loc="left", fontsize=9, fontweight="bold")
            for depth, (source, offset) in enumerate(zip(run["sources"], (-0.14, 0.14), strict=True)):
                for row, model in enumerate(models):
                    scores = model["scores"][source]
                    ax.plot(100 * scores[key] / scores["n"], row + offset, **marker_style(depth == 0))
            ax.set_yticks(range(len(names)), labels=names)
            ax.set_ylim(len(names) - 0.5, -0.5)
            ax.set_xlim(-3, 103)
            ax.set_xticks([0, 25, 50, 75, 100])
            ax.set_xlabel("Requests (%)")
        fig.legend(handles=[legend_marker(label, **marker_style(index == 0))
                            for index, label in enumerate(run["sources"].values())],
                   loc="lower center", bbox_to_anchor=(0.61, 0.02), ncols=2, frameon=False)
        save_svg(fig, path, "Expanded Home Lab deployment results",
                 "Exact JSON match and correct on-time requests across 13 deployments and two evaluation corpora.")


def fresh_effects_figure(run, path):
    names = [item["label"].replace(" to ", " → ") for item in run["effects"]]
    with mpl.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(7.4, 2.95), sharey=True)
        fig.subplots_adjust(left=0.30, right=0.97, bottom=0.27, top=0.86, wspace=0.23)
        for ax, (metric, title) in zip(axes, (("correct", "a   Exact JSON match"),
                                              ("timely", "b   Correct and on time")), strict=True):
            ax.set_title(title, loc="left", fontsize=9, fontweight="bold")
            ax.axvline(0, color="#b5b5b5", linewidth=0.85, zorder=0)
            for i, item in enumerate(run["effects"]):
                for depth, (source, offset) in enumerate(zip(run["sources"], (-0.17, 0.17), strict=True)):
                    result = item["results"][source][metric]
                    y = i + offset
                    ax.hlines(y, result["lo_pp"], result["hi_pp"], colors=RANGE, linewidth=0.85)
                    ax.plot(result["delta_pp"], y, zorder=4, **marker_style(depth == 0))
            ax.set_yticks(range(len(names)), labels=names)
            ax.set_ylim(len(names) - 0.5, -0.5)
            ax.xaxis.set_major_locator(MaxNLocator(5, integer=True))
            ax.set_xlabel("Paired change (percentage points)")
        fig.legend(handles=[legend_marker(label, **marker_style(index == 0))
                            for index, label in enumerate(run["sources"].values())],
                   loc="lower center", bbox_to_anchor=(0.60, 0.018), ncols=2, frameon=False)
        save_svg(fig, path, "Paired exact-match and deadline attainment effects",
                 "Paired percentage point differences and stratified case-bootstrap intervals by corpus.")
