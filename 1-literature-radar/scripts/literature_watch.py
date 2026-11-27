#!/usr/bin/env python3
"""Literature radar: search Europe PMC for new papers, de-duplicate, optionally let an
AI keep/drop them, and write a report (or open a GitHub Issue from it).

Europe PMC is a free index of PubMed, PMC and preprints; no key is needed. For each
topic in the config file the script lists papers first published in the last
`days_window` days as CANDIDATES for a person to read. It never decides for you.

Design rules (each one has a test in tests/):
  * Fail-open: no AI key, or an AI failure, means "list everything", and the report says so.
  * A topic whose search fails is reported as unchecked, never as "nothing new".
  * De-duplication with two keys per paper (link + normalised title), because Europe PMC
    can return the same article twice (a MEDLINE record and a PMC record).
  * Earlier reports are the memory: --seen-from-issues reads old GitHub Issues back,
    --seen-file keeps a local JSON list. No hidden state file in the repo.
  * Truncation is stated: if a topic has more hits than `max_per_topic`, the report says
    how many were NOT scanned.

Usage (run from the repository root):
  python scripts/literature_watch.py --config config/literature-watch.ot.json --out report.md
  python scripts/literature_watch.py --config config/literature-watch.ot.json --triage \\
      --seen-file seen.json --out report.md
  python scripts/literature_watch.py --config config/literature-watch.ot.json \\
      --fixture examples/mock_epmc_response.json          # offline check, no network

Standard library only.
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import http_retry
import llm_triage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_CONFIG = os.path.join(ROOT, "config", "literature-watch.json")

DEFAULT_ENV_FILE = os.path.join(ROOT, ".env")


def ua():
    """Europe PMC asks clients to identify themselves. An optional contact address is read
    from the environment so no personal address is ever stored in the repository."""
    contact = os.environ.get("LITWATCH_CONTACT", "").strip()
    return {"User-Agent": "literature-radar/1.0 " + (f"(mailto:{contact})" if contact else "(no contact set)")}


def load_dotenv(path):
    """Read KEY=VALUE lines from a .env file into os.environ. Never overrides a variable that
    is already set, and skips empty values. Returns the number of variables it set."""
    n = 0
    try:
        with open(path, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and v and k not in os.environ:
                    os.environ[k] = v
                    n += 1
    except OSError:
        pass
    return n
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
GH_API = "https://api.github.com"
TIMEOUT = 30
LINK_RE = re.compile(r"https://(?:doi\.org/[^\s)\]>]+|europepmc\.org/article/[^\s)\]>]+)")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")


class ConfigError(Exception):
    """The config file cannot be used. The message is written for the person who edits it."""


# ---- config ---------------------------------------------------------------
def load_config(path):
    """Read and check a config file. Keys that start with '_' are comments and ignored."""
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"找不到設定檔：{path}。請先把 config/ 裡的範例複製一份，再用 --config 指定它。")
    except ValueError as e:
        raise ConfigError(f"設定檔 {path} 不是合法的 JSON（{e}）。常見原因：漏了逗號、最後一項後面多了逗號、"
                          "引號沒成對、查詢句裡的雙引號沒有寫成 \\\"。")
    if not isinstance(cfg, dict):
        raise ConfigError(f"設定檔 {path} 最外層必須是 {{ }}。")
    topics = cfg.get("topics")
    if not isinstance(topics, list) or not topics:
        raise ConfigError("設定檔裡的 topics 必須是至少一個主題的清單。")
    for i, t in enumerate(topics, 1):
        if not isinstance(t, dict) or not str(t.get("label", "")).strip() or not str(t.get("query", "")).strip():
            raise ConfigError(f"第 {i} 個主題缺 label（顯示名稱）或 query（Europe PMC 查詢句）。")
    for key in ("days_window", "max_per_topic"):
        if key in cfg:
            try:
                ok = int(cfg[key]) > 0
            except (TypeError, ValueError):
                ok = False
            if not ok:
                raise ConfigError(f"{key} 必須是大於 0 的整數（目前是 {cfg[key]!r}）。")
    if "max_per_topic" in cfg and int(cfg["max_per_topic"]) > 1000:
        raise ConfigError("max_per_topic 不要超過 1000（Europe PMC 單頁上限）。")
    return cfg


# ---- Europe PMC -----------------------------------------------------------
def epmc_search(query, since_iso, until_iso, page_size):
    """(hitCount, [records]) for papers first published in the date range."""
    full = f"({query}) AND (FIRST_PDATE:[{since_iso} TO {until_iso}])"
    params = urllib.parse.urlencode({
        "query": full, "format": "json", "pageSize": str(page_size),
        "sort": "P_PDATE_D desc", "resultType": "core",   # core includes the abstract
    })
    req = urllib.request.Request(f"{EPMC}?{params}", headers=ua())
    d = json.loads(http_retry.fetch(req, TIMEOUT).decode("utf-8", "replace"))
    return d.get("hitCount", 0), d.get("resultList", {}).get("result", [])


def fixture_search(fixture, topic_id, page_size):
    """Offline stand-in for epmc_search: read the answer from a saved JSON file.

    The file maps a topic id (or "*" for every topic) to a Europe PMC style answer:
    {"hitCount": 3, "resultList": {"result": [ ...records... ]}}"""
    d = fixture.get(topic_id) or fixture.get("*") or {}
    results = (d.get("resultList") or {}).get("result", [])
    return d.get("hitCount", len(results)), results[:page_size]


def journal_of(rec):
    return (rec.get("journalTitle")
            or (rec.get("journalInfo") or {}).get("journal", {}).get("title")
            or (rec.get("bookOrReportDetails") or {}).get("publisher")
            or "預印本／其他")


def link_for(rec):
    if rec.get("doi"):
        return f"https://doi.org/{rec['doi']}"
    src, rid = rec.get("source"), rec.get("id")
    return f"https://europepmc.org/article/{src}/{rid}" if src and rid else ""


# ---- de-duplication -------------------------------------------------------
def _title_key(title):
    return "title:" + re.sub(r"\W+", " ", (title or "").lower()).strip()


def paper_keys(rec):
    """Keys that identify one paper, so the same work found twice is listed once.

    Two keys are needed. Europe PMC may return a MEDLINE record (with a DOI) and a PMC
    record (often without one) for the same article. The link catches re-runs; the
    normalised title catches the MEDLINE/PMC pair. Both appear in the printed report,
    so an old report can be read back with a regex (see keys_in_text)."""
    keys = {_title_key(rec.get("title"))}
    url = link_for(rec)
    if url:
        keys.add(url.lower().rstrip(".,;"))
    return keys


def keys_in_text(text):
    """Paper keys (links and titles) found in an earlier report: the inverse of line_for."""
    keys = {m.lower().rstrip(".,;") for m in LINK_RE.findall(text or "")}
    keys |= {_title_key(t) for t, _ in MD_LINK_RE.findall(text or "")}
    return keys


def seen_from_issues(label):
    """Paper keys already listed in this repository's earlier Issues that carry `label`.

    Returns (keys, error). Needs GITHUB_REPOSITORY and GH_TOKEN (or GITHUB_TOKEN), which
    GitHub Actions provides. Anything else returns an error and the caller fails open."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        return set(), "GITHUB_REPOSITORY / GH_TOKEN 未設定"
    keys = set()
    try:
        for page in range(1, 6):                       # up to 500 issues = many years of monthly runs
            q = urllib.parse.urlencode({"labels": label, "state": "all", "per_page": 100, "page": page})
            req = urllib.request.Request(f"{GH_API}/repos/{repo}/issues?{q}", headers={
                **ua(), "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
            batch = json.loads(http_retry.fetch(req, TIMEOUT).decode("utf-8", "replace"))
            for issue in batch:
                keys |= keys_in_text(issue.get("body"))
            if len(batch) < 100:
                break
    except (*http_retry.FETCH_ERRORS, ValueError) as e:
        return set(), http_retry.describe(e)
    return keys, None


# ---- report ---------------------------------------------------------------
def line_for(rec, verdict=None):
    title = (rec.get("title") or "").rstrip(".")
    url = link_for(rec)
    cite = f"[{title}]({url})" if url else title
    tag = f" — _{verdict['reason']}_" if verdict and verdict.get("reason") else ""
    return f"- {rec.get('firstPublicationDate', '?')} · *{journal_of(rec)}* — {cite}{tag}"


def default_judge(rec, label):
    """The standard keep/drop judgement, using the config's rubric."""
    return llm_triage.triage(rec.get("title", ""), (rec.get("abstractText") or "")
                             + f"\n\n(Found by a search for: {label})")


def main(argv=None, judge=None, extra_notes=None, judge_header=None):
    """Run the radar. Returns the report text.

    judge        optional callable (record, topic_label) -> verdict dict or None; used by
                 advanced/ to swap in a different way of judging. Default: keep/drop rubric.
    extra_notes  optional list of lines appended to the report footer.
    judge_header optional text for the AI line when a custom judge answered; may contain {models}.
    """
    ap = argparse.ArgumentParser(description="每月文獻雷達：Europe PMC 檢索、去重、可選的 AI 篩選。")
    ap.add_argument("--config", default=DEFAULT_CONFIG,
                    help="關鍵字設定檔（預設 config/literature-watch.json）")
    ap.add_argument("--out", default="", help="報告檔路徑；不給就印在螢幕上")
    ap.add_argument("--append", action="store_true", help="接在 --out 檔案後面，而不是覆蓋")
    ap.add_argument("--triage", action="store_true", help="啟用 AI 保留／篩掉（需要至少一組金鑰；沒有就全列）")
    ap.add_argument("--seen-from-issues", metavar="LABEL", default="",
                    help="略過這個標籤的舊 Issue 裡已列過的論文（GitHub Actions 用）")
    ap.add_argument("--seen-file", default="",
                    help="本機模式：已報告過的論文清單（JSON），讀取後更新")
    ap.add_argument("--env-file", default=DEFAULT_ENV_FILE,
                    help="存放金鑰的 .env 檔（預設：專案根目錄的 .env；檔案不存在就略過）")
    ap.add_argument("--fixture", default="",
                    help="離線驗證：用存好的 Europe PMC 回應檔代替網路檢索")
    args = ap.parse_args(argv)
    load_dotenv(args.env_file)

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"[錯誤] {e}", file=sys.stderr)
        sys.exit(2)
    fixture = None
    if args.fixture:
        try:
            with open(args.fixture, encoding="utf-8") as f:
                fixture = json.load(f)
        except (OSError, ValueError) as e:
            print(f"[錯誤] 讀不了 --fixture 檔：{e}", file=sys.stderr)
            sys.exit(2)

    config_name = os.path.basename(args.config)
    window = int(cfg.get("days_window", 45))
    per_topic = int(cfg.get("max_per_topic", 6))
    until = datetime.date.today()
    since = until - datetime.timedelta(days=window)
    since_iso, until_iso = since.isoformat(), until.isoformat()

    # A topic may carry its own `rubric` (e.g. one written from a PICO form); topics
    # without one use the config-wide rubric, so older config files behave as before.
    base_rubric = cfg.get("rubric") or llm_triage.DEFAULT_RUBRIC
    rubric_missing = bool(args.triage) and not cfg.get("rubric") \
        and not all(str(t.get("rubric") or "").strip() for t in cfg["topics"])
    llm_triage.RUBRIC = base_rubric
    keys_present = llm_triage.available()
    do_triage = bool(args.triage and keys_present)
    judge = judge or default_judge

    seen, seen_note = set(), ""
    if args.seen_from_issues:
        seen, err = seen_from_issues(args.seen_from_issues)
        seen_note = (f"【警告】讀不到舊的 Issue（{err}），所以過去幾個月列過的論文可能重複出現"
                     if err else f"已讀回舊 Issue（標籤 `{args.seen_from_issues}`）裡的 {len(seen)} 筆論文紀錄")
    if args.seen_file and os.path.exists(args.seen_file):
        try:
            with open(args.seen_file, encoding="utf-8") as f:
                seen |= set(json.load(f))
        except ValueError:
            seen_note = f"【警告】{args.seen_file} 讀不了，所以以前列過的論文可能重複出現"
    listed = set()                        # keys printed in this run (also de-duplicates across topics)
    skipped_seen = skipped_dup = 0

    L = [f"## 新文獻雷達：最近 {window} 天（{since_iso} 到 {until_iso}）\n"]
    L.append(cfg.get("intro") or
             "以下是 Europe PMC 依關鍵字找到的新論文候選。**只是候選，請人讀過再決定**。")
    # The AI line is filled in after the loop: it must name the model that really answered,
    # and that is unknown until the first verdict comes back. Printing "AI filtered" when
    # every provider silently failed is the failure this design guards against.
    ai_line = len(L)
    L.append("")
    triaged_by = set()
    triage_tried = 0      # a quiet month has nothing to score: not the same as a broken chain

    total_keep = 0
    failed_topics = []
    for t in cfg["topics"]:
        label = t["label"]
        llm_triage.RUBRIC = str(t.get("rubric") or "").strip() or base_rubric
        try:
            if fixture is not None:
                hits, results = fixture_search(fixture, t.get("id", ""), per_topic)
            else:
                hits, results = epmc_search(t["query"], since_iso, until_iso, per_topic)
        except (*http_retry.FETCH_ERRORS, ValueError) as e:
            failed_topics.append(label)
            L.append(f"### {label}\n- 【無法檢查】{http_retry.describe(e)}\n")
            continue

        keeps, drops = [], []
        for r in results:
            ks = paper_keys(r)
            if ks & seen:
                skipped_seen += 1
                continue
            if ks & listed:
                skipped_dup += 1
                continue
            listed |= ks
            v = None
            if do_triage:
                triage_tried += 1
                v = judge(r, label)
                if v:
                    triaged_by.add(f"{v.get('tier', '?')}/`{v.get('model', '?')}`")
                time.sleep(1)                      # gentle pacing for free-tier rate limits
            if v and v.get("verdict") == "drop":
                drops.append(line_for(r, v))
            else:
                keeps.append(line_for(r, v))
        total_keep += len(keeps)

        if keeps:
            L.append(f"### {label}：{len(keeps) + len(drops)} 篇新"
                     + (f"，保留 {len(keeps)} 篇" if do_triage else ""))
            L.extend(keeps)
            if drops:
                L.append(f"\n<details><summary>AI 篩掉 {len(drops)} 篇（點開檢查有沒有誤殺）</summary>\n")
                L.extend(drops)
                L.append("\n</details>")
            L.append("")
        elif drops:
            L.append(f"### {label}：{len(drops)} 篇新，保留 0 篇")
            L.append(f"<details><summary>AI 篩掉 {len(drops)} 篇（點開檢查有沒有誤殺）</summary>\n")
            L.extend(drops)
            L.append("\n</details>\n")
        elif results:                          # papers exist, but every one was skipped above
            L.append(f"### {label}\n- 沒有新的：最近 {window} 天有 {len(results)} 篇，"
                     "但都已經報告過，或在別的主題列過\n")
        else:
            L.append(f"### {label}\n- 最近 {window} 天沒有符合的論文\n")

        # Results come newest first, so papers beyond the page are the OLDEST of the window,
        # and next month's window will already have moved past them.
        if hits > len(results):
            L.append(f"- 【上限】只掃描了最新 {len(results)} 篇（共 {hits} 篇），較舊的 {hits - len(results)} 篇"
                     "**沒有**出現在這份報告。請調高 `max_per_topic` 後重跑，或把查詢句寫得更精確。\n")

        if t.get("manual_also"):
            L.append(f"  <sub>{t.get('note', '')}</sub>")
            for m in t["manual_also"]:
                L.append(f"  - 請另外手動查：{m}")
            L.append("")

    if not args.triage:
        L[ai_line] = "_未使用 AI 篩選：所有候選都列出。_\n"
    elif not keys_present:
        L[ai_line] = ("_已要求 AI 篩選，但沒有找到任何金鑰，所以**全部列出、沒有篩選**。"
                      "金鑰設定見 README。_\n")
    elif triaged_by:
        models = ", ".join(sorted(triaged_by))
        L[ai_line] = ((judge_header.format(models=models) if judge_header else
                       f"_AI 篩選：由 {models} 判斷。被篩掉的收合在各主題下，請抽查。_") + "\n")
    elif not triage_tried and failed_topics:
        L[ai_line] = "_已開啟 AI 篩選，但沒有抓到任何論文可以判斷。_\n"
    elif not triage_tried:
        L[ai_line] = "_已開啟 AI 篩選，但這次沒有新論文需要判斷。_\n"
    else:
        L[ai_line] = ("_【警告】已要求 AI 篩選，但**所有模型都失敗**：沒有篩掉任何論文，"
                      "下面是全部候選。請檢查金鑰是否過期、免費模型是否下架（見 README 的 D 段）。_\n")
    if rubric_missing and keys_present:
        L.insert(ai_line + 1, "_設定檔沒有 `rubric`，AI 只用最寬鬆的預設判準（只篩掉明顯離題的）。_\n")

    # A skipped search is not a quiet month. The window overlaps the next run by only a
    # couple of weeks, so older papers in a failed topic are never scanned unless re-run.
    if failed_topics:
        next_run = (until.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        blind = next_run - datetime.timedelta(days=window)
        L.insert(ai_line, f"**【不完整】{len(cfg['topics'])} 個主題裡有 {len(failed_topics)} 個無法檢查，"
                          "它們的論文不在這份報告裡。** 請重新執行一次（GitHub 的 Actions 頁 → Run workflow；"
                          f"本機就再跑一次指令）。下個月的搜尋範圍從 {blind.isoformat()} 開始，"
                          "在那之前的論文不重跑就永遠不會被掃到。\n")

    notes = []
    if skipped_seen:
        notes.append(f"{skipped_seen} 篇在更早的報告列過")
    if skipped_dup:
        notes.append(f"{skipped_dup} 篇是重複紀錄（同一篇在 Europe PMC 出現兩筆，或同時符合多個主題）")
    for n in (extra_notes or []):
        L.append(f"_{n}_\n")
    if seen_note.startswith("【警告】"):
        L.append(f"_{seen_note}。_\n")
    elif notes:
        L.append(f"_略過：{'；'.join(notes)}。_\n")

    checked = len(cfg["topics"]) - len(failed_topics)
    L.append(f"> 共 {total_keep} 篇候選待讀，檢查了 {checked} / {len(cfg['topics'])} 個主題。"
             f"查詢句寫在 `config/{config_name}`。")

    if args.seen_file:
        tmp = args.seen_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(seen | listed), f, ensure_ascii=False, indent=0)
        os.replace(tmp, args.seen_file)

    report = "\n".join(L)
    if args.out:
        with open(args.out, "a" if args.append else "w", encoding="utf-8") as f:
            if args.append:
                f.write("\n\n---\n\n")
            f.write(report)
    else:
        try:
            sys.stdout.write(report + "\n")      # a real console shows Chinese correctly
        except UnicodeEncodeError:               # a pipe with a legacy code page: send UTF-8 bytes
            sys.stdout.buffer.write((report + "\n").encode("utf-8"))
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"n_failed={len(failed_topics)}\nn_kept={total_keep}\n")
    print(f"[literature-radar] kept={total_keep} topics_checked={checked}/{len(cfg['topics'])} "
          f"window={since_iso}..{until_iso} triage={'on' if do_triage else 'off'} "
          f"skipped_seen={skipped_seen} skipped_dup={skipped_dup}", file=sys.stderr)
    return report


if __name__ == "__main__":
    main()
