"""Tests for validate_extraction.py. Run: python -m unittest discover -s tests (from 04_extract)."""
import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import validate_extraction as ve  # noqa: E402

with open(os.path.join(HERE, "..", "extraction_schema.json"), encoding="utf-8") as f:
    SCHEMA = json.load(f)


def count(v="10"):
    return {"value": v, "quote": "", "location": ""}


def score(m="1", d="2", t="SD"):
    return {"mean": m, "dispersion": d, "dispersion_type": t, "quote": "", "location": ""}


GOOD = {"pmid": "123", "design": "parallel", "notes": "",
        "arms": [{"arm_name": "A", "intervention_summary": "x", "n_randomized": count(),
                  "n_analyzed": count("Unclear"), "fma_ue_pre": score(), "fma_ue_post": score(),
                  "fma_ue_change": score("Unclear", "Unclear", "Unclear"), "timepoint": "week 4"}]}


class ValidateTests(unittest.TestCase):
    def test_good_document(self):
        self.assertEqual(ve.validate(GOOD, SCHEMA, SCHEMA), [])

    def test_missing_field(self):
        bad = copy.deepcopy(GOOD)
        del bad["arms"][0]["fma_ue_pre"]
        self.assertTrue(any("fma_ue_pre" in e for e in ve.validate(bad, SCHEMA, SCHEMA)))

    def test_bad_dispersion_type(self):
        bad = copy.deepcopy(GOOD)
        bad["arms"][0]["fma_ue_post"]["dispersion_type"] = "standard error"
        self.assertTrue(ve.validate(bad, SCHEMA, SCHEMA))

    def test_number_instead_of_string(self):
        bad = copy.deepcopy(GOOD)
        bad["arms"][0]["n_randomized"]["value"] = 10
        self.assertTrue(ve.validate(bad, SCHEMA, SCHEMA))

    def test_empty_arms(self):
        bad = copy.deepcopy(GOOD)
        bad["arms"] = []
        self.assertTrue(ve.validate(bad, SCHEMA, SCHEMA))


if __name__ == "__main__":
    unittest.main()
