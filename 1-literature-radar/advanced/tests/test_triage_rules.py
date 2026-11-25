"""Offline checks for the ledger rules in advanced/ (no network, no AI).

Run from the repository root:  python -m unittest discover -s advanced/tests
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ADV = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(ADV, ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, ADV)
import triage_rules as tr  # noqa: E402
import facts  # noqa: E402
import literature_watch as lw  # noqa: E402
import literature_watch_ledger as lwl  # noqa: E402

LEDGER = tr.load_ledger(os.path.join(ADV, "ledger.dementia-example.json"))
TODAY = __import__("datetime").date(2026, 11, 25)


def f(**kw):
    base = {"estimate": True, "layer": "prevalence", "measure": "prevalence", "population": "general",
            "method": "survey", "representative": True, "countries": ["KR"], "data_end_year": 2023,
            "dataset": "Some new survey"}
    base.update(kw)
    return base


class EndYear(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(tr.end_year("2015-18", TODAY), 2018)
        self.assertEqual(tr.end_year("2019-2023", TODAY), 2023)
        self.assertEqual(tr.end_year("2022", TODAY), 2022)
        self.assertEqual(tr.end_year("2030-2050", TODAY), 2030)   # a projection stops at its start
        self.assertIsNone(tr.end_year("n/a", TODAY))


class Decide(unittest.TestCase):
    def test_newer_data_than_country_override_is_update(self):
        self.assertEqual(tr.decide(f(data_end_year=2023), LEDGER)[0], tr.UPDATE)

    def test_older_data_is_older(self):
        self.assertEqual(tr.decide(f(data_end_year=2015), LEDGER)[0], tr.OLDER)

    def test_same_dataset_is_older_even_without_year(self):
        r = tr.decide(f(countries=["GLOBAL"], dataset="GBD 2021", data_end_year=None), LEDGER)
        self.assertEqual(r[0], tr.OLDER)

    def test_subgroup_and_local_sample_and_wrong_measure_are_not_estimates(self):
        self.assertEqual(tr.decide(f(population="subgroup"), LEDGER)[0], tr.NOT_ESTIMATE)
        self.assertEqual(tr.decide(f(representative=False), LEDGER)[0], tr.NOT_ESTIMATE)
        self.assertEqual(tr.decide(f(measure="relative_risk"), LEDGER)[0], tr.NOT_ESTIMATE)
        self.assertEqual(tr.decide(f(estimate=False), LEDGER)[0], tr.NOT_ESTIMATE)
        self.assertEqual(tr.decide(f(layer="none"), LEDGER)[0], tr.NOT_ESTIMATE)

    def test_layer_rules_from_the_ledger(self):
        self.assertEqual(tr.decide(f(layer="mci", method="administrative"), LEDGER)[0], tr.NOT_ESTIMATE)
        single = f(layer="risk_ratio", measure="relative_risk", method="survey", representative=False)
        self.assertEqual(tr.decide(single, LEDGER)[0], tr.NOT_ESTIMATE)
        pooled = f(layer="risk_ratio", measure="relative_risk", method="meta_analysis",
                   representative=False, countries=["GLOBAL"], data_end_year=2025)
        self.assertEqual(tr.decide(pooled, LEDGER)[0], tr.UPDATE)

    def test_country_missing_from_ledger_uses_global_default(self):
        r = tr.decide(f(countries=["JP"], data_end_year=2015), LEDGER)
        self.assertEqual(r[0], tr.OLDER)
        self.assertIn("GBD 2021", r[1])


class FactsParsing(unittest.TestCase):
    def test_rubric_lists_the_ledger_layers(self):
        rubric = facts.build_rubric(LEDGER)
        for key in LEDGER["layers"]:
            self.assertIn(key, rubric)

    def test_parse_normalises_and_rejects(self):
        o = facts.parse_facts('{"estimate":"true","layer":"MCI","countries":"KR"}')
        self.assertEqual((o["estimate"], o["layer"], o["countries"]), (True, "mci", []))
        self.assertIsNone(facts.parse_facts("no json"))
        self.assertIsNone(facts.parse_facts('{"layer":"mci"}'))


class WholeRun(unittest.TestCase):
    def test_run_with_fake_facts_keeps_update_and_collapses_older(self):
        fx = {"*": {"hitCount": 2, "resultList": {"result": [
            {"title": "New national estimate", "doi": "10.1/a", "firstPublicationDate": "2026-10-01"},
            {"title": "Old data estimate", "doi": "10.1/b", "firstPublicationDate": "2026-10-02"}]}}}
        d = tempfile.mkdtemp()
        fxp = os.path.join(d, "fx.json")
        import json
        with open(fxp, "w", encoding="utf-8") as fh:
            json.dump(fx, fh)

        def fake_triage(title, text, env=None, system=None, parse=None, heavy=False):
            year = 2023 if title.startswith("New") else 2010
            return {**f(data_end_year=year), "tier": "groq", "model": "test-model"}

        env = {k: v for k, v in os.environ.items()}
        env["GROQ_API_KEY"] = "x"
        out = os.path.join(d, "r.md")
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(facts.llm_triage, "triage", side_effect=fake_triage), \
                mock.patch.object(lw.time, "sleep"):
            report = lwl.main(["--config", os.path.join(ADV, "config.dementia-example.json"),
                               "--fixture", fxp, "--triage", "--out", out,
                               "--env-file", os.path.join(d, "none.env")])
        self.assertIn("New national estimate", report)
        self.assertIn("data 2023 > KR in use", report)
        self.assertIn("data 2010 <= KR in use", report)
        self.assertIn("groq/`test-model`", report)

    def test_unreadable_ledger_falls_back_and_says_so(self):
        d = tempfile.mkdtemp()
        cfg = {"ledger": "missing.json", "topics": [{"id": "t", "label": "T", "query": "TITLE:x"}]}
        import json
        cp = os.path.join(d, "c.json")
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        fxp = os.path.join(d, "fx.json")
        with open(fxp, "w", encoding="utf-8") as fh:
            json.dump({}, fh)
        report = lwl.main(["--config", cp, "--fixture", fxp, "--out", os.path.join(d, "r.md"),
                           "--env-file", os.path.join(d, "none.env")])
        self.assertIn("帳本讀不了", report)


if __name__ == "__main__":
    unittest.main()
