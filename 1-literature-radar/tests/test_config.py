"""Config files: the shipped ones must parse, and mistakes must give a readable message."""
import glob
import os
import tempfile
import unittest

import helpers
from helpers import lw


class ShippedConfigs(unittest.TestCase):
    def test_every_config_in_config_dir_loads(self):
        paths = glob.glob(os.path.join(helpers.ROOT, "config", "*.json"))
        self.assertGreaterEqual(len(paths), 3)
        for p in paths:
            with self.subTest(p=os.path.basename(p)):
                cfg = lw.load_config(p)
                self.assertTrue(cfg["topics"])

    def test_ot_config_has_four_topics_with_unique_ids(self):
        cfg = lw.load_config(helpers.OT_CONFIG)
        ids = [t["id"] for t in cfg["topics"]]
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(set(ids)), 4)

    def test_underscore_keys_are_comments(self):
        cfg = lw.load_config(os.path.join(helpers.ROOT, "config", "literature-watch.template.json"))
        self.assertEqual(cfg["days_window"], 45)


class Mistakes(unittest.TestCase):
    def _load(self, obj=None, text=None):
        d = tempfile.mkdtemp()
        if text is not None:
            p = os.path.join(d, "c.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            p = helpers.write_json(d, "c.json", obj)
        return lw.load_config(p)

    def test_missing_file(self):
        with self.assertRaisesRegex(lw.ConfigError, "找不到設定檔"):
            lw.load_config(os.path.join(tempfile.mkdtemp(), "nope.json"))

    def test_broken_json_names_the_usual_causes(self):
        with self.assertRaisesRegex(lw.ConfigError, "不是合法的 JSON"):
            self._load(text='{"topics": [ {"label": "a", } ]}')

    def test_no_topics(self):
        with self.assertRaisesRegex(lw.ConfigError, "topics"):
            self._load({"days_window": 45})

    def test_topic_without_query(self):
        with self.assertRaisesRegex(lw.ConfigError, "第 1 個主題"):
            self._load({"topics": [{"label": "x"}]})

    def test_bad_number(self):
        with self.assertRaisesRegex(lw.ConfigError, "days_window"):
            self._load({"days_window": "abc", "topics": [{"label": "x", "query": "TITLE:a"}]})
        with self.assertRaisesRegex(lw.ConfigError, "max_per_topic"):
            self._load({"max_per_topic": 0, "topics": [{"label": "x", "query": "TITLE:a"}]})

    def test_cli_exits_with_message_on_bad_config(self):
        with self.assertRaises(SystemExit) as cm:
            helpers.run_main(["--config", os.path.join(tempfile.mkdtemp(), "nope.json")])
        self.assertEqual(cm.exception.code, 2)


class DotEnv(unittest.TestCase):
    def test_reads_values_skips_empty_and_never_overrides(self):
        p = os.path.join(tempfile.mkdtemp(), ".env")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# comment\nLITTEST_A=abc\nLITTEST_EMPTY=\nLITTEST_KEEP=new\n")
        os.environ["LITTEST_KEEP"] = "old"
        try:
            n = lw.load_dotenv(p)
            self.assertEqual((n, os.environ["LITTEST_A"], os.environ["LITTEST_KEEP"]), (1, "abc", "old"))
            self.assertNotIn("LITTEST_EMPTY", os.environ)
        finally:
            for k in ("LITTEST_A", "LITTEST_KEEP", "LITTEST_EMPTY"):
                os.environ.pop(k, None)

    def test_missing_file_is_fine(self):
        self.assertEqual(lw.load_dotenv(os.path.join(tempfile.mkdtemp(), "none.env")), 0)


if __name__ == "__main__":
    unittest.main()
