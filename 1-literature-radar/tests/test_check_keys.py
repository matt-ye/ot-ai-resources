"""check_keys.py: each provider is tested on its own, and no key ever reaches the output.
Offline: provider calls are replaced by fakes; fake keys only."""
import contextlib
import io
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

import helpers  # noqa: F401  (puts scripts/ on sys.path)
import check_keys as ck

FAKE_KEY = "gsk_fake_1234567890"
FAKE_ACCT = "acct_fake_abcdef"


def ok(model):
    return lambda title, abstract, env: {"verdict": "keep", "reason": "測試", "model": model}


def boom(message):
    def fn(title, abstract, env):
        raise urllib.error.URLError(message)
    return fn


class CheckOne(unittest.TestCase):
    def test_not_set(self):
        r = ck.check_one("Groq", ok("m"), ("GROQ_API_KEY",), {})
        self.assertEqual(r["status"], "沒設定")

    def test_half_set_is_a_failure(self):
        r = ck.check_one("Cloudflare", ok("m"), ("CF_ACCOUNT_ID", "CF_API_TOKEN"), {"CF_ACCOUNT_ID": FAKE_ACCT})
        self.assertEqual(r["status"], "失敗")
        self.assertIn("CF_API_TOKEN", r["detail"])

    def test_works_and_names_the_model(self):
        r = ck.check_one("Groq", ok("openai/gpt-oss-20b"), ("GROQ_API_KEY",), {"GROQ_API_KEY": FAKE_KEY})
        self.assertEqual((r["status"], r["model"]), ("能用", "openai/gpt-oss-20b"))

    def test_failure_message_never_shows_secrets(self):
        env = {"CF_ACCOUNT_ID": FAKE_ACCT, "CF_API_TOKEN": FAKE_KEY}
        r = ck.check_one("Cloudflare", boom(f"https://api.cloudflare.com/accounts/{FAKE_ACCT}?t={FAKE_KEY}"),
                         ("CF_ACCOUNT_ID", "CF_API_TOKEN"), env)
        self.assertEqual(r["status"], "失敗")
        self.assertNotIn(FAKE_ACCT, r["detail"])
        self.assertNotIn(FAKE_KEY, r["detail"])
        self.assertIn("<CF_ACCOUNT_ID>", r["detail"])

    def test_no_verdict_is_a_failure(self):
        r = ck.check_one("NIM", lambda t, a, e: None, ("NVIDIA_API_KEY",), {"NVIDIA_API_KEY": FAKE_KEY})
        self.assertEqual(r["status"], "失敗")


class Main(unittest.TestCase):
    def run_main(self, providers, env):
        out = io.StringIO()
        with mock.patch.object(ck, "PROVIDERS", providers), contextlib.redirect_stdout(out):
            code = ck.main(["--env-file", os.devnull], env=env)
        return code, out.getvalue()

    def test_every_provider_is_called_even_after_a_success(self):
        calls = []

        def track(name):
            def fn(title, abstract, env):
                calls.append(name)
                return {"verdict": "keep", "model": name}
            return fn
        providers = [("A", track("a"), ("A_KEY",)), ("B", track("b"), ("B_KEY",))]
        code, _ = self.run_main(providers, {"A_KEY": "1", "B_KEY": "2"})
        self.assertEqual((code, calls), (0, ["a", "b"]))

    def test_one_failure_fails_the_run_and_summary_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            summary = os.path.join(d, "summary.md")
            env = {"GROQ_API_KEY": FAKE_KEY, "NVIDIA_API_KEY": FAKE_KEY, "GITHUB_STEP_SUMMARY": summary}
            providers = [("NVIDIA NIM", ok("nvidia/x"), ("NVIDIA_API_KEY",)),
                         ("Groq", boom(f"bad key {FAKE_KEY}"), ("GROQ_API_KEY",))]
            code, out = self.run_main(providers, env)
            with open(summary, encoding="utf-8") as f:
                written = f.read()
        self.assertEqual(code, 1)
        for text in (out, written):
            self.assertIn("❌ 失敗", text)
            self.assertIn("✅ 能用", text)
            self.assertNotIn(FAKE_KEY, text)

    def test_nothing_configured_fails(self):
        code, out = self.run_main(ck.PROVIDERS, {})
        self.assertEqual(code, 1)
        self.assertIn("沒設定", out)


if __name__ == "__main__":
    unittest.main()
