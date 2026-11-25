#!/usr/bin/env python3
"""Look up DOIs in Crossref and compare with what you expect (title, journal, year).

Also reports whether Crossref lists an update notice (retraction, correction...).
Input : a CSV with a header row; columns: doi (required), title, journal, year
        (the last three are optional "what I expect" values), or a plain text
        file with one DOI per line.
Output: a CSV table with one verdict per DOI: 一致 / 衝突 / 待查 / 無法判定.
Standard library only. The network call is one small function (fetch_crossref)
so you can replace it, or run offline with --offline-json (a file of saved
Crossref records; the tests use it).
License: MIT.
"""
import argparse
import csv
import difflib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.crossref.org/works/"
# Update types that must stop the file from being used until a human looks.
BLOCK_TYPES = {"retraction", "withdrawal", "removal", "expression_of_concern"}
# Update types that need a human look but do not by themselves block.
CHECK_TYPES = {"correction", "erratum", "corrigendum", "addendum", "clarification", "new_edition",
               "new_version", "other"}
OUT_COLS = ["doi", "判定", "原因", "Crossref題名", "Crossref期刊", "Crossref年", "更新紀錄",
            "預期題名", "預期期刊", "預期年", "題名相似度"]


def fetch_crossref(doi, mailto=None, timeout=20):
    """Return the Crossref 'message' dict for a DOI, or None if not found.

    Replace this function to use another source or a cache. Raises OSError on
    network trouble so the caller can mark the row as 無法判定.
    """
    ua = "extraction-pipeline-doi-check/1.0" + (f" (mailto:{mailto})" if mailto else "")
    req = urllib.request.Request(API + urllib.parse.quote(doi, safe="/"), headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))["message"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise OSError(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise OSError(str(e.reason)) from e


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def first(v):
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""


def record_year(rec):
    for k in ("published-print", "published-online", "issued", "published"):
        parts = (rec.get(k) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def update_notes(rec):
    """List update notices as 'type' strings. Crossref puts them in 'updated-by'
    (on the original article) and 'update-to' (on the notice itself). If both
    are absent we cannot say the article is clean: it only means Crossref has
    no such record."""
    notes = []
    for key in ("updated-by", "update-to"):
        for u in rec.get(key) or []:
            notes.append(str(u.get("type") or u.get("label") or "other").lower().replace(" ", "_"))
    return notes


def check_one(row, fetch=fetch_crossref):
    """Return one output dict for an input row {'doi','title','journal','year'}."""
    doi = (row.get("doi") or "").strip()
    out = {c: "" for c in OUT_COLS}
    out["doi"] = doi
    # "待補" (to be filled) means "no expectation yet", not a value to compare against
    exp_title, exp_journal, exp_year = [("" if (row.get(k) or "").strip() == "待補" else (row.get(k) or "").strip())
                                        for k in ("title", "journal", "year")]
    out.update({"預期題名": exp_title, "預期期刊": exp_journal, "預期年": exp_year})
    if not doi or doi == "待補":
        out.update({"判定": "無法判定", "原因": "沒有 DOI，請先補 DOI"})
        return out
    try:
        rec = fetch(doi)
    except OSError as e:
        out.update({"判定": "無法判定", "原因": f"查詢失敗（{e}），不代表 DOI 有問題，請稍後重試"})
        return out
    if rec is None:
        out.update({"判定": "衝突", "原因": "Crossref 查無此 DOI（可能抄錯，或不是 Crossref 登記的 DOI）"})
        return out
    title, journal, year = first(rec.get("title")), first(rec.get("container-title")), record_year(rec)
    notes = update_notes(rec)
    out.update({"Crossref題名": title, "Crossref期刊": journal, "Crossref年": year or "",
                "更新紀錄": ";".join(notes)})
    reasons, verdict = [], "一致"

    def raise_to(level, why):
        nonlocal verdict
        order = ["一致", "待查", "衝突"]
        if order.index(level) > order.index(verdict):
            verdict = level
        reasons.append(why)

    if any(n in BLOCK_TYPES for n in notes):
        raise_to("衝突", "Crossref 有撤稿／撤回／關注聲明紀錄，先攔截，人工確認")
    elif notes:
        raise_to("待查", "Crossref 有更新紀錄（如更正），確認你的數字沒被更正影響")
    if exp_title:
        ratio = difflib.SequenceMatcher(None, norm(exp_title), norm(title)).ratio()
        out["題名相似度"] = f"{ratio:.2f}"
        if ratio < 0.5:
            raise_to("衝突", "題名差很多，DOI 可能指到別篇")
        elif ratio < 0.85:
            raise_to("待查", "題名略有出入，人工看一下")
    if exp_year:
        try:
            if year is None:
                raise_to("待查", "Crossref 沒有年份")
            elif abs(int(exp_year) - year) > 1:
                raise_to("衝突", f"年份差距大（預期 {exp_year}，Crossref {year}）")
            elif int(exp_year) != year:
                raise_to("待查", f"年份差 1 年（預期 {exp_year}，Crossref {year}），可能是線上／紙本差異")
        except ValueError:
            raise_to("待查", "預期年份不是數字")
    if exp_journal:
        known = [norm(j) for j in (journal, first(rec.get("short-container-title"))) if j]
        if norm(exp_journal) not in known:
            s = max([difflib.SequenceMatcher(None, norm(exp_journal), k).ratio() for k in known] or [0])
            # Abbreviations look very different from full names, so a journal mismatch
            # alone is never a conflict when the title already matches.
            if s >= 0.6 or exp_title:
                raise_to("待查", "期刊名不同（縮寫或改名也可能）")
            else:
                raise_to("衝突", "期刊名差很多")
    out["判定"] = verdict
    out["原因"] = "；".join(reasons) or "題名、期刊、年份與預期相符，且 Crossref 無更新紀錄"
    return out


def read_input(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    first_line = text.splitlines()[0] if text.strip() else ""
    if "," in first_line or first_line.strip().lower() == "doi":
        return [normalize_keys(r) for r in csv.DictReader(text.splitlines())]
    return [{"doi": ln.strip()} for ln in text.splitlines() if ln.strip()]


# Accept English or Chinese column headers (papers.csv uses Chinese ones).
HEADER_ALIASES = {"doi": "doi", "title": "title", "題名": "title", "journal": "journal",
                  "期刊": "journal", "year": "year", "年": "year"}


def normalize_keys(row):
    out = {}
    for k, v in row.items():
        key = HEADER_ALIASES.get((k or "").strip().lower())
        if key:
            out[key] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="用 Crossref 查 DOI 對得上題名／期刊／年份嗎，有沒有撤稿或更正紀錄。")
    ap.add_argument("input", help="DOI 清單（CSV 或一行一個 DOI 的文字檔）")
    ap.add_argument("--out", required=True, help="輸出 CSV 路徑")
    ap.add_argument("--mailto", help="你的聯絡信箱，Crossref 禮貌使用規範建議附上（不會寫進輸出檔）")
    ap.add_argument("--offline-json", help="離線測試：存好的 Crossref 紀錄檔（{DOI: 紀錄}），不連網")
    args = ap.parse_args()
    rows = read_input(args.input)
    if args.offline_json:
        with open(args.offline_json, encoding="utf-8") as f:
            saved = json.load(f)

        def fetch(doi):
            return saved.get(doi)
    else:
        def fetch(doi):
            return fetch_crossref(doi, args.mailto)
    results = [check_one(r, fetch) for r in rows]
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel shows Chinese correctly
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(results)
    tally = {}
    for r in results:
        tally[r["判定"]] = tally.get(r["判定"], 0) + 1
    print(f"查了 {len(results)} 筆：" + "、".join(f"{k} {v}" for k, v in sorted(tally.items())) + f"。結果：{args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
