"""Tests for check_file.py using fake page-1 text files only (no network, no real papers).
Run from 03_sources: python -m unittest discover -s tests"""
import csv
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check_file as cf  # noqa: E402

FILES = os.path.join(HERE, "fake_files")


def rows():
    return {r["pmid"]: r for r in cf.read_rows(os.path.join(HERE, "fake_papers.csv"))}


def read_text(name):
    with open(os.path.join(FILES, name), encoding="utf-8") as f:
        return f.read()


def write_fake_pdf(folder):
    with open(os.path.join(folder, "PMID_1.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 fake")


def run(pmid):
    return cf.check_one(rows()[pmid], FILES)


class CheckFileTests(unittest.TestCase):
    def test_match(self):
        self.assertEqual(run("1")["判定"], "一致")

    def test_wrong_paper_is_conflict(self):
        # The case that bit the original project: the file is a different (cited) paper.
        r = run("2")
        self.assertEqual(r["判定"], "衝突")
        self.assertIn("10.8888/other.777", r["第一頁找到的DOI"])

    def test_retraction_banner_blocks(self):
        self.assertEqual(run("3")["判定"], "衝突")

    def test_correction_needs_look(self):
        self.assertEqual(run("4")["判定"], "待查")

    def test_missing_file_is_not_ok(self):
        self.assertEqual(run("5")["判定"], "無法判定")

    def test_no_text_is_not_ok(self):
        self.assertEqual(run("6")["判定"], "無法判定")

    def test_one_page_pdf_needs_look(self):
        row = rows()["1"]
        text = read_text("PMID_1.txt")
        self.assertEqual(cf.check_text(row, text, pages=1)[0], "待查")

    def test_pdf_without_pypdf_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            write_fake_pdf(d)
            original = cf.read_pdf

            def no_pypdf(path):
                raise ImportError("pypdf")
            cf.read_pdf = no_pypdf
            try:
                r = cf.check_one(rows()["1"], d)
            finally:
                cf.read_pdf = original
        self.assertEqual(r["判定"], "無法判定")
        self.assertIn("pypdf", r["原因"])

    def test_merge_keeps_worse_level(self):
        results = [run("1")]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "doi.csv")
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["doi", "判定", "原因"])
                w.writeheader()
                w.writerow({"doi": "10.9999/fake.001", "判定": "衝突", "原因": "Crossref 有撤稿紀錄"})
            cf.merge_doi_result(results, p)
        self.assertEqual(results[0]["判定"], "衝突")

    def test_merge_missing_row_is_not_ok(self):
        results = [run("1")]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "doi.csv")
            with open(p, "w", encoding="utf-8-sig", newline="") as f:
                csv.DictWriter(f, fieldnames=["doi", "判定", "原因"]).writeheader()
            cf.merge_doi_result(results, p)
        self.assertEqual(results[0]["判定"], "無法判定")

    # Cases found in review: each one used to come out as 一致.
    GOOD = "Task-oriented training after stroke: a fictional trial"

    def judge(self, text, doi="10.9999/fake.001", title=GOOD, pages=None):
        return cf.check_text({"doi": doi, "title": title}, text, pages)[0]

    def test_retracted_banner_variants_block(self):
        for banner in ["RETRACTED: " + self.GOOD, "WITHDRAWN\n" + self.GOOD, "Retracted\n" + self.GOOD]:
            self.assertEqual(self.judge(banner + "\nhttps://doi.org/10.9999/fake.001"), "衝突", banner)

    def test_ordinary_retraction_word_is_not_blocked(self):
        text = self.GOOD + " with scapular retraction exercises\nhttps://doi.org/10.9999/fake.001"
        self.assertEqual(self.judge(text), "一致")

    def test_springer_retraction_note_blocks(self):
        text = ("Retraction Note to: " + self.GOOD + "\nhttps://doi.org/10.9999/fake.001\n"
                "The Editor has retracted this article because of concerns about the data.")
        self.assertEqual(self.judge(text), "衝突")

    def test_ordinary_words_are_not_conflict(self):
        # PDF line breaks, CONSORT flow charts and rehab titles must not be called 衝突.
        cases = [
            self.GOOD + "\nthe shoulder was\nretracted and held for 5 s; two participants were\n"
                        "withdrawn because of pain.\nhttps://doi.org/10.9999/fake.001",
            self.GOOD + "\nAllocated (n=20)  3 WITHDRAWN\nhttps://doi.org/10.9999/fake.001",
        ]
        for text in cases:
            self.assertEqual(self.judge(text), "待查", text[-60:])
        title = "Scapular retraction: a fictional randomized trial in stroke"
        text = title + "\nhttps://doi.org/10.9999/fake.001"
        self.assertEqual(self.judge(text, title=title), "一致")

    def test_no_list_doi_is_never_ok(self):
        text = "stroke after training: a trial fictional task-oriented\nhttps://doi.org/10.7777/other.1"
        self.assertNotEqual(self.judge(text, doi=""), "一致")
        self.assertNotEqual(self.judge(self.GOOD, doi="待補"), "一致")

    def test_other_dois_next_to_ours_need_look(self):
        # e.g. a whole paper whose reference list cites our paper
        text = "Some other paper\nhttps://doi.org/10.5555/x.1\nReferences\n1. " + self.GOOD + ". doi:10.9999/fake.001"
        self.assertEqual(self.judge(text), "待查")

    def test_doi_cleaning(self):
        self.assertEqual(cf.clean_doi("doi:10.9999/fake.015)"), "10.9999/fake.015")
        self.assertEqual(cf.clean_doi("https://doi.org/10.9999/FAKE.001."), "10.9999/fake.001")
        self.assertEqual(cf.clean_doi("10.1016/S0140-6736(20)30367-6"), "10.1016/s0140-6736(20)30367-6")
        text = self.GOOD + " (doi:10.9999/fake.001)"
        self.assertEqual(self.judge(text), "一致")

    def test_pdf_without_pypdf_falls_back_to_txt(self):
        with tempfile.TemporaryDirectory() as d:
            write_fake_pdf(d)
            with open(os.path.join(d, "PMID_1.txt"), "w", encoding="utf-8") as f:
                f.write(read_text("PMID_1.txt"))
            original = cf.read_pdf

            def no_pypdf(path):
                raise ImportError("pypdf")
            cf.read_pdf = no_pypdf
            try:
                r = cf.check_one(rows()["1"], d)
            finally:
                cf.read_pdf = original
        self.assertEqual((r["判定"], r["檔案"]), ("一致", "PMID_1.txt"))

    def test_merge_rejects_wrong_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.csv")
            with open(p, "w", encoding="utf-8") as f:
                f.write("DOI,verdict\n10.9999/fake.001,ok\n")
            with self.assertRaises(SystemExit):
                cf.merge_doi_result([run("1")], p)

    def test_worse(self):
        self.assertEqual(cf.worse("一致", "無法判定"), "無法判定")
        self.assertEqual(cf.worse("待查", "無法判定"), "待查")
        self.assertEqual(cf.worse("衝突", "一致"), "衝突")


if __name__ == "__main__":
    unittest.main()
