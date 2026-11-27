"""Topic forms for six question frameworks share one engine (pico_topic.py + topic_frameworks.py).
Offline: fake LLM, fake search, fake MeSH."""
import datetime
import glob
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

import helpers
import pico_topic as pt
import topic_frameworks as tf

HERE = os.path.dirname(os.path.abspath(__file__))
RADAR = os.path.dirname(HERE)
FORM_FILES = {"radar-topic.yml": "PICO", "radar-topic-cocopop.yml": "CoCoPop", "radar-topic-peco.yml": "PECO",
              "radar-topic-pird.yml": "PIRD", "radar-topic-cosmin.yml": "COSMIN",
              "radar-topic-pico-qualitative.yml": "PICo", "radar-topic-experiment.yml": "EXPERIMENT"}
QUERIES = {"PICO": 'TITLE:(stroke) AND TITLE:("mirror therapy")',
           "CoCoPop": 'TITLE:(dementia OR alzheimer*) AND TITLE:(older OR elderly) AND TITLE:(prevalence OR incidence)',
           "PECO": 'TITLE:(older OR elderly) AND TITLE:(sedentary OR "sitting time") AND TITLE:(falls OR fall)',
           "PIRD": 'TITLE:("Montreal Cognitive Assessment" OR MoCA) AND TITLE:("mild cognitive impairment" OR MCI)',
           "COSMIN": 'TITLE:("upper limb" OR "upper extremity") AND TITLE:(stroke) AND ABSTRACT:(reliability OR validity)',
           "PICo": 'TITLE:(stroke) AND TITLE:("return to work") AND ABSTRACT:(qualitative OR interview)',
           "EXPERIMENT": 'TITLE:(older OR elderly) AND TITLE:(handwriting OR writing) AND ABSTRACT:(kinematic OR kinematics)'}


def sample_body(fw, skip=()):
    lines = []
    for heading, key in tf.all_fields(fw).items():
        value = "_No response_" if key in skip or key == "replace_id" else f"範例 {key}"
        lines += [f"### {heading}", "", value, ""]
    return "\n".join(lines)


def propose(fw, body=None, llm=None):
    verdict = dict(llm or {"id": f"{fw.lower()} topic", "query": QUERIES[fw],
                           "rubric": "KEEP studies that fit. DROP protocols.", "mesh_terms": ["Stroke"],
                           "notes_zh": "說明。"}, tier="groq", model="m")

    def search(query, since, until, size):
        return 5, [{"firstPublicationDate": "2026-10-01", "title": "Paper."}]
    with mock.patch.object(pt.llm_triage, "triage", return_value=verdict) as call, \
            mock.patch.object(pt.llm_triage, "available", return_value=True):
        text = pt.propose(body or sample_body(fw), helpers.OT_CONFIG, search=search,
                          mesh=lambda t: True, today=datetime.date(2026, 11, 27), pause=0)
    return text, call


