"""Tests for check_doi.py using fake records only (no network). Run from 03_sources:
python -m unittest discover -s tests"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check_doi as cd  # noqa: E402

with open(os.path.join(HERE, "fake_crossref.json"), encoding="utf-8") as f:
    FAKE = json.load(f)


def fetch(doi):
    return FAKE.get(doi)


def rows():
    return {r["doi"]: r for r in cd.read_input(os.path.join(HERE, "fake_dois.csv"))}


class CheckDoiTests(unittest.TestCase):
    def test_match(self):
        r = cd.check_one(rows()["10.9999/fake.001"], fetch)
        self.assertEqual(r["判定"], "一致")

    def test_retraction_blocks(self):
        r = cd.check_one(rows()["10.9999/fake.002"], fetch)
        self.assertEqual(r["判定"], "衝突")
        self.assertIn("retraction", r["更新紀錄"])

    def test_correction_needs_look(self):
        r = cd.check_one(rows()["10.9999/fake.003"], fetch)
        self.assertEqual(r["判定"], "待查")

    def test_wrong_paper(self):
        r = cd.check_one(rows()["10.9999/fake.004"], fetch)
        self.assertEqual(r["判定"], "衝突")

    def test_unknown_doi(self):
        r = cd.check_one(rows()["10.9999/fake.999"], fetch)
        self.assertEqual(r["判定"], "衝突")

    def test_missing_doi_is_undecidable(self):
        r = cd.check_one(rows()["待補"], fetch)
        self.assertEqual(r["判定"], "無法判定")

    def test_network_failure_is_undecidable_not_conflict(self):
        def broken(doi):
            raise OSError("timeout")
        r = cd.check_one({"doi": "10.9999/fake.001"}, broken)
        self.assertEqual(r["判定"], "無法判定")

    def test_year_off_by_one_is_check(self):
        row = dict(rows()["10.9999/fake.001"], year="2023")
        self.assertEqual(cd.check_one(row, fetch)["判定"], "待查")

    def test_placeholder_expectation_is_ignored(self):
        row = {"doi": "10.9999/fake.001", "title": "待補", "journal": "待補", "year": "待補"}
        self.assertEqual(cd.check_one(row, fetch)["判定"], "一致")

    def test_chinese_headers_are_accepted(self):
        got = cd.read_input(os.path.join(HERE, "papers_fake_aliases.csv"))
        self.assertEqual(cd.check_one(got[0], fetch)["判定"], "一致")

class JournalNameTest(unittest.TestCase):
    """Abbreviated journal names must not turn a matching paper into a conflict."""

    REC = {"title": ["Effects of home rehab"], "container-title": ["Journal of NeuroEngineering and Rehabilitation"],
           "short-container-title": ["J NeuroEngineering Rehabil"], "issued": {"date-parts": [[2025]]}}

    def grade(self, **row):
        return cd.check_one({"doi": "10.1/x", "year": "2025", **row}, fetch=lambda d: self.REC)

    def test_abbreviation_with_matching_title_is_not_conflict(self):
        r = self.grade(title="Effects of home rehab", journal="J Neuroeng Rehabil")
        self.assertEqual(r["判定"], "待查")

    def test_full_name_matches(self):
        r = self.grade(title="Effects of home rehab", journal="Journal of neuroengineering and rehabilitation")
        self.assertEqual(r["判定"], "一致")

    def test_wrong_journal_without_title_is_conflict(self):
        self.assertEqual(self.grade(journal="Cancer Cell")["判定"], "衝突")

    def test_wrong_title_is_still_conflict(self):
        r = self.grade(title="Completely unrelated paper about astronomy", journal="J Neuroeng Rehabil")
        self.assertEqual(r["判定"], "衝突")

if __name__ == "__main__":
    unittest.main()
