"""Fail-open: when something breaks, the report must say so, never look like a quiet month."""
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import helpers
from helpers import lw, llm_triage

ARGS = ["--config", helpers.OT_CONFIG, "--fixture", helpers.FIXTURE]


class AiLine(unittest.TestCase):
    def test_no_triage_requested(self):
        report, _ = helpers.run_main(ARGS)
        self.assertIn("未使用 AI 篩選", report)

    def test_triage_requested_but_no_keys(self):
        report, _ = helpers.run_main(ARGS + ["--triage"])
        self.assertIn("沒有找到任何金鑰", report)
        self.assertIn("共 9 篇候選待讀", report)         # everything still listed

    def test_every_provider_fails_is_flagged_and_nothing_is_dropped(self):
        with mock.patch.object(llm_triage, "triage", return_value=None), \
                mock.patch.object(lw.time, "sleep"):
            report, _ = helpers.run_main(ARGS + ["--triage"], env={"GROQ_API_KEY": "x"})
        self.assertIn("所有模型都失敗", report)
        self.assertNotIn("AI 篩掉", report)
        self.assertIn("共 9 篇候選待讀", report)

    def test_working_provider_names_the_model_and_collapses_drops(self):
        verdict = {"verdict": "drop", "reason": "無介入", "tier": "groq", "model": "test-model"}
        with mock.patch.object(llm_triage, "triage", return_value=verdict), \
                mock.patch.object(lw.time, "sleep"):
            report, _ = helpers.run_main(ARGS + ["--triage"], env={"GROQ_API_KEY": "x"})
        self.assertIn("groq/`test-model`", report)
        self.assertIn("保留 0 篇", report)
        self.assertIn("AI 篩掉", report)

    def test_nothing_new_to_score_is_not_called_a_failure(self):
        seen = os.path.join(tempfile.mkdtemp(), "seen.json")
        helpers.run_main(ARGS + ["--seen-file", seen])
        with mock.patch.object(lw.time, "sleep"):
            report, _ = helpers.run_main(ARGS + ["--triage", "--seen-file", seen], env={"GROQ_API_KEY": "x"})
        self.assertIn("沒有新論文需要判斷", report)
        self.assertNotIn("所有模型都失敗", report)

    def test_missing_rubric_is_disclosed(self):
        cfg = lw.load_config(helpers.OT_CONFIG)
        del cfg["rubric"]
        path = helpers.write_json(tempfile.mkdtemp(), "c.json", cfg)
        verdict = {"verdict": "keep", "reason": "", "tier": "groq", "model": "m"}
        with mock.patch.object(llm_triage, "triage", return_value=verdict), \
                mock.patch.object(lw.time, "sleep"):
            report, _ = helpers.run_main(["--config", path, "--fixture", helpers.FIXTURE, "--triage"],
                                         env={"GROQ_API_KEY": "x"})
        self.assertIn("沒有 `rubric`", report)


class FailedSearch(unittest.TestCase):
    def test_failed_topic_is_reported_as_unchecked_not_as_empty(self):
        err = urllib.error.URLError("no network")
        with mock.patch.object(lw, "epmc_search", side_effect=err):
            report, _ = helpers.run_main(["--config", helpers.OT_CONFIG])
        self.assertIn("【不完整】4 個主題裡有 4 個無法檢查", report)
        self.assertIn("【無法檢查】URLError", report)
        self.assertIn("檢查了 0 / 4", report)
        self.assertNotIn("沒有符合的論文", report)

    def test_failures_are_counted_for_the_workflow(self):
        out = os.path.join(tempfile.mkdtemp(), "gh_out.txt")
        err = urllib.error.URLError("no network")
        with mock.patch.object(lw, "epmc_search", side_effect=err):
            helpers.run_main(["--config", helpers.OT_CONFIG], env={"GITHUB_OUTPUT": out})
        with open(out, encoding="utf-8") as f:
            self.assertIn("n_failed=4", f.read())

    def test_unreadable_issue_history_is_flagged(self):
        env = {"GITHUB_REPOSITORY": "a/b", "GH_TOKEN": "x"}
        with mock.patch.object(lw.http_retry, "fetch", side_effect=ConnectionResetError("r")):
            report, _ = helpers.run_main(ARGS + ["--seen-from-issues", "literature-radar"], env=env)
        self.assertIn("讀不到舊的 Issue", report)


class Truncation(unittest.TestCase):
    def test_cap_is_stated_with_numbers(self):
        cfg = lw.load_config(helpers.OT_CONFIG)
        cfg["max_per_topic"] = 1
        path = helpers.write_json(tempfile.mkdtemp(), "c.json", cfg)
        report, _ = helpers.run_main(["--config", path, "--fixture", helpers.FIXTURE])
        self.assertIn("【上限】只掃描了最新 1 篇（共 2 篇）", report)


class HttpRetry(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = []

        class R:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b"ok"

        def opener(req, timeout):
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionResetError("x")
            return R()

        self.assertEqual(lw.http_retry.fetch("req", 1, sleep=lambda s: None, opener=opener), b"ok")
        self.assertEqual(len(calls), 3)

    def test_gives_up_after_three_attempts(self):
        def opener(req, timeout):
            raise ConnectionResetError("x")
        with self.assertRaises(ConnectionResetError):
            lw.http_retry.fetch("req", 1, sleep=lambda s: None, opener=opener)


class ModelChoice(unittest.TestCase):
    def test_picks_chat_model_by_pattern_and_skips_other_modalities(self):
        ids = ["whisper-large-v3", "groq/compound", "openai/gpt-oss-20b", "meta/some-new-model"]
        self.assertEqual(llm_triage.choose_model("groq", ids), ["openai/gpt-oss-20b"])

    def test_unknown_models_on_groq_are_not_guessed(self):
        self.assertEqual(llm_triage.choose_model("groq", ["brand-new-model"]), [])

    def test_verdict_parser_accepts_only_keep_or_drop(self):
        self.assertEqual(llm_triage._parse('{"verdict":"KEEP","reason":"ok"}'),
                         {"verdict": "keep", "reason": "ok"})
        self.assertIsNone(llm_triage._parse('{"verdict":"maybe"}'))
        self.assertIsNone(llm_triage._parse("not json"))
        self.assertIsNone(llm_triage._parse(None))


if __name__ == "__main__":
    unittest.main()