class EachFramework(unittest.TestCase):
    def test_detect_and_parse(self):
        for fw in tf.FRAMEWORKS:
            form = pt.parse_form(sample_body(fw))
            self.assertEqual(form["framework"], fw)
            self.assertEqual(pt.form_problems(form), [], fw)
            self.assertEqual(form["replace_id"], "")

    def test_required_fields(self):
        for fw, spec in tf.FRAMEWORKS.items():
            key = [k for k in spec["required"] if k != "label"][0]
            text, _ = propose(fw, sample_body(fw, skip=(key,)))
            self.assertIn("表單沒填完整", text, fw)

    def test_each_framework_uses_its_own_rules(self):
        for fw, spec in tf.FRAMEWORKS.items():
            text, call = propose(fw)
            system = call.call_args.kwargs["system"]
            self.assertIn(spec["query_rule"].splitlines()[0], system, fw)
            self.assertIn(spec["name"], system, fw)
            self.assertIn(spec["name"], text, fw)                 # the comment names the framework
            self.assertIn(spec["search"], text, fw)               # ...and what goes into the query
            p = pt.extract_proposal(text)
            self.assertEqual(p["framework"], fw)

    def test_diagnostic_accuracy_forbids_design_filters(self):
        self.assertIn("Do NOT add any study-design", tf.FRAMEWORKS["PIRD"]["query_rule"])

    def test_cosmin_searches_all_four(self):
        self.assertIn("ALL FOUR", tf.FRAMEWORKS["COSMIN"]["query_rule"])

    def test_apply_records_the_framework(self):
        d = tempfile.mkdtemp()
        try:
            cfg = os.path.join(d, "c.json")
            shutil.copy(helpers.OT_CONFIG, cfg)
            text, _ = propose("CoCoPop")
            pt.apply(text, cfg)
            with open(cfg, encoding="utf-8") as f:
                t = json.load(f)["topics"][-1]
            self.assertIn("CoCoPop", t["_來源"])
            pt.lw.load_config(cfg)
        finally:
            shutil.rmtree(d)

    def test_old_design_heading_still_parses(self):
        # Forms before 2026-11-27 had "### 研究設計"; it is now "S 研究設計（…）".
        for fw, body in (("PICO", "### P 對象（Population）\n\np\n\n### I 介入（Intervention）\n\ni\n\n### 研究設計\n\n隨機對照試驗\n"),
                         ("PECO", "### P 族群（Population）\n\np\n\n### E 暴露或危險因子（Exposure）\n\ne\n\n"
                                  "### O 結果（Outcome）\n\no\n\n### 研究設計\n\n病例對照研究\n")):
            form = pt.parse_form("### 主題名稱\n\nx\n\n" + body)
            self.assertEqual(form["framework"], fw)
            self.assertTrue(form["design"], fw)

    def test_pico_time_and_design_go_to_the_rubric(self):
        spec = tf.FRAMEWORKS["PICO"]
        self.assertIn("time (T)", spec["query_rule"])            # T is never searched
        self.assertIn("under T", spec["rubric_rule"])
        self.assertIn("under S", spec["rubric_rule"])
        form = pt.parse_form(sample_body("PICO"))
        self.assertEqual(form["t"], "範例 t")
        self.assertIn("T 時間", pt.form_as_text(form))

    def test_experiment_states_its_basis_and_excludes_treatment_trials(self):
        spec = tf.FRAMEWORKS["EXPERIMENT"]
        self.assertIn("PICOS", spec["name"])
        self.assertIn("沒有專屬框架", spec["basis"])           # honest about the source
        self.assertIn("MANIPULATE", spec["rubric_rule"])
        self.assertIn("intervention trials", spec["rubric_rule"])

    def test_peco_design_follows_s(self):
        self.assertIn("listed under S", tf.FRAMEWORKS["PECO"]["rubric_rule"])

    def test_pico_still_detected_from_old_forms(self):
        form = pt.parse_form("### 主題名稱\n\nx\n\n### P 對象（Population）\n\np\n\n### I 介入（Intervention）\n\ni\n")
        self.assertEqual(form["framework"], "PICO")


class FormFilesMatchTheTable(unittest.TestCase):
    """The issue forms' field labels must be exactly the headings the program reads."""

    def check_dir(self, d):
        found = 0
        for fname, fw in FORM_FILES.items():
            path = os.path.join(d, fname)
            if not os.path.exists(path):
                continue
            found += 1
            with open(path, encoding="utf-8") as f:
                text = f.read()
            labels = {m.strip().strip('"') for m in re.findall(r"^\s+label:\s*(.+)$", text, re.M)}
            self.assertEqual(labels, set(tf.all_fields(fw)), f"{path}")
        return found

    def test_template_copies(self):
        self.assertEqual(self.check_dir(os.path.join(RADAR, ".github", "ISSUE_TEMPLATE")), len(FORM_FILES))

    def test_repo_root_copies_if_present(self):
        root = os.path.join(os.path.dirname(RADAR), ".github", "ISSUE_TEMPLATE")
        if os.path.isdir(root):           # absent after someone copies only the template folder
            self.assertEqual(self.check_dir(root), len(FORM_FILES))


if __name__ == "__main__":
    unittest.main()
