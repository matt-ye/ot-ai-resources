"""Tests for compare_extractions.py. Run: python -m unittest discover -s tests (from 05_verify)."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import compare_extractions as ce  # noqa: E402

CSV = os.path.join(HERE, "..", "..", "04_extract", "examples", "numbers_long.csv")


class RuleTests(unittest.TestCase):
    def test_same_number_different_format(self):
        self.assertTrue(ce.values_agree("12.30", "12.3"))
        self.assertTrue(ce.values_agree("12.3 (4.1)", "12.3"))

    def test_one_unclear_is_disagreement(self):
        self.assertFalse(ce.values_agree("23", "Unclear"))
        self.assertEqual(ce.judge("23", "Unclear", False), "disagree")

    def test_both_unclear(self):
        self.assertEqual(ce.judge("Unclear", "", False), "both-unclear")

    def test_text_field_is_case_insensitive_but_exact(self):
        self.assertEqual(ce.judge("SD", "sd", True), "agree")
        self.assertEqual(ce.judge("SD", "SE", True), "disagree")

    def test_no_tolerance(self):
        self.assertFalse(ce.values_agree("12.3", "12.4"))


class ReproductionTests(unittest.TestCase):
    def test_csv_reproduces_110_82_8_20(self):
        a, b = ce.load_csv(CSV, "模型A"), ce.load_csv(CSV, "模型B")
        s = ce.summarize(ce.compare(a, b))
        self.assertEqual((s["total"], s["agree"], s["disagree"], s["both-unclear"]), (110, 82, 8, 20))
        self.assertEqual(s["denominator"], 90)
        self.assertEqual(round(s["rate"] * 100), 91)


class JsonWithoutQuotesTests(unittest.TestCase):
    def _write(self, folder, pmid, mean):
        doc = {"pmid": pmid, "arms": [{"arm_name": "X", "fma_ue_post": {"mean": mean, "dispersion": "1.0",
                                                                        "dispersion_type": "SD"}}]}
        with open(os.path.join(folder, pmid + ".json"), "w", encoding="utf-8") as f:
            json.dump(doc, f)

    def test_json_without_quote_or_location_keys(self):
        with tempfile.TemporaryDirectory() as ta, tempfile.TemporaryDirectory() as tb:
            self._write(ta, "1", "10")
            self._write(tb, "1", "11")
            cells = ce.compare(ce.load_json_dir(ta), ce.load_json_dir(tb))
            post_mean = [c for c in cells if c["label"] == "後測 mean"][0]
            self.assertEqual(post_mean["verdict"], "disagree")
            s = ce.summarize(cells)
            self.assertEqual(s["total"], 11)

    def test_arm_count_mismatch_counts_as_disagree(self):
        a = {"1": {1: {"name": "a", "cells": {("n_randomized", "value"): ("10", "")}}}}
        b = {"1": {}}
        cells = ce.compare(a, b)
        n_cell = [c for c in cells if c["label"] == "隨機分派 N"][0]
        self.assertEqual(n_cell["verdict"], "disagree")


if __name__ == "__main__":
    unittest.main()
