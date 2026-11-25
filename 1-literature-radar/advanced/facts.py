#!/usr/bin/env python3
"""Ask the AI to read an abstract into FACTS (not a judgement). Reuses the provider rotation
and fail-open behaviour of scripts/llm_triage.py.

The list of layers is built from YOUR ledger, so changing the ledger changes what the AI is
asked to look for. The field names (estimate, layer, measure, population, method, ...) are
generic and normally stay as they are.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import llm_triage  # noqa: E402


def build_rubric(ledger):
    """The instruction sent to the AI, with the layers of this ledger listed in it."""
    layer_lines = "; ".join(f"{k} = {v['description']}" for k, v in ledger["layers"].items())
    measures = sorted({m for v in ledger["layers"].values() for m in v["measures"]} | {"other"})
    return (
        "You read a scientific abstract and report FACTS about it. Do not judge novelty. Fields:\n"
        "estimate: true if it reports a population-level number (prevalence, incidence, risk ratio, "
        "share, projection, exposure level), else false.\n"
        f"layer: which figure the number is about. One of: {layer_lines}; or none.\n"
        f"measure: one of {' | '.join(measures)}.\n"
        "population: general (community or national population) or subgroup (patients, one "
        "occupation, a clinic sample, people already diagnosed).\n"
        "method: survey | administrative (insurance, claims or registry diagnoses) | modelled | "
        "meta_analysis | other.\n"
        "representative: true if the sample stands for a whole country or region; false for local "
        "cohorts, single sites or convenience samples.\n"
        'countries: ISO 3166-1 alpha-2 codes of the countries covered; ["GLOBAL"] for global or '
        "multi-region estimates.\n"
        "data_end_year: the last year the DATA were collected (not the publication year); null if "
        "not stated.\n"
        'dataset: short name of the underlying survey or database, or "".\n'
        "reason: at most 12 characters, in Traditional Chinese.\n"
        'Reply with JSON only: {"estimate":..,"layer":..,"measure":..,"population":..,"method":..,'
        '"representative":..,"countries":[..],"data_end_year":..,"dataset":..,"reason":..}.'
    )


def parse_facts(content):
    """Read the facts object out of a model reply, or None if it is unusable."""
    if content is None:
        return None
    o = content if isinstance(content, dict) else None
    if o is None:
        m = re.search(r"\{[\s\S]*\}", str(content))
        try:
            o = json.loads(m.group(0)) if m else None
        except ValueError:
            o = None
    if not isinstance(o, dict) or "estimate" not in o or "layer" not in o:
        return None
    est = o.get("estimate")
    o["estimate"] = est is True or str(est).lower() == "true"
    o["layer"] = str(o.get("layer") or "").strip().lower()
    if not isinstance(o.get("countries"), list):
        o["countries"] = []
    return o


def extract(title, abstract, ledger, hint="", env=None):
    """Facts about one paper, or None if every provider failed (the caller then keeps the paper)."""
    text = (abstract or "(none)") + (f"\n\n(Found by a search for: {hint})" if hint else "")
    return llm_triage.triage(title, text, env=env, system=build_rubric(ledger),
                             parse=parse_facts, heavy=True)
