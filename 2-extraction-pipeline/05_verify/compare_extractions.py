#!/usr/bin/env python3
"""Compare two independent extractions of the same papers, cell by cell.

Inputs (pick one):
  --csv numbers_long.csv --labels A B     long CSV: one row per value, a model column
  --dir-a DIR --dir-b DIR                 two folders of <PMID>.json (quotes are optional)

Each cell (paper x arm x field) gets one verdict:
  agree         both models give the same number (or the same text for text fields)
  disagree      the two differ, or one says Unclear while the other gives a value
  both-unclear  both say Unclear (not an error: the paper may not report it)

Agreement rate = agree / (agree + disagree); both-unclear cells are left out of
the denominator. The script never decides which side is right: every
"disagree" cell goes to a human who checks the paper.
License: MIT.
"""
import argparse
import csv
import json
import os
import re
import sys

# (field, key, label, is_text). Text fields (dispersion type: SD/SE/IQR...) are
# compared as strings, because labelling the same number SD or SE changes the
# weight by a factor of sqrt(n) when pooling.
FIELDS = [
    ("n_randomized", "value", "隨機分派 N", False),
    ("n_analyzed", "value", "分析 N", False),
    ("fma_ue_pre", "mean", "前測 mean", False),
    ("fma_ue_pre", "dispersion", "前測 離散", False),
    ("fma_ue_pre", "dispersion_type", "前測 離散類型", True),
    ("fma_ue_post", "mean", "後測 mean", False),
    ("fma_ue_post", "dispersion", "後測 離散", False),
    ("fma_ue_post", "dispersion_type", "後測 離散類型", True),
    ("fma_ue_change", "mean", "變化量 mean", False),
    ("fma_ue_change", "dispersion", "變化量 離散", False),
    ("fma_ue_change", "dispersion_type", "變化量 離散類型", True),
]
UNCLEAR_WORDS = ("", "unclear", "nr", "n/a", "none")


def is_unclear(v):
    return v is None or str(v).strip().lower() in UNCLEAR_WORDS


def first_number(s):
    m = re.search(r"-?\d+(?:\.\d+)?", str(s))
    return float(m.group(0)) if m else None


def values_agree(a, b):
    """Strict rule: one Unclear + one value is a disagreement; otherwise the
    first number in each string must be exactly equal ("12.30" == "12.3",
    "12.3 (4.1)" == "12.3"). No tolerance: extraction forbids conversions."""
    if is_unclear(a) or is_unclear(b):
        return False
    na, nb = first_number(a), first_number(b)
    return na is not None and na == nb


def judge(va, vb, is_text):
    if is_unclear(va) and is_unclear(vb):
        return "both-unclear"
    if is_text:
        return "agree" if str(va).strip().lower() == str(vb).strip().lower() else "disagree"
    return "agree" if values_agree(va, vb) else "disagree"


# Both loaders return:
# {pmid: {arm_index: {"name": str, "cells": {(field, key): (value, location)}}}}

def load_json_dir(folder):
    out = {}
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(folder, fn), encoding="utf-8") as f:
            doc = json.load(f)
        pmid = str(doc.get("pmid") or fn[:-5])
        arms = {}
        for i, arm in enumerate(doc.get("arms", []), start=1):
            cells = {}
            for field, key, _label, _t in FIELDS:
                d = arm.get(field) or {}
                cells[(field, key)] = (str(d.get(key, "Unclear")), d.get("location", ""))
            arms[i] = {"name": arm.get("arm_name", ""), "cells": cells}
        out[pmid] = arms
    return out


def load_csv(path, label):
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["模型"] != label:
                continue
            field, _, key = r["欄位"].partition(".")
            arm = out.setdefault(r["PMID"], {}).setdefault(
                int(r["組序"]), {"name": r["組別"], "cells": {}})
            arm["cells"][(field, key)] = (r["數值"], r.get("原文位置", ""))
    return out


def compare(a_all, b_all):
    """Return a list of cell dicts, one per paper x arm x field."""
    cells = []
    for pmid in sorted(set(a_all) | set(b_all)):
        arms_a, arms_b = a_all.get(pmid, {}), b_all.get(pmid, {})
        for i in sorted(set(arms_a) | set(arms_b)):
            ra = arms_a.get(i, {"name": "", "cells": {}})
            rb = arms_b.get(i, {"name": "", "cells": {}})
            for field, key, label, is_text in FIELDS:
                va, la = ra["cells"].get((field, key), ("Unclear", ""))
                vb, lb = rb["cells"].get((field, key), ("Unclear", ""))
                cells.append({"pmid": pmid, "arm": i, "label": label,
                              "va": va, "vb": vb, "loc_a": la, "loc_b": lb,
                              "verdict": judge(va, vb, is_text)})
    return cells


