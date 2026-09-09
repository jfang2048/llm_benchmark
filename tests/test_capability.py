#!/usr/bin/env python3
"""Lightweight capability-layer unit tests (stdlib unittest only).

Validates the correctness-critical pieces that do NOT need a GPU or a Docker
environment: Wilson intervals, TSV merge/upsert, multi-run manifest, run
fingerprint, and the SWE-bench report parser / failure taxonomy.

Run: python3 tests/test_capability.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import normalize  # noqa: E402
import swe  # noqa: E402


class TestWilson(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(normalize.wilson(0, 0), (0.0, 0.0))

    def test_full_success_small_n(self):
        lo, hi = normalize.wilson(5, 5)
        self.assertLess(lo, 1.0)  # Wilson never returns exactly 100% at small n
        self.assertAlmostEqual(hi, 1.0, places=6)

    def test_half(self):
        lo, hi = normalize.wilson(10, 5)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)

    def test_never_reports_100_without_n(self):
        # pct with n=0 must be None, not 100
        self.assertIsNone(normalize.pct(0, 0))


class TestFingerprint(unittest.TestCase):
    def test_deterministic(self):
        a = normalize.run_fingerprint({"a": 1, "b": [2, 3]})
        b = normalize.run_fingerprint({"b": [2, 3], "a": 1})
        self.assertEqual(a, b)  # order-independent
        self.assertEqual(len(a), 16)

    def test_differs(self):
        a = normalize.run_fingerprint({"model": "qwen3_8b"})
        b = normalize.run_fingerprint({"model": "glm4_9b"})
        self.assertNotEqual(a, b)


class TestMergeUpsert(unittest.TestCase):
    def test_summary_keeps_both_datasets(self):
        with tempfile.TemporaryDirectory() as td:
            # monkeypatch CAP_RESULTS to the temp dir
            normalize.CAP_RESULTS = Path(td)
            normalize.write_summary("evalplus",
                                    [{"model": "m", "dataset": "humaneval", "v": 1}],
                                    ["model", "dataset", "v"],
                                    key_cols=["model", "dataset"])
            normalize.write_summary("evalplus",
                                    [{"model": "m", "dataset": "mbpp", "v": 2}],
                                    ["model", "dataset", "v"],
                                    key_cols=["model", "dataset"])
            rows = normalize._read_tsv(Path(td) / "evalplus" / "summary.tsv")
            self.assertEqual(len(rows), 2)  # humaneval AND mbpp preserved


class TestManifest(unittest.TestCase):
    def test_multi_run_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            normalize.CAP_RESULTS = Path(td)
            m1 = normalize.make_manifest("swe_verified", "qwen3_8b", kind="agent",
                                         extra={"subset": "Local-20"})
            m2 = normalize.make_manifest("swe_verified", "glm4_9b", kind="agent",
                                         extra={"subset": "Local-20"})
            normalize.write_manifest("swe-verified", m1)
            normalize.write_manifest("swe-verified", m2)
            data = json.loads((Path(td) / "swe-verified" / "manifest.json").read_text())
            self.assertEqual(len(data["runs"]), 2)
            models = {r["model"] for r in data["runs"]}
            self.assertEqual(models, {"qwen3_8b", "glm4_9b"})
            self.assertIn("run_fingerprint", data["runs"][0])

    def test_kind_differs(self):
        d = normalize.make_manifest("evalplus", "qwen3_8b", kind="direct")
        a = normalize.make_manifest("swe_verified", "qwen3_8b", kind="agent")
        self.assertEqual(d["agent"], "none")
        self.assertEqual(d["serving_profile"], "direct_coding_profile")
        self.assertEqual(a["serving_profile"], "agent_profile")
        self.assertIn("agent_commit", a)


class TestSweReportParser(unittest.TestCase):
    def test_resolved(self):
        r = {"resolved": True, "patch_exists": True,
             "patch_successfully_applied": True}
        self.assertEqual(swe.classify_report(r), "RESOLVED")

    def test_no_patch(self):
        r = {"resolved": False, "patch_is_None": True, "patch_exists": False}
        self.assertEqual(swe.classify_report(r), "NO_PATCH")

    def test_patch_invalid(self):
        r = {"resolved": False, "patch_exists": True,
             "patch_successfully_applied": False}
        self.assertEqual(swe.classify_report(r), "PATCH_INVALID")

    def test_test_failure(self):
        r = {"resolved": False, "patch_exists": True,
             "patch_successfully_applied": True}
        self.assertEqual(swe.classify_report(r), "TEST_FAILURE")

    def test_infra_failure_not_test_failure(self):
        r = {"resolved": False, "patch_exists": True,
             "patch_successfully_applied": True, "infra_failure": True}
        self.assertEqual(swe.classify_report(r), "ENVIRONMENT_ERROR")

    def test_missing_report(self):
        self.assertEqual(swe.classify_report({}), "MISSING_REPORT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
