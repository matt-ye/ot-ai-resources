#!/usr/bin/env python3
"""PostToolUse hook (cross-platform twin of validate_md_write.ps1): validate .md files after Write/Edit.

Standard library only. Works on Windows, macOS and Linux.

Contract (same as the PowerShell version):
  exit 0 = passed, or not applicable (not a .md file, outside the vault, internal archive folders...)
  exit 2 = problems found; the reasons are written to stderr (UTF-8) and fed back to the AI agent
  Any internal error or malformed input -> exit 0 (fail-open): a validator bug must never block your work.

Checks: BOM, final newline, invisible control characters, git conflict markers,
frontmatter closed / no duplicate keys, card schema (cards/ only, see md_schema.json),
and wikilinks that point to a file that does not exist in the vault.
"""
import json
import os
import re
import sys

SKIP_DIRS = {".obsidian", ".git", ".trash", ".claude"}
INDEX_SKIP = {".git", ".obsidian", ".trash", "node_modules"}
CTRL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
CTRL_NAMES = {
    7: "BEL (\\a)", 8: "BACKSPACE (\\b)", 11: "VERTICAL TAB (\\v)", 12: "FORM FEED (\\f)",
    27: "ESC (\\e)",
}


def emit(text):
    """Write to stderr as UTF-8 bytes, whatever the console code page is."""
    data = text.encode("utf-8", errors="replace")
    try:
        sys.stderr.buffer.write(data)
        sys.stderr.buffer.flush()
    except Exception:
        pass


def load_payload():
    raw = sys.stdin.buffer.read()
    if not raw.strip():
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        # Malformed payload (for example unescaped Windows backslashes): skip silently.
        return None


def build_indexes(root):
    md_index, any_index = set(), set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in INDEX_SKIP]
        for name in filenames:
            low = name.lower()
            any_index.add(low)
            stem, ext = os.path.splitext(low)
            if ext in (".md", ".base", ".canvas"):
                md_index.add(stem)
    return md_index, any_index


def check(fp, root):
    """Return (rel_path, issues) or None when the file is out of scope."""
    if not fp or not fp.lower().endswith(".md"):
        return None
    fp_abs = os.path.abspath(fp)
    root_abs = os.path.abspath(root)
    if not os.path.normcase(fp_abs).startswith(os.path.normcase(root_abs) + os.sep):
        return None
    if not os.path.isfile(fp_abs):
        return None
    rel = os.path.relpath(fp_abs, root_abs)
    segments = rel.split(os.sep)
    if any(seg in SKIP_DIRS for seg in segments):
        return None
    # Folders starting with "_" (archives, extracted text): basic hygiene only.
    is_archive = any(seg.startswith("_") for seg in segments)

    issues = []
    with open(fp_abs, "rb") as fh:
        data = fh.read()

    # 1. Byte-level checks
    if data.startswith(b"\xef\xbb\xbf"):
        issues.append("檔案開頭有 BOM。規則：.md 必須是 UTF-8 無 BOM。")
    text = data.decode("utf-8", errors="replace")
    if data and not text.endswith("\n"):
        issues.append("檔案結尾沒有換行。")

    # 2. Invisible control characters (typical cause: a script wrote "\b" or "\v" from a Windows path)
    hits = list(CTRL_RE.finditer(text))
    for m in hits[:5]:
        code = ord(m.group())
        name = CTRL_NAMES.get(code, "control char")
        line_no = text.count("\n", 0, m.start()) + 1
        start = max(0, m.start() - 25)
        ctx = CTRL_RE.sub("?", text[start:start + 50]).strip()
        issues.append(
            "不可見控制字元 0x%02X %s，第 %d 行，前後文：...%s...。"
            "常見原因是程式把 Windows 路徑裡的反斜線當成跳脫字元寫進檔案。" % (code, name, line_no, ctx)
        )
    if len(hits) > 5:
        issues.append("...此檔還有 %d 個控制字元。" % (len(hits) - 5))

    # 3. Conflict markers ('=======' alone is skipped: setext headings look the same)
    if re.search(r"(?m)^(<{7}( |$)|>{7}( |$))", text):
        issues.append("發現 git 衝突標記（<<<<<<< 或 >>>>>>>）。")

    lines = text.replace("\r\n", "\n").split("\n")

    # 4. Frontmatter: closed, no duplicate top-level keys
    fm_keys, fm_lines, has_fm = [], [], False
    if lines and lines[0].rstrip() == "---":
        closed = False
        for ln in lines[1:]:
            t = ln.rstrip()
            if t in ("---", "..."):
                closed = True
                break
            fm_lines.append(ln)
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", ln)
            if m:
                fm_keys.append(m.group(1))
        if not closed:
            issues.append("檔案開頭有 --- 但 frontmatter 沒有用 --- 收尾。")
        else:
            has_fm = True
            for key in sorted({k for k in fm_keys if fm_keys.count(k) > 1}):
                issues.append("frontmatter 欄位重複：'%s'。" % key)

    # 5. Card schema (cards/ only, not archive folders)
    if not is_archive and segments[0] == "cards":
        schema_path = os.path.join(root_abs, "scripts", "md_schema.json")
        if os.path.isfile(schema_path):
            with open(schema_path, "rb") as fh:
                schema = json.loads(fh.read().decode("utf-8"))
            required = schema.get("card_required_keys", [])
            ip_values = schema.get("ip_values", [])
            if not has_fm:
                issues.append("卡片沒有 frontmatter。必填欄位：" + "、".join(required) + "。")
            else:
                for key in required:
                    if key not in fm_keys:
                        issues.append("卡片 frontmatter 缺必填欄位：'%s'。" % key)
                for ln in fm_lines:
                    m = re.match(r"^ip\s*:\s*(.+)$", ln)
                    if m:
                        val = m.group(1).strip().strip('"').strip("'")
                        if val not in ip_values:
                            issues.append("卡片 'ip' 欄的值 '%s' 不在允許清單內：%s。" % (val, " | ".join(ip_values)))
                        break

    # 6. Wikilinks must resolve to a file in the vault
    if not is_archive:
        md_index, any_index = build_indexes(root_abs)
        in_fence, broken = False, set()
        for ln in lines:
            if re.match(r"^\s*(```|~~~)", ln):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in re.finditer(r"\[\[([^\[\]]+?)\]\]", ln):
                target = m.group(1).split("|")[0].split("#")[0].split("^")[0].strip()
                if not target:
                    continue
                leaf = target.split("/")[-1].strip().lower()
                if re.search(r"\.[A-Za-z0-9]{2,5}$", leaf):
                    if leaf not in any_index:
                        broken.add(target)
                elif leaf not in md_index:
                    broken.add(target)
        for b in sorted(broken):
            issues.append("斷掉的 wikilink：[[%s]]（庫內找不到同名檔案）。請修正連結；若是刻意預留的未來連結，請在檔內明說。" % b)

    return rel, issues


def main():
    try:
        payload = load_payload()
        if not payload:
            return 0
        fp = (payload.get("tool_input") or {}).get("file_path")
        root = os.environ.get("VAULT_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = check(fp, root)
        if result is None:
            return 0
        rel, issues = result
        if issues:
            emit("md-validator: %s 有 %d 個問題：\n" % (rel, len(issues)))
            for it in issues:
                emit(" - " + it + "\n")
            return 2
        return 0
    except Exception as exc:  # fail-open on purpose
        emit("md-validator internal error (fail-open, not blocking): %s\n" % exc)
        return 0


if __name__ == "__main__":
    sys.exit(main())
