"""自我檢查：確認「存檔後自動檢查」真的會擋下缺欄位的卡片，也會放行合格的卡片。

做法和 Claude Code 呼叫 hook 一樣：把 JSON 以 UTF-8 位元組送進 stdin。
為什麼要測：Windows 的 PowerShell 5.1 預設用系統碼頁讀 stdin，中文路徑變亂碼後檢查程式內部出錯，
會「悄悄放行」（exit 0），表面上看不出來。所以這裡一定要看到 exit 2 才算通過。

用法（在 starter-vault 資料夾打開終端機，兩個系統都一樣）：
    Windows：  py scripts/hook_selftest.py        （或 python scripts/hook_selftest.py）
    Mac：      python3 scripts/hook_selftest.py
Windows 會測 .ps1 與 .py 兩支檢查；Mac 只測 .py。全部通過回傳 0，否則回傳 1。
"""
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARD = ROOT / "cards" / "學術寫作" / "hook自我測試_暫存.md"

BAD = "---\ntitle: hook 自我測試\ntype: 原則\n---\n\n## 主張\n測試用，缺 themes、ip、maturity。\n"
GOOD = (
    "---\ntitle: hook 自我測試\ntype: 原則\nthemes:\n  - 測試\nmaturity: \"AI草稿\"\n"
    "ip: 自有\ncreated: 2026-01-01\ntags:\n  - ai-draft\n---\n\n## 主張\n測試用，欄位齊全。\n"
)


def runners():
    """Return (label, argv) pairs for every validator available on this machine."""
    out = []
    ps1 = ROOT / "scripts" / "validate_md_write.ps1"
    if os.name == "nt" and ps1.exists():
        out.append(("PowerShell 版 (.ps1)", ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                              "-File", str(ps1)]))
    out.append(("Python 版 (.py)", [sys.executable, str(ROOT / "scripts" / "validate_md_write.py")]))
    return out


def run_once(argv, body):
    CARD.write_text(body, encoding="utf-8")
    try:
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(CARD)}},
                             ensure_ascii=False).encode("utf-8")
        r = subprocess.run(argv, input=payload, capture_output=True)
    finally:
        CARD.unlink()
    return r.returncode, r.stderr.decode("utf-8", errors="replace").strip()


def main():
    failed = False
    for label, argv in runners():
        code, msg = run_once(argv, BAD)
        if code != 2:
            print(f"FAIL [{label}]：缺欄位的卡片應該被擋（exit 2），實際 exit {code}。\n{msg}")
            failed = True
            continue
        if str(CARD.relative_to(ROOT)) not in msg:
            print(f"FAIL [{label}]：有擋下（exit 2），但訊息裡的中文路徑不是 UTF-8，畫面會變亂碼。\n{msg}")
            failed = True
            continue
        code, msg = run_once(argv, GOOD)
        if code != 0:
            print(f"FAIL [{label}]：欄位齊全的卡片應該放行（exit 0），實際 exit {code}。\n{msg}")
            failed = True
            continue
        print(f"PASS [{label}]：缺欄位被擋（exit 2、中文路徑正常顯示），合格卡放行（exit 0）。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
