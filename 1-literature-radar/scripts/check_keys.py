#!/usr/bin/env python3
"""Check each AI provider's key separately: does it answer, and with which model?

The radar tries NVIDIA NIM -> Groq -> Cloudflare and stops at the first success, so a
broken backup key stays hidden until the day the first provider fails. This script
calls EACH configured provider once with a made-up paper title and reports:

  能用    the provider answered; shows the model that really answered
  失敗    the key is set but the call failed; shows the error type (never the key)
  沒設定  no key for this provider (not an error: one provider is enough)

Exit code: 1 if any configured provider failed, or if none is configured; else 0.
Keys come from the environment, or from a .env file (same rules as literature_watch.py).
Nothing real is sent: the title below is fictional. Standard library only. License: MIT.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import llm_triage  # noqa: E402
from literature_watch import DEFAULT_ENV_FILE, load_dotenv  # noqa: E402

# A made-up title: no real paper, no personal data.
TEST_TITLE = "A fictional randomized trial of task practice for arm function after stroke"

PROVIDERS = [  # (label, function, the variables it needs)
    ("NVIDIA NIM", llm_triage._nim, ("NVIDIA_API_KEY",)),
    ("Groq", llm_triage._groq, ("GROQ_API_KEY",)),
    ("Cloudflare Workers AI", llm_triage._cloudflare, ("CF_ACCOUNT_ID", "CF_API_TOKEN")),
]
SECRET_VARS = ("NVIDIA_API_KEY", "GROQ_API_KEY", "CF_ACCOUNT_ID", "CF_API_TOKEN")


def redact(text, env):
    """Remove any secret value that might appear inside an error message."""
    text = str(text)
    for var in SECRET_VARS:
        val = env.get(var)
        if val and len(val) >= 4:
            text = text.replace(val, f"<{var}>")
    return text


def check_one(label, fn, needed, env):
    """Return a dict: provider, status (能用/失敗/沒設定), model, detail."""
    missing = [v for v in needed if not env.get(v)]
    if len(missing) == len(needed):
        return {"provider": label, "status": "沒設定", "model": "", "detail": "沒有設定這一家的金鑰"}
    if missing:
        return {"provider": label, "status": "失敗", "model": "",
                "detail": "只設了一半，還缺 " + "、".join(missing)}
    try:
        v = fn(TEST_TITLE, "", env)
    except llm_triage.PROVIDER_ERRORS as e:
        return {"provider": label, "status": "失敗", "model": "",
                "detail": redact(f"{type(e).__name__}: {e}", env)}
    if not v:
        return {"provider": label, "status": "失敗", "model": "", "detail": "沒有回傳可用的判斷"}
    return {"provider": label, "status": "能用", "model": v.get("model", ""),
            "detail": f"判斷：{v.get('verdict')}"}


def to_markdown(results):
    lines = ["## 金鑰檢查", "", "| 服務 | 結果 | 實際回答的模型 | 說明 |", "|---|---|---|---|"]
    for r in results:
        mark = {"能用": "✅ 能用", "失敗": "❌ 失敗", "沒設定": "— 沒設定"}[r["status"]]
        model = f"`{r['model']}`" if r["model"] else ""
        lines.append(f"| {r['provider']} | {mark} | {model} | {r['detail']} |")
    ok = sum(r["status"] == "能用" for r in results)
    bad = sum(r["status"] == "失敗" for r in results)
    lines += ["", f"能用 {ok} 家、失敗 {bad} 家。送出的題目是虛構的，不含任何真實資料；金鑰不會出現在這裡。"]
    return "\n".join(lines) + "\n"


def exit_code(results):
    if any(r["status"] == "失敗" for r in results):
        return 1
    if not any(r["status"] == "能用" for r in results):
        return 1          # nothing configured: the radar would list everything unfiltered
    return 0


def main(argv=None, env=None):
    ap = argparse.ArgumentParser(description="三家 AI 服務各自測一次，確認金鑰能用。")
    ap.add_argument("--env-file", default=DEFAULT_ENV_FILE,
                    help="存放金鑰的 .env 檔（預設：專案根目錄的 .env；檔案不存在就略過）")
    args = ap.parse_args(argv)
    if env is None:
        load_dotenv(args.env_file)
        env = os.environ
    results = [check_one(label, fn, needed, env) for label, fn, needed in PROVIDERS]
    md = to_markdown(results)
    print(md)
    summary = env.get("GITHUB_STEP_SUMMARY")   # GitHub shows this on the run page
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(md)
    return exit_code(results)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
