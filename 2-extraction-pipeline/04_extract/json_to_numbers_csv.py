#!/usr/bin/env python3
"""Flatten extraction JSON files (one per paper) into a long CSV of numbers.

The long CSV keeps: PMID, arm index, arm name, field, value, unit, model,
is-Unclear flag, and the location (e.g. "Table 2"). It deliberately drops the
verbatim quote, so the CSV can be shared without reproducing paper text.

Usage:
  python json_to_numbers_csv.py --model "ModelA" dirA --model "ModelB" dirB --out numbers.csv
Each directory holds <PMID>.json files that follow extraction_schema.json.
License: MIT.
"""
import argparse
import csv
import json
import os
import sys

# (JSON field, JSON key, unit). Unit "" means the value is text, not a number.
FIELDS = [
    ("n_randomized", "value", "人"),
    ("n_analyzed", "value", "人"),
    ("fma_ue_pre", "mean", "分"),
    ("fma_ue_pre", "dispersion", "分"),
    ("fma_ue_pre", "dispersion_type", ""),
    ("fma_ue_post", "mean", "分"),
    ("fma_ue_post", "dispersion", "分"),
    ("fma_ue_post", "dispersion_type", ""),
    ("fma_ue_change", "mean", "分"),
    ("fma_ue_change", "dispersion", "分"),
    ("fma_ue_change", "dispersion_type", ""),
]
HEADER = ["PMID", "組序", "組別", "欄位", "數值", "單位", "模型", "是否Unclear", "原文位置"]


def is_unclear(v):
    return v is None or str(v).strip().lower() in ("", "unclear", "nr", "n/a", "none")


def rows_for(model, folder):
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(folder, fn), encoding="utf-8") as f:
            doc = json.load(f)
        pmid = str(doc.get("pmid") or fn[:-5])
        for i, arm in enumerate(doc.get("arms", []), start=1):
            for field, key, unit in FIELDS:
                d = arm.get(field) or {}
                val = str(d.get(key, "Unclear"))
                yield [pmid, i, arm.get("arm_name", ""), f"{field}.{key}", val, unit,
                       model, "是" if is_unclear(val) else "否", d.get("location", "")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", nargs=2, action="append", metavar=("LABEL", "DIR"), required=True,
                    help="model label and its folder of JSON files (repeat for each model)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rows = []
    for label, folder in args.model:
        if not os.path.isdir(folder):
            sys.exit(f"找不到資料夾：{folder}")
        rows.extend(rows_for(label, folder))
    # utf-8-sig so that Excel in a Chinese locale shows the text correctly
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print(f"已寫出 {len(rows)} 列 -> {args.out}")


if __name__ == "__main__":
    main()
