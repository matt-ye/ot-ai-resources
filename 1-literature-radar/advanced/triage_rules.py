#!/usr/bin/env python3
"""Rules that compare a paper's FACTS with a ledger of what you already use. No network, no AI.

Idea: asking an AI "is this paper new for me?" does not work, because the AI does not know
what you already have, and it will keep papers that report older or identical data. So the
work is split:
  1. The AI only READS the abstract and reports facts (see facts.py).
  2. This file compares the facts with YOUR ledger and decides, with a written reason.

Updating the ledger therefore updates the judgement, and every verdict shows the comparison
that produced it.

!! The ledger in advanced/ledger.dementia-example.json is a DEMENTIA-RESEARCH EXAMPLE
!! (layers such as dementia prevalence, MCI, PM2.5). Replace the layers with your own
!! (see advanced/README.md). The rules below do not know anything about dementia: layers,
!! kinds of numbers and special rules all come from the ledger file.

Standard library only.
"""
import datetime
import json
import re

UPDATE, OLDER, NOT_ESTIMATE = "update", "older", "not_estimate"
_STOP = {"national", "survey", "study", "data", "database", "health", "global", "the", "and",
         "of", "cohort", "estimates", "estimate", "burden", "disease", "registry", "insurance"}


def load_ledger(path):
    """Read a ledger file. Raises OSError / ValueError / KeyError if it is unusable.

    Format (see ledger.dementia-example.json):
      layers    : list of {key, description, measures: [...], rules: {...}}
      defaults  : {layer key: {"source": "...", "year": "2019-2023"}}   what you use by default
      overrides : {"KR": {layer key: {"source": ..., "year": ...}}}      per-country exceptions
    """
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    layers = {}
    for item in d["layers"]:
        layers[item["key"]] = {
            "description": item.get("description", item["key"]),
            "measures": set(item["measures"]),
            "rules": item.get("rules") or {},
        }
    if not layers:
        raise ValueError("ledger has no layers")
    return {"layers": layers, "defaults": d.get("defaults", {}), "overrides": d.get("overrides", {})}


def end_year(text, today=None):
    """Last year a source's DATA covers: '2015-18' -> 2018, '2019-2023' -> 2023, '2022' -> 2022.
    A range that runs past today is a projection ('2020-45'): its data stops at the start."""
    if text is None:
        return None
    years = []
    for m in re.finditer(r"(19|20)\d\d(?:\s*[–\-/~]\s*(\d{2,4}))?", str(text)):
        y0 = int(m.group(0)[:4])
        years.append(y0)
        if m.group(2):
            tail = m.group(2)
            years.append(int(tail) if len(tail) == 4 else (y0 // 100) * 100 + int(tail))
    if not years:
        return None
    this_year = (today or datetime.date.today()).year
    past = [y for y in years if y <= this_year]
    return max(past) if past else min(years)


def in_use(ledger, layer, iso2):
    """(source, data year) you use for this layer and country: the country entry first,
    because that is the finer figure a new paper would have to beat."""
    o = (ledger["overrides"].get(iso2) or {}).get(layer) if iso2 else None
    d = o or ledger["defaults"].get(layer) or {}
    src, yr = d.get("source"), d.get("year")
    if src and src != "-" and end_year(yr):
        return src, end_year(yr)
    return None, None


def _tokens(name):
    return {w for w in re.findall(r"[a-z0-9]{3,}", (name or "").lower()) if w not in _STOP}


def same_dataset(dataset, source):
    """True when the paper's underlying dataset is the one you already use (for example both
    are the same survey). Overlap of distinctive words only; a miss falls back to the year test."""
    a, b = _tokens(dataset), _tokens(source)
    return bool(a and b and a & b)


def decide(facts, ledger, today=None):
    """facts come from facts.extract():
         estimate: bool   reports a population-level number at all
         layer: a key from the ledger, or "none"
         measure: the kind of number (must be one of the layer's `measures`)
         population: general | subgroup
         method: survey | administrative | modelled | meta_analysis | other
         representative: bool   the sample stands for a whole country or region
         countries: ["KR", ...] ISO-2 codes, or ["GLOBAL"] / [] for global or regional
         data_end_year: int | null   last year the data were COLLECTED (not published)
         dataset: short name of the underlying survey or database
       returns (bucket, reason); bucket is update | older | not_estimate

    Special rules per layer, all optional, written in the ledger under layers[].rules:
         need_representative (default true)  a local sample cannot replace a national figure
         exclude_methods: ["administrative"] methods that cannot feed this layer
         require_method: "meta_analysis"     only this method can feed this layer
    """
    layers = ledger["layers"]
    layer = facts.get("layer")
    if not facts.get("estimate") or layer not in layers:
        return NOT_ESTIMATE, "no population estimate for any of your layers"
    spec = layers[layer]
    rules = spec["rules"]
    if facts.get("population") == "subgroup":
        return NOT_ESTIMATE, "subgroup, not the general population"
    measure = facts.get("measure")
    if measure and measure not in spec["measures"]:
        return NOT_ESTIMATE, f"{measure}, layer needs {'/'.join(sorted(spec['measures']))}"
    rep = facts.get("representative")
    if rules.get("need_representative", True) and (rep is False or str(rep).lower() == "false"):
        return NOT_ESTIMATE, "local sample, not representative"
    if facts.get("method") in (rules.get("exclude_methods") or []):
        return NOT_ESTIMATE, f"{facts.get('method')} data cannot feed this layer"
    need = rules.get("require_method")
    if need and facts.get("method") != need:
        return NOT_ESTIMATE, f"layer needs {need}"

    year = facts.get("data_end_year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    countries = [c for c in (facts.get("countries") or []) if isinstance(c, str) and len(c) == 2
                 and c.upper() != "GL"] or [None]          # None -> the layer's global default

    best = None   # the most favourable comparison across the paper's countries
    for c in countries:
        c = c.upper() if c else None
        src, used = in_use(ledger, layer, c)
        where = c or "global"
        if src is None:
            return UPDATE, f"{where}: no {layer} source in the ledger yet"
        if same_dataset(facts.get("dataset"), src) and (year is None or year <= used):
            cand = (OLDER, f"same data as {where} in use: {src} ({used})")
        elif year is None:
            cand = (UPDATE, f"data year unknown; {where} uses {src} ({used})")
        elif year > used:
            cand = (UPDATE, f"data {year} > {where} in use {src} ({used})")
        else:
            cand = (OLDER, f"data {year} <= {where} in use {src} ({used})")
        if best is None or (cand[0] == UPDATE and best[0] != UPDATE):
            best = cand
    return best
