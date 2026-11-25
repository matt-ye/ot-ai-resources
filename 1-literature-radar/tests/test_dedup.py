"""De-duplication: the same paper must be listed once, this month and across months."""
import os
import tempfile
import unittest
from unittest import mock

import helpers
from helpers import lw

DOI_REC = {"doi": "10.1000/ABC.123", "title": "A trial.", "firstPublicationDate": "2026-10-01",
           "journalTitle": "J Rehab"}
EPMC_REC = {"source": "PPR", "id": "PPR999", "title": "A preprint", "firstPublicationDate": "2026-10-02"}
# One article as Europe PMC can return it twice: a MEDLINE record with a DOI, and a
# PMC record without, with curly instead of straight quotes.
MED_REC = {"doi": "10.1111/hex.70918", "title": "'Some of Them Were Created by People': Stroke Study"}
PMC_REC = {"source": "PMC", "id": "PMC13648021",
           "title": "‘Some of Them Were Created by People’: Stroke Study"}


class PaperKeys(unittest.TestCase):
    def test_doi_key_is_case_insensitive(self):
        self.assertEqual(lw.paper_keys(DOI_REC), lw.paper_keys({**DOI_REC, "doi": "10.1000/abc.123"}))

    def test_med_and_pmc_records_of_one_paper_share_a_key(self):
        self.assertTrue(lw.paper_keys(MED_REC) & lw.paper_keys(PMC_REC))

    def test_different_papers_share_no_key(self):
        self.assertFalse(lw.paper_keys(DOI_REC) & lw.paper_keys(EPMC_REC))


class ReadBack(unittest.TestCase):
    """What a report prints must read back to the same keys: the cross-month
    de-duplication depends on this round trip."""

    def test_report_lines_round_trip_to_keys(self):
        body = "\n".join([lw.line_for(DOI_REC), lw.line_for(EPMC_REC, {"reason": "RCT"})])
        self.assertEqual(lw.keys_in_text(body), lw.paper_keys(DOI_REC) | lw.paper_keys(EPMC_REC))

    def test_text_without_links_yields_nothing(self):
        self.assertEqual(lw.keys_in_text("- 最近 45 天沒有符合的論文"), set())


class SeenFromIssues(unittest.TestCase):
    def test_missing_env_fails_open_with_reason(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            for k in ("GITHUB_REPOSITORY", "GH_TOKEN", "GITHUB_TOKEN"):
                os.environ.pop(k, None)
            keys, err = lw.seen_from_issues("literature-radar")
        self.assertEqual(keys, set())
        self.assertTrue(err)

    def test_dropped_connection_fails_open_with_reason(self):
        env = {"GITHUB_REPOSITORY": "a/b", "GH_TOKEN": "x"}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(lw.http_retry, "fetch", side_effect=ConnectionResetError("reset")):
            keys, err = lw.seen_from_issues("literature-radar")
        self.assertEqual((keys, err), (set(), "ConnectionResetError"))


class WholeRun(unittest.TestCase):
    def test_duplicate_pair_is_listed_once_and_counted(self):
        report, _ = helpers.run_main(["--config", helpers.OT_CONFIG, "--fixture", helpers.FIXTURE])
        self.assertEqual(report.count("Never Had a Stroke"), 1)
        self.assertIn("1 篇是重複紀錄", report)

    def test_seen_file_hides_old_papers_and_says_so(self):
        d = tempfile.mkdtemp()
        seen = os.path.join(d, "seen.json")
        args = ["--config", helpers.OT_CONFIG, "--fixture", helpers.FIXTURE, "--seen-file", seen]
        first, _ = helpers.run_main(args)
        self.assertIn("共 9 篇候選待讀", first)
        second, _ = helpers.run_main(args)
        self.assertIn("共 0 篇候選待讀", second)
        self.assertIn("沒有新的", second)
        self.assertIn("在更早的報告列過", second)


if __name__ == "__main__":
    unittest.main()
