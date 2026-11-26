#!/usr/bin/env python3
"""File-level check: open each downloaded file and see whether page 1 is the paper on your list.

check_doi.py checks the list (does the DOI match the title in Crossref?). This script
checks the file you actually got (is page 1 that paper, or a cited reference, a
preview page, a retraction notice?).

Input : papers.csv (columns PMID, DOI, 題名 / or pmid, doi, title) and a folder of
        files named PMID_<number>.pdf or PMID_<number>.txt
        (.pdf needs the pypdf package; .txt must hold the text of PAGE 1 ONLY --
        a whole paper would let a matching entry in its reference list pass).
Verdict order, worst first: 衝突 > 待查 > 無法判定 > 一致.
Output: a CSV with one verdict per paper: 一致 / 衝突 / 待查 / 無法判定.
        With --doi-result, the verdict from check_doi.py is merged in and the worse
        of the two levels is kept (as 驗證四級與攔截規則.md asks).
Standard library only for .txt files. License: MIT.
"""
import argparse
import csv
import os
import re
import sys

LEVELS = ["一致", "待查", "衝突"]  # 無法判定 is handled separately: it never counts as 一致
OUT_COLS = ["PMID", "doi", "檔案", "判定", "原因", "題名吻合比例", "第一頁找到的DOI", "頁數"]

# Retraction signals come in two strengths, so that ordinary words do not cry wolf.
# STRONG = the page is (or announces) a retraction -> 衝突.
STRONG_PHRASES = ["retracted article", "retraction note", "retraction notice", "notice of retraction",
                  "this article has been retracted", "has retracted this article", "have retracted this article",
                  "this article has been withdrawn", "expression of concern"]
# A banner line: "RETRACTED", "RETRACTED: <title>", or a line that is only "Retracted"/"Withdrawn".
STRONG_RE = re.compile(r"^\s*(RETRACTED|WITHDRAWN)\s*(:|$)|^\s*(retracted|withdrawn)\s*$", re.M | re.I)
# WEAK = a word that may mean retraction but also appears in normal papers
# ("the arm was retracted", "3 WITHDRAWN" in a CONSORT flow chart) -> 待查, a human looks.
# "scapular retraction" alone is not even weak: it is a common rehab term.
WEAK_RE = re.compile(r"\bretracted\b", re.I)
WEAK_CAPS_RE = re.compile(r"\bWITHDRAWN\b")
# Words that need a human look: the paper was corrected.
CHECK_WORDS = ["erratum", "corrigendum", "correction to:", "correction:", "author correction"]
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>,;]+", re.I)
STOP = {"with", "from", "that", "this", "were", "after", "into", "their", "versus", "among", "study", "trial"}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def clean_doi(d):
    """Lower-case a DOI and drop a URL/doi: prefix and trailing punctuation.
    A trailing ')' is dropped only when unbalanced: DOIs such as
    10.1016/S0140-6736(20)30367-6 legitimately contain brackets."""
    d = (d or "").strip().lower()
    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", d)
    while d and d[-1] in ".,;:]}":
        d = d[:-1]
    while d.endswith(")") and d.count(")") > d.count("("):
        d = d[:-1]
    return d


def title_overlap(title, text):
    """Share of the title's meaningful words (4+ letters) that appear on page 1."""
    words = [w for w in norm(title).split() if len(w) >= 4 and w not in STOP]
    if not words:
        return None
    page = set(norm(text).split())
    return sum(w in page for w in words) / len(words)


def read_pdf(path):
    """Return (page-1 text, page count). Raises ImportError if pypdf is not installed."""
    from pypdf import PdfReader  # optional dependency
    reader = PdfReader(path)
    n = len(reader.pages)
    return (reader.pages[0].extract_text() or "") if n else "", n


def find_files(folder, pmid):
    """Existing files for this PMID, .pdf first (it is the real file and has a page count)."""
    return [p for p in (os.path.join(folder, f"PMID_{pmid}{e}") for e in (".pdf", ".txt")) if os.path.exists(p)]


def check_text(row, text, pages=None):
    """Judge one paper from its page-1 text. Returns (verdict, reasons, overlap, found_dois)."""
    exp_doi, title = clean_doi(row.get("doi")), (row.get("title") or "").strip()
    low = " ".join(text.lower().split())
    found = sorted({clean_doi(d) for d in DOI_RE.findall(text)})
    verdict, reasons = "一致", []

    def raise_to(level, why):
        nonlocal verdict
        if LEVELS.index(level) > LEVELS.index(verdict):
            verdict = level
        reasons.append(why)

    strong = (any(w in low for w in STRONG_PHRASES)
              or any(m.group(0).strip()[:1].isupper() for m in STRONG_RE.finditer(text)))
    if strong:
        raise_to("衝突", "第一頁有撤稿／撤回／關注聲明，先攔截，人工確認")
    elif WEAK_RE.search(text) or WEAK_CAPS_RE.search(text):
        raise_to("待查", "第一頁出現 retracted／WITHDRAWN 字樣，可能是撤稿，也可能只是一般用字，人工看一下")
    if any(w in low for w in CHECK_WORDS):
        raise_to("待查", "第一頁有更正或勘誤字樣，確認你要的數字有沒有被改")
    overlap = title_overlap(title, text) if title and title != "待補" else None
    if overlap is not None:
        if overlap < 0.5:
            raise_to("衝突", "第一頁的題名跟清單差很多，可能抓到別篇（例如引用文獻）")
        elif overlap < 0.85:
            raise_to("待查", "第一頁的題名只對上一部分，人工看一下")
    else:
        raise_to("待查", "清單沒有題名，無法比對")
    no_list_doi = not exp_doi or exp_doi == "待補"
    if not no_list_doi:
        others = [d for d in found if d != exp_doi]
        if exp_doi not in found:
            if found:
                raise_to("待查", "第一頁找到的是別的 DOI，不是清單上的")
            else:
                raise_to("待查", "第一頁找不到 DOI，靠題名判斷")
        elif others:
            raise_to("待查", "第一頁除了清單上的 DOI 還有別的 DOI，確認這不是整篇或參考文獻")
    if pages == 1:
        raise_to("待查", "PDF 只有 1 頁，多半是預覽頁")
    if no_list_doi:
        reasons.append("清單沒有 DOI，只靠題名不能算一致，請先補 DOI")
        if verdict == "一致":
            verdict = "無法判定"
    return verdict, reasons, overlap, found


