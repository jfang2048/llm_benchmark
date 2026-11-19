import csv
import json
import random
import unittest
from collections import Counter

from bench import config, fresh, fresh_report, home
from bench.home_report import read_run


class FreshCorpusTests(unittest.TestCase):
    def setUp(self):
        self.rows = [json.loads(line) for line in fresh.TASKS.read_text().splitlines()]

    def test_corpus_is_frozen_and_balanced(self):
        provenance = json.loads(fresh.SOURCES.read_text())
        self.assertEqual(provenance["task_sha256"], home.sha(fresh.TASKS))
        self.assertEqual(len({row["id"] for row in self.rows}), 192)
        self.assertEqual(len({row["prompt"] for row in self.rows}), 192)
        external = [row for row in self.rows if row["source"] == "llmstructbench2"]
        self.assertEqual(len({row["object_id"] for row in external}), 96)
        external_strata = Counter((row["stratum"], row["length_tier"], row["formatting"]) for row in external)
        self.assertEqual(Counter(external_strata.values()), {3: 32})
        local = [row for row in self.rows if row["source"] == "home_holdout"]
        self.assertEqual(Counter(Counter((row["stratum"], row["template"]) for row in local).values()), {4: 24})

    def test_masks_replace_the_intended_literals(self):
        rows = [row for row in self.rows if row["source"] == "home_holdout" and row["kind"] == "redact"]
        self.assertEqual(len(rows), 32)
        for row in rows:
            original = row["prompt"].split("\n", 1)[1]
            for literal in row["sensitive"]:
                self.assertIn(literal, original)
                original = original.replace(literal, "[MASK]")
            self.assertEqual(row["expected"]["text"], original)

    def test_weight_date_evidence_covers_the_registered_arms(self):
        settings = json.loads(fresh.SETTINGS.read_text())
        weights = {m["arm"]: m["sha256"] for cohort in settings["cohorts"]
                   for m in config.models_for_cohort(cohort)}
        ledger = fresh.ROOT / "configs/fresh_weight_dates.tsv"
        release = json.loads(fresh.SOURCES.read_text())["published_utc"]
        with ledger.open() as stream:
            dates = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual({row["arm"]: row["gguf_sha256"] for row in dates}, weights)
        self.assertTrue(all(row["observed_by_utc"][:10] < release and row["evidence"].startswith("https://")
                            for row in dates))

    def test_paired_bootstrap_preserves_stratum_sizes_and_sign(self):
        result = fresh_report.bootstrap([[1, 1], [-1]], 100, 17, 0.95)
        self.assertEqual(result, {"delta_pp": 100 / 3, "n": 3, "lo_pp": 100 / 3,
                                  "hi_pp": 100 / 3, "discordant": 3})

    def test_published_context_audit(self):
        records = json.loads((fresh.PUBLISHED / "audit.json").read_text())
        self.assertEqual(len(records), 13)
        self.assertTrue(all(row["cache_disabled_log"] and row["nonzero_initial_prefixes"] == 0
                            for row in records))
        failed = {row["arm"]: row["prompt_context_rejections"] for row in records
                  if row["prompt_context_rejections"]}
        self.assertEqual(failed, {"yi_15_9b": [{"input_tokens": 2096, "slot_tokens": 2048}]})
        self.assertEqual(sum(row["prefill_log_requests"] for row in records), 2496 + 26 - 1)

    def test_published_matrix(self):
        manifest, rows, cases = read_run(fresh.PUBLISHED)
        self.assertEqual(len(cases), 192)
        self.assertEqual(len(manifest["arms"]), 13)
        self.assertEqual(sum(map(len, rows.values())), 2496)
        self.assertEqual(manifest["tasks_sha256"], home.sha(fresh.TASKS))
        self.assertEqual(manifest["order"], [arm["arm"] for arm in manifest["arms"]])
        seed = manifest["settings"]["order_seed"]
        ordering = random.Random(seed + 1).sample([task["id"] for task in self.rows], len(self.rows))
        self.assertTrue(all([row["task"] for row in cell] == ordering for cell in rows.values()))


if __name__ == "__main__":
    unittest.main()
