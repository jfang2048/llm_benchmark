"""Merge compatible measurements and reject incompatible baselines."""
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bench.home import COLUMNS
from bench.home_merge import merge_runs
from bench.home_report import load_fit, summarize


def fixture(directory, arm, budget=500, include_reasoning_flag=False):
    directory.mkdir()
    tasks = '{"id":"a","kind":"extract","language":"en"}\n'
    (directory / "tasks.jsonl").write_text(tasks)
    manifest = {
        "settings": {
            "cohorts": [arm], "disable_reasoning_for": [arm] if include_reasoning_flag else [],
            "slots": 2, "context": 4096, "repeats": 1,
            "scenarios": {"desk": {"first_answer_ms": budget, "complete_ms": 5000}},
        },
        "gpu": "gpu", "platform": "platform",
        "tasks_sha256": hashlib.sha256(tasks.encode()).hexdigest(),
        "settings_sha256": "settings", "source_commit": "commit",
        "arms": [{
            "arm": arm, "name": arm, "cohort": arm, "quantization": "Q4_K_M",
            "engine_image": "llama.cpp", "startup_ms": 50, "peak_vram_mib": 800,
            "windows": [{"scenario": "desk", "repeat": 1, "seconds": 2}],
        }],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with (directory / "requests.tsv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerow({
            "arm": arm, "scenario": "desk", "repeat": 1, "task": "a", "kind": "extract",
            "language": "en", "status": "correct", "first_token_ms": 90, "first_answer_ms": 100,
            "complete_ms": 300, "redaction_leak": "", "fence_correct": 0,
        })
    return directory


class MergeTest(unittest.TestCase):
    def test_join_keeps_per_arm_provenance(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = fixture(root / "one", "a")
            two = fixture(root / "two", "b", include_reasoning_flag=True)
            output = root / "merge"
            merge_runs([one, two], output)
            result = summarize(output)
            self.assertEqual([m["scenarios"]["desk"]["timely"] for m in result["models"]], [1, 1])
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["settings"]["disable_reasoning_for"], ["b"])
            self.assertEqual([p["arms"] for p in manifest["source_runs"]], [["a"], ["b"]])

    def test_reject_changed_deadline(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = fixture(root / "one", "a")
            two = fixture(root / "two", "b", budget=700)
            with self.assertRaisesRegex(ValueError, "different protocol"):
                merge_runs([one, two], root / "merge")
            self.assertFalse((root / "merge").exists())

    def test_context_fit_requires_all_layers_and_requested_slot_size(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fit.json"
            base = {"gpu": "GPU, 6144, driver", "platform": "wsl", "slots": 2,
                    "contexts": [4096, 8192, 16384], "gpu_layers": 999, "auto_fit": False}
            row = {"arm": "a", "peak_vram_mib": 2100, "status": "streamed",
                   "offloaded_layers": 20, "total_layers": 20}
            base["rows"] = [dict(row, context=4096, per_slot_context=2048),
                            dict(row, context=8192, per_slot_context=4096, offloaded_layers=19),
                            dict(row, context=16384, per_slot_context=4096)]
            path.write_text(json.dumps(base))
            manifest = {"gpu": base["gpu"], "platform": base["platform"],
                        "settings": {"slots": 2}, "arms": [{"arm": "a", "name": "A"}]}
            self.assertEqual(load_fit(path, manifest)["vram_total_mib"], 6144)
            self.assertEqual([row["fully_offloaded"] for row in load_fit(path, manifest)["rows"]],
                             [True, False, False])

    def test_reject_duplicate_deployment(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = fixture(root / "one", "a")
            with self.assertRaisesRegex(ValueError, "duplicate deployments"):
                merge_runs([one, one], root / "merge")


if __name__ == "__main__":
    unittest.main()