def check_one(row, folder):
    pmid = (row.get("pmid") or "").strip()
    out = {c: "" for c in OUT_COLS}
    out.update({"PMID": pmid, "doi": (row.get("doi") or "").strip()})
    paths = find_files(folder, pmid) if pmid else []
    if not paths:
        out.update({"判定": "無法判定", "原因": f"找不到檔案 PMID_{pmid}.pdf 或 .txt"})
        return out
    path, pages = paths[0], None
    try:
        if path.lower().endswith(".pdf"):
            try:
                text, pages = read_pdf(path)
                out["頁數"] = pages
            except ImportError:
                if len(paths) < 2:
                    out.update({"檔案": os.path.basename(path), "判定": "無法判定",
                                "原因": "讀 PDF 需要 pypdf（pip install pypdf），或先把第一頁轉成 .txt"})
                    return out
                path = paths[1]  # fall back to the page-1 text file
        if path.lower().endswith(".txt"):
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
    except Exception as e:  # broken file, or a web page saved as .pdf
        out["檔案"] = os.path.basename(path)
        out.update({"判定": "無法判定", "原因": f"檔案打不開（{type(e).__name__}），可能不是真的 PDF，請重取"})
        return out
    out["檔案"] = os.path.basename(path)
    if len(norm(text)) < 20:
        out.update({"判定": "無法判定", "原因": "讀不出文字（可能是掃描圖檔），請人工看"})
        return out
    verdict, reasons, overlap, found = check_text(row, text, pages)
    out.update({"判定": verdict, "原因": "；".join(reasons) or "第一頁的題名與 DOI 都對得上，沒有撤稿或更正字樣",
                "題名吻合比例": "" if overlap is None else f"{overlap:.2f}", "第一頁找到的DOI": ";".join(found)})
    return out


def worse(a, b):
    """The worse of two levels. 無法判定 beats 一致 (it is never 'fine') but not 衝突/待查."""
    rank = {"一致": 0, "無法判定": 1, "待查": 2, "衝突": 3}
    return a if rank.get(a, 1) >= rank.get(b, 1) else b


HEADER_ALIASES = {"pmid": "pmid", "doi": "doi", "title": "title", "題名": "title"}


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{HEADER_ALIASES[k.strip().lower()]: v for k, v in r.items()
                 if k and k.strip().lower() in HEADER_ALIASES} for r in csv.DictReader(f)]


def merge_doi_result(results, path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"doi", "判定"} <= set(reader.fieldnames or []):
            sys.exit(f"{path} 不像 check_doi.py 的輸出（需要 doi 與 判定 兩欄）")
        by_doi = {clean_doi(r["doi"]): r for r in reader}
    for r in results:
        d = by_doi.get(clean_doi(r["doi"]))
        if d is None:
            r["判定"] = worse(r["判定"], "無法判定")
            r["原因"] += "；清單層結果裡沒有這篇"
        elif worse(d["判定"], r["判定"]) == d["判定"] and d["判定"] != r["判定"]:
            r["判定"] = d["判定"]
            r["原因"] += f"；清單層判為{d['判定']}：{d['原因']}"


def main():
    ap = argparse.ArgumentParser(description="打開每個檔案，核對第一頁是不是清單上那一篇。")
    ap.add_argument("papers", help="論文清單 CSV（需有 PMID、DOI、題名）")
    ap.add_argument("folder", help="放檔案的資料夾，檔名 PMID_<編號>.txt 或 .pdf")
    ap.add_argument("--out", required=True, help="輸出 CSV 路徑")
    ap.add_argument("--doi-result", help="check_doi.py 的輸出；給了就取兩段中較差的一級")
    args = ap.parse_args()
    results = [check_one(r, args.folder) for r in read_rows(args.papers)]
    if args.doi_result:
        merge_doi_result(results, args.doi_result)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel shows Chinese correctly
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(results)
    tally = {}
    for r in results:
        tally[r["判定"]] = tally.get(r["判定"], 0) + 1
    print(f"核對了 {len(results)} 個檔案：" + "、".join(f"{k} {v}" for k, v in sorted(tally.items())) + f"。結果：{args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