def summarize(cells):
    n = {"agree": 0, "disagree": 0, "both-unclear": 0}
    for c in cells:
        n[c["verdict"]] += 1
    denom = n["agree"] + n["disagree"]
    rate = n["agree"] / denom if denom else None
    return {"total": len(cells), **n, "denominator": denom, "rate": rate}


MARK = {"agree": "一致", "disagree": "不一致", "both-unclear": "都 Unclear"}


def render(cells, summary, la, lb, title):
    rate = f"{summary['rate']:.0%}" if summary["rate"] is not None else "無可比對格"
    lines = [f"# {title}", "",
             f"- 比對格數：{summary['total']}",
             f"- 一致：{summary['agree']}｜不一致：{summary['disagree']}｜都 Unclear：{summary['both-unclear']}",
             f"- 一致率：{rate}（分母＝一致＋不一致＝{summary['denominator']}，不含都 Unclear）",
             "- 「不一致」一律回原文由人判定；本表不判斷哪一邊對。「都 Unclear」可能是原文沒報，也要抽查。", ""]
    bad = [c for c in cells if c["verdict"] == "disagree"]
    lines += ["## 不一致清單（要人看原文）", "",
              f"| PMID | 組序 | 欄位 | {la} | {lb} | {la} 位置 | {lb} 位置 |", "|---|---|---|---|---|---|---|"]
    for c in bad:
        lines.append(f"| {c['pmid']} | {c['arm']} | {c['label']} | {c['va']} | {c['vb']} | "
                     f"{c['loc_a']} | {c['loc_b']} |".replace("\n", " "))
    if not bad:
        lines.append("| （無） | | | | | | |")
    lines += ["", "## 全部格子", "",
              f"| PMID | 組序 | 欄位 | {la} | {lb} | 判定 |", "|---|---|---|---|---|---|"]
    for c in cells:
        lines.append(f"| {c['pmid']} | {c['arm']} | {c['label']} | {c['va']} | {c['vb']} | {MARK[c['verdict']]} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="比對兩個模型的萃取結果，不判斷誰對誰錯。")
    ap.add_argument("--csv", help="長格式 CSV（欄位：PMID、組序、組別、欄位、數值、單位、模型、是否Unclear、原文位置）")
    ap.add_argument("--labels", nargs=2, default=["模型A", "模型B"],
                    help="兩個模型在 CSV「模型」欄裡的名字，也會當報告標籤")
    ap.add_argument("--dir-a", help="模型 A 的 JSON 資料夾")
    ap.add_argument("--dir-b", help="模型 B 的 JSON 資料夾")
    ap.add_argument("--out", required=True, help="輸出的 Markdown 報告路徑")
    ap.add_argument("--title", default="雙模型萃取對照表")
    args = ap.parse_args()
    la, lb = args.labels
    try:
        if args.csv:
            a, b = load_csv(args.csv, la), load_csv(args.csv, lb)
        elif args.dir_a and args.dir_b:
            a, b = load_json_dir(args.dir_a), load_json_dir(args.dir_b)
        else:
            sys.exit("請給 --csv，或同時給 --dir-a 與 --dir-b。")
    except (OSError, KeyError, ValueError) as e:
        sys.exit(f"讀檔失敗：{e}")
    if not a or not b:
        sys.exit("其中一個模型沒有讀到任何資料；請檢查 --labels 是否與 CSV 的「模型」欄一致。")
    cells = compare(a, b)
    summary = summarize(cells)
    md = render(cells, summary, la, lb, args.title)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:  # write then replace: a crash never leaves a half file
        f.write(md)
    os.replace(tmp, args.out)
    rate = f"{summary['rate']:.0%}" if summary["rate"] is not None else "無"
    print(f"比對 {summary['total']} 格：一致 {summary['agree']}、不一致 {summary['disagree']}、"
          f"都 Unclear {summary['both-unclear']}；一致率 {rate}（分母 {summary['denominator']}）。報告：{args.out}")


if __name__ == "__main__":
    main()
