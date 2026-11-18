import copy
import csv
import json
import unittest
from collections import defaultdict

from bench import config
from bench.controlled import DESIGN, schedule, validate_design
from bench.controlled_report import PUBLISHED, paired_values, run_metrics, summarize


class ControlledBenchmarkTests(unittest.TestCase):
    def test_rejects_changes_to_more_than_one_setting(self):
        design = json.loads(DESIGN.read_text())
        models = {m["id"]: m for m in config.enabled_models()}
        validate_design(design, models)
        broken = copy.deepcopy(design)
        broken["experiments"][0]["changed"]["clients"] += 1
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_design(broken, models)

    def test_balances_launch_order(self):
        self.assertEqual([schedule(i)[0] for i in range(1, 7)], ["baseline", "changed"] * 3)

    def test_changes_are_calculated_within_pairs(self):
        pairs = [{"baseline": {"score": a}, "changed": {"score": b}}
                 for a, b in [(1, 10), (10, 2), (20, 21), (None, 25)]]
        stats = paired_values(pairs, "score")
        self.assertEqual((stats["min_delta"], stats["median_delta"], stats["max_delta"], stats["pairs"]),
                         (-8, 1, 9, 3))

    def test_quality_and_latency_use_their_respective_denominators(self):
        rows = [
            dict(status="correct", first_answer_ms="499", complete_ms="5000", output_tokens="10"),
            dict(status="wrong_value", first_answer_ms="300", complete_ms="8000", output_tokens="20"),
            dict(status="transport_error", first_answer_ms="", complete_ms="30000", output_tokens=""),
        ]
        run = dict(seconds=10, peak_vram_mib=900, before_launch_vram_mib=200)
        design = dict(first_answer_ms=500, complete_ms=5000)
        values = run_metrics(rows, run, design)
        self.assertEqual(values["correct"], 1)
        self.assertEqual(values["on_time"], 1)
        self.assertEqual(values["goodput"], 6)
        self.assertEqual(values["complete_ms"], 7850)
        self.assertEqual(values["output_tps"], 3)
        self.assertEqual(values["delta_mib"], 700)

    def test_telemetry_reproduces_published_peaks(self):
        manifest = json.loads((PUBLISHED / "manifest.json").read_text())
        peaks = defaultdict(list)
        with (PUBLISHED / "gpu.tsv").open(newline="", encoding="utf-8") as samples:
            for sample in csv.DictReader(samples, delimiter="\t"):
                key = sample["experiment"], int(sample["pair"]), sample["arm"]
                peaks[key].append(int(sample["memory.used [MiB]"].removesuffix(" MiB")))
        self.assertEqual(len(peaks), len(manifest["runs"]))
        for run in manifest["runs"]:
            key = run["experiment"], run["pair"], run["arm"]
            self.assertEqual(max(run["ready_vram_mib"], *peaks[key]), run["peak_vram_mib"])

    def test_plot_data_matches_archived_pairs(self):
        data = summarize(PUBLISHED)
        path = config.ROOT / "docs/data/controlled-pairs.tsv"
        with path.open(newline="", encoding="utf-8") as source:
            rows = {(row["comparison"], int(row["pair"]), row["metric"]): row
                    for row in csv.DictReader(source, delimiter="\t")}
        self.assertEqual(len(rows), 5 * 6 * len(data["metrics"]))
        for experiment in data["experiments"]:
            for pair in experiment["pairs"]:
                for metric, (_, unit) in data["metrics"].items():
                    row = rows[experiment["id"], pair["number"], metric]
                    a, b = pair["baseline"][metric], pair["changed"][metric]
                    self.assertEqual(row["first_arm"], pair["order"][0])
                    self.assertEqual(row["unit"], unit)
                    self.assertEqual(float(row["a"]), a)
                    self.assertEqual(float(row["b"]), b)
                    self.assertEqual(float(row["b_minus_a"]), b - a)

    def test_published_archive(self):
        data = summarize(PUBLISHED)
        self.assertEqual(data["request_count"], 1080)
        self.assertEqual(data["pair_count"], 6)
        self.assertEqual(len(data["experiments"]), 5)
        self.assertTrue(all(item["summary"]["peak_mib"]["pairs"] == 6 for item in data["experiments"]))


if __name__ == "__main__":
    unittest.main()
