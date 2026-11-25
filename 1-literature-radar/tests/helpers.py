"""Shared helpers for the offline tests (no network is ever used)."""
import contextlib
import io
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import literature_watch as lw  # noqa: E402
import llm_triage  # noqa: E402

OT_CONFIG = os.path.join(ROOT, "config", "literature-watch.ot.json")
FIXTURE = os.path.join(ROOT, "examples", "mock_epmc_response.json")

KEY_VARS = ("NVIDIA_API_KEY", "GROQ_API_KEY", "CF_ACCOUNT_ID", "CF_API_TOKEN",
            "GITHUB_OUTPUT", "GITHUB_REPOSITORY", "GH_TOKEN", "GITHUB_TOKEN")


def write_json(directory, name, obj):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def run_main(argv, env=None, **kw):
    """Run lw.main with a clean environment; return (report_text, stderr_text)."""
    clean = {k: v for k, v in os.environ.items() if k not in KEY_VARS}
    clean.update(env or {})
    err = io.StringIO()
    old = os.environ.copy()
    os.environ.clear()
    os.environ.update(clean)
    try:
        with contextlib.redirect_stderr(err):
            report = lw.main(argv + ["--env-file", os.path.join(ROOT, "no-such.env"), "--out", os.path.join(tempfile.mkdtemp(), "r.md")], **kw)
    finally:
        os.environ.clear()
        os.environ.update(old)
    return report, err.getvalue()
