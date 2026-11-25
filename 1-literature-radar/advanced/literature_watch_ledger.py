#!/usr/bin/env python3
"""Advanced entry point: the same radar, but papers are judged by comparing AI-read facts
with a ledger of what you already use (see README.md in this folder).

Run from the repository root:
  python advanced/literature_watch_ledger.py --config advanced/config.dementia-example.json \\
      --triage --seen-file seen.json --out report.md

All options of scripts/literature_watch.py work here. The config needs a `ledger` entry whose
path is relative to the config file. If the ledger cannot be read, the run falls back to the
plain keep/drop rubric and the report says so.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import literature_watch as lw  # noqa: E402
import facts  # noqa: E402
import triage_rules  # noqa: E402

HEADER = ("_AI 只讀出論文的事實，再由程式和你的帳本比對：由 {models} 讀取。保留＝資料比帳本新或帳本有缺口；"
          "較舊、同一份資料、非全人口估計的論文被收合，並附上比對理由。_")


def make_judge(ledger):
    def judge(rec, label):
        f = facts.extract(rec.get("title", ""), rec.get("abstractText", ""), ledger, hint=label)
        if not f:
            return None                       # fail-open: the caller keeps the paper
        bucket, why = triage_rules.decide(f, ledger)
        return {"verdict": "keep" if bucket == triage_rules.UPDATE else "drop", "reason": why,
                "bucket": bucket, "tier": f.get("tier"), "model": f.get("model")}
    return judge


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=lw.DEFAULT_CONFIG)
    known, _ = pre.parse_known_args(argv)
    notes, judge, header = [], None, None
    try:
        cfg = lw.load_config(known.config)
        if not cfg.get("ledger"):
            raise ValueError("設定檔沒有 ledger 欄位")
        ledger_path = os.path.join(os.path.dirname(os.path.abspath(known.config)), cfg["ledger"])
        ledger = triage_rules.load_ledger(ledger_path)
        judge, header = make_judge(ledger), HEADER
    except lw.ConfigError:
        pass                                   # lw.main will print the proper message and exit
    except (OSError, ValueError, KeyError) as e:
        notes.append(f"【警告】帳本讀不了（{type(e).__name__}: {e}），已退回一般的保留／篩掉判準")
    return lw.main(argv, judge=judge, extra_notes=notes, judge_header=header)


if __name__ == "__main__":
    main()
