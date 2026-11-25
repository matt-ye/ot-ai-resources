#!/usr/bin/env python3
"""Optional AI keep/drop filter for the literature radar, with three free providers in turn.

Order: NVIDIA NIM -> Groq -> Cloudflare Workers AI -> (give up, keep everything).
Standard library only, so GitHub Actions needs no pip install.

Fail-open by design: with no keys, or when every provider fails, `triage()` returns
None and the caller keeps the paper. The radar therefore always produces a report;
the AI only sorts it. The caller is responsible for SAYING when that happened.

Model ids are NOT written into this file. Providers retire models without notice.
Each provider is asked what it serves today (`list_models`), we pick by name
patterns (`_PREFER`), and the verdict carries the model that really answered so the
report can print it. `_FALLBACK` holds last-resort ids that may also be retired.

Environment variables (all optional; one provider is enough):
  NVIDIA_API_KEY                  tier 1 (NIM)         + optional NIM_MODEL
  GROQ_API_KEY                    tier 2 (Groq)        + optional GROQ_MODEL
  CF_ACCOUNT_ID + CF_API_TOKEN    tier 3 (Cloudflare)  + optional CF_AI_MODEL
A *_MODEL variable pins one model id and skips discovery. Use it only to reproduce
an old run.
"""
import json
import os
import re
import urllib.request

import http_retry

# A provider failing in any of these ways is skipped in favour of the next one.
PROVIDER_ERRORS = (*http_retry.FETCH_ERRORS, ValueError, KeyError)

TIMEOUT = 40
UA = "literature-radar-triage/1.0"   # some providers reject urllib's default User-Agent

# Token budget. Most current models "think" before answering and the thinking uses
# this allowance first, so a tiny budget returns an empty answer. It is a ceiling,
# not a bill. HEAVY is for tasks that write many fields (see advanced/).
MAX_TOKENS = 400
HEAVY_MAX_TOKENS = 1200

# Used when the config file has no `rubric`. Deliberately loose.
DEFAULT_RUBRIC = (
    "You triage scientific papers for a literature radar. KEEP a paper if it plausibly "
    "belongs to the search topic named below. DROP it only if it is clearly off topic."
)
RUBRIC = DEFAULT_RUBRIC   # literature_watch.py replaces this with the config's `rubric`

# Appended to every rubric, so rubric authors only write the criteria.
OUTPUT_SPEC = (
    '\n\nReply with JSON only, nothing else: {"verdict":"keep" or "drop",'
    '"reason":"<a short phrase of at most 12 characters, in Traditional Chinese>"}.'
)


def _messages(title, abstract, system=None):
    return [
        {"role": "system", "content": system or (RUBRIC + OUTPUT_SPEC)},
        {"role": "user", "content": f"TITLE: {title}\n\nABSTRACT: {abstract or '(none)'}"},
    ]


