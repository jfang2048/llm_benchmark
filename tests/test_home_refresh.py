import json
import unittest

from bench import config, fresh, fresh_report, home_report


class RefreshTests(unittest.TestCase):
    def test_blob_sources_are_content_addressed(self):
        with_blob = [model for model in config.models() if model.get("gguf_blob_url")]
        self.assertTrue(with_blob)
        for model in with_blob:
            self.assertTrue(model["gguf_blob_url"].endswith("/blobs/sha256:" + model["sha256"]))
            self.assertGreater(model["gguf_bytes"], 0)

    def test_extension_retains_original_scores_and_tracks_bridge(self):
        base = home_report.read_run(fresh.PUBLISHED)[0]
        extension = fresh_report.EXTENSION
        later, rows, _ = home_report.read_run(extension)
        outcome = fresh_report.summarize(fresh.PUBLISHED, extension)
        overlap = {item["arm"] for item in base["arms"]} & {item["arm"] for item in later["arms"]}
        self.assertEqual(overlap, {fresh_report.ANCHOR})
        self.assertEqual(len(outcome["models"]), len(base["arms"]) + len(later["arms"]) - 1)
        self.assertEqual(outcome["extension"]["n_requests"], sum(map(len, rows.values())))
        self.assertEqual(outcome["extension"]["anchor"]["arm"], fresh_report.ANCHOR)
        self.assertTrue(all(isinstance(arm["startup_ms"], (float, int)) for arm in later["arms"]))

    def test_scored_candidates_passed_admission(self):
        path = fresh_report.EXTENSION
        admissions = json.loads((path / "admission.json").read_text())
        admitted = {row["arm"]: row for row in admissions if row["status"] == "admitted"}
        tested = {arm["arm"]: arm for arm in home_report.read_run(path)[0]["arms"]
                  if arm["arm"] != fresh_report.ANCHOR}
        self.assertEqual(set(admitted), set(tested))
        for name, arm in tested.items():
            self.assertEqual(admitted[name]["sha256"], arm["gguf_sha256"])
            self.assertEqual(admitted[name]["image_id"], arm["image_id"])


if __name__ == "__main__":
    unittest.main()