def _post(url, headers, payload):
    req = urllib.request.Request(
        url, json.dumps(payload).encode("utf-8"),
        {**headers, "Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _get(url, headers):
    req = urllib.request.Request(url, headers={**headers, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


# ---- model discovery ------------------------------------------------------
# One list call per provider per process: triage() runs once per paper.
_OVERRIDE_VAR = {"nim": "NIM_MODEL", "groq": "GROQ_MODEL", "cf": "CF_AI_MODEL"}
_model_cache = {}

# Name patterns, not ids: a pattern survives a version bump, an id does not.
# Ordered best-first. Add your own pattern here if a provider changes its line-up.
_PREFER = {
    "groq": [r"gpt-oss-20b$", r"gpt-oss-120b$"],
    "nim": [r"^openai/gpt-oss-20b$", r"^google/gemma-\d+-\d+b-it$", r"^nvidia/nemotron-mini-\d+b-instruct$"],
    "cf": [r"llama.*3\.3.*70b", r"llama.*4", r"qwen.*(32|72)b"],
}
# Last resort when discovery fails or matches nothing. These can be retired too.
_FALLBACK = {
    "groq": ["openai/gpt-oss-20b", "openai/gpt-oss-120b"],
    "nim": ["openai/gpt-oss-20b", "google/gemma-4-31b-it"],
    "cf": ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/meta/llama-3.1-8b-instruct"],
}
# NIM and Groq list chat models together with speech, embedding, vision and safety
# models in one flat list, so ids[0] is not safe to use. Exclude those by name.
_EXCLUDE = (r"whisper|orpheus|embed|bge-|rerank|guard|safeguard|moderation|content-safety"
            r"|translate|vision|-vl$|omni|ocr|kosmos|deplot|diffusion|compound")


def list_models(provider, env):
    """Ids the provider serves right now, in the provider's own order."""
    if provider in _model_cache:
        return _model_cache[provider]
    if provider == "nim":
        d = _get("https://integrate.api.nvidia.com/v1/models",
                 {"Authorization": f"Bearer {env.get('NVIDIA_API_KEY')}"})
        ids = [m.get("id") for m in d.get("data") or []]
    elif provider == "groq":
        d = _get("https://api.groq.com/openai/v1/models",
                 {"Authorization": f"Bearer {env.get('GROQ_API_KEY')}"})
        ids = [m.get("id") for m in d.get("data") or []]
    else:  # cf
        d = _get(f"https://api.cloudflare.com/client/v4/accounts/{env.get('CF_ACCOUNT_ID')}"
                 "/ai/models/search?task=Text%20Generation&hide_experimental=true&per_page=100",
                 {"Authorization": f"Bearer {env.get('CF_API_TOKEN')}"})
        ids = [m.get("name") for m in d.get("result") or []]
    ids = [i for i in ids if isinstance(i, str)]
    _model_cache[provider] = ids
    return ids


def choose_model(provider, ids):
    """Ordered list of ids worth trying for keep/drop triage (may be empty).

    A wrong pick does not raise; it quietly returns bad verdicts, and a paper
    dropped by a bad model is never looked at again. So unknown models on NIM and
    Groq are NOT used: with no match, the tier is skipped and the report says so.
    Cloudflare's list is already limited to text generation, so there one unknown
    model is better than none.
    """
    usable = [i for i in ids if not re.search(_EXCLUDE, i, re.I)]
    ranked = []
    for pat in _PREFER.get(provider, []):
        for i in usable:
            if re.search(pat, i, re.I) and i not in ranked:
                ranked.append(i)
    if provider == "cf" and usable and not ranked:
        ranked = usable[:1]
    return ranked


def candidates(provider, env):
    """Ordered ids to try for one provider. 'Listed' does not always mean 'served',
    so the caller must be able to fall through to the next id."""
    pinned = env.get(_OVERRIDE_VAR[provider])
    if pinned:
        return [pinned]
    try:
        ranked = choose_model(provider, list_models(provider, env))
    except PROVIDER_ERRORS:
        ranked = []          # discovery is itself a network call, and it does fail
    return ranked + [m for m in _FALLBACK.get(provider, []) if m not in ranked]


def _stamp(verdict, model, how):
    if verdict:
        verdict["model"], verdict["how"] = model, how
    return verdict


# ---- providers: return a verdict dict, or None if not configured -----------
def _openai_chat(provider, url, key, title, abstract, env, system=None, parse=None, heavy=False):
    """Try each candidate model until one returns a parsable verdict."""
    last = None
    for model in candidates(provider, env):
        payload = {"model": model, "messages": _messages(title, abstract, system),
                   "temperature": 0.1,
                   "max_tokens": HEAVY_MAX_TOKENS if heavy else MAX_TOKENS,
                   "response_format": {"type": "json_object"}}
        if heavy and "gpt-oss" in model:
            payload["reasoning_effort"] = "low"
        try:
            d = _post(url, {"Authorization": f"Bearer {key}"}, payload)
            v = (parse or _parse)(d["choices"][0]["message"]["content"])
            if v:
                return _stamp(v, model, f"{provider} candidate")
            last = ValueError(f"{provider}: {model} returned no usable verdict")
        except PROVIDER_ERRORS as e:
            last = e
    if last:
        raise last
    return None


def _nim(title, abstract, env, system=None, parse=None, heavy=False):
    key = env.get("NVIDIA_API_KEY")
    if not key:
        return None
    return _openai_chat("nim", "https://integrate.api.nvidia.com/v1/chat/completions",
                        key, title, abstract, env, system, parse, heavy)


def _groq(title, abstract, env, system=None, parse=None, heavy=False):
    key = env.get("GROQ_API_KEY")
    if not key:
        return None
    return _openai_chat("groq", "https://api.groq.com/openai/v1/chat/completions",
                        key, title, abstract, env, system, parse, heavy)


def _cloudflare(title, abstract, env, system=None, parse=None, heavy=False):
    acct, tok = env.get("CF_ACCOUNT_ID"), env.get("CF_API_TOKEN")
    if not (acct and tok):
        return None
    last = None
    for model in candidates("cf", env):
        try:
            d = _post(f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{model}",
                      {"Authorization": f"Bearer {tok}"},
                      {"messages": _messages(title, abstract, system),
                       "max_tokens": HEAVY_MAX_TOKENS if heavy else MAX_TOKENS})
            v = (parse or _parse)(d.get("result", {}).get("response"))
            if v:
                return _stamp(v, model, "cf candidate")
            last = ValueError(f"cf: {model} returned no usable verdict")
        except PROVIDER_ERRORS as e:
            last = e
    if last:
        raise last
    return None


TIERS = [_nim, _groq, _cloudflare]


def available(env=None):
    """True if at least one provider has its key(s) set."""
    e = env if env is not None else os.environ
    return bool(e.get("NVIDIA_API_KEY") or e.get("GROQ_API_KEY")
                or (e.get("CF_ACCOUNT_ID") and e.get("CF_API_TOKEN")))


def triage(title, abstract="", env=None, system=None, parse=None, heavy=False):
    """Return {'verdict','reason','tier','model','how'} from the first working provider, or None.

    `system` and `parse` let advanced/ reuse the provider rotation for a different task."""
    e = env if env is not None else os.environ
    for fn in TIERS:
        try:
            v = fn(title, abstract, e, system, parse, heavy)
            if v:
                v["tier"] = fn.__name__.lstrip("_")
                return v
        except PROVIDER_ERRORS:
            continue
    return None


def _parse(content):
    """Read {"verdict": "keep"|"drop", "reason": ...} out of a model reply, or None."""
    if content is None:
        return None
    if isinstance(content, dict):
        o = content
    else:
        m = re.search(r"\{[\s\S]*\}", str(content))
        try:
            o = json.loads(m.group(0)) if m else None
        except ValueError:
            o = None
    if not isinstance(o, dict):
        return None
    verdict = str(o.get("verdict", "")).strip().lower()
    if verdict not in ("keep", "drop"):
        return None          # anything else is not a verdict; try the next model
    return {"verdict": verdict, "reason": str(o.get("reason", "")).strip()}
