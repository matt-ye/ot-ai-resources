"""Question frameworks for the radar's topic forms (one GitHub issue form per framework).

Each framework says three things:
  fields    form heading -> key (headings must match the ISSUE_TEMPLATE file word for word;
            a test checks this)
  search    which elements go into the Europe PMC query (to FIND candidates)
  screen    which elements go only into the topic's keep/drop rubric (to FILTER them)

Which element goes where follows the evidence-synthesis guidance summarised in
README section C0 (e.g. Cochrane Handbook 4.4.2: comparison and outcome are usually not
searched; Leeflang 2008: no study-design filter for diagnostic accuracy; COSMIN: all
four elements are searched). The LLM only translates the form into search syntax; the
program validates the result and a person approves it.
License: MIT.
"""

COMMON = {
    "主題名稱": "label",
    "不要收的（選填）": "exclude",
    "要取代的現有主題代號（選填）": "replace_id",
}

FRAMEWORKS = {
    "PICO": {
        "name": "介入效果（PICO）",
        "fields": {"P 對象（Population）": "p", "I 介入（Intervention）": "i",
                   "C 對照（Comparison，選填）": "c", "O 結果指標（Outcome，選填但建議填）": "o", "研究設計": "design"},
        "required": ["label", "p", "i"],
        "search": "P 與 I", "screen": "C、O、研究設計、排除",
        "query_rule": """built ONLY from P (population) and I (intervention).
- If the form asks for randomized trials or reviews, you MAY add one plain group such as
  (randomized OR randomised OR "systematic review" OR "meta-analysis") without a field code.
- Do NOT put outcomes, comparisons or exclusions in the query.""",
        "rubric_rule": """Start with "KEEP" and name, in this order: the study designs, the population,
the intervention, the comparison if given, and EVERY outcome measure listed under O
(the query cannot filter by outcome, so the rubric is the only place outcomes are
checked). Then "DROP": study protocols without results, case reports, studies whose
population or body part differs from P, and everything the form says to exclude.""",
        "mesh_of": "P and I",
    },
    "CoCoPop": {
        "name": "盛行率／發生率（CoCoPop）",
        "fields": {"Co 病況（Condition）": "condition", "Pop 族群（Population）": "population",
                   "Co 情境（Context：國家、場域、年代，選填）": "context", "要找的指標": "measure"},
        "required": ["label", "condition", "population"],
        "search": "病況與族群（＋流行病學詞）", "screen": "情境、指標、排除",
        "query_rule": """built from Condition and Population, plus ONE block of epidemiology words, e.g.
  TITLE:(prevalence OR incidence OR epidemiology OR epidemiological OR "cross-sectional").
- Do NOT put the Context (country, setting, years) in the query unless the form says it must
  appear in the title; context is checked by the rubric.
- Do NOT add intervention or treatment words.""",
        "rubric_rule": """Start with "KEEP": population-based, cross-sectional or cohort studies, and systematic
reviews or meta-analyses of such studies, that REPORT AN ESTIMATE of the prevalence and/or
incidence (as asked under 要找的指標) of the Condition in the Population, within the Context if
one is given (name the countries/settings/years). Then "DROP": intervention trials, studies
that report only risk factors, diagnostic accuracy or treatment outcomes without a
prevalence/incidence estimate, study protocols, case reports, and everything the form says
to exclude.""",
        "mesh_of": "the Condition and the Population",
    },
    "PECO": {
        "name": "暴露與風險（PEO／PECO）",
        "fields": {"P 族群（Population）": "p", "E 暴露或危險因子（Exposure）": "e",
                   "C 比較組（Comparison，選填；填了就是 PECO）": "c", "O 結果（Outcome）": "o", "研究設計": "design"},
        "required": ["label", "p", "e", "o"],
        "search": "P 與 E（O 是明確疾病或事件時也可放）", "screen": "C、O、研究設計、排除",
        "query_rule": """built from P (population) and E (exposure).
- If O is a specific disease or event (e.g. dementia, falls, hip fracture) you MAY add it as a
  third block, but search it with ABSTRACT:(...) (three TITLE: blocks find almost nothing);
  if O is broad (e.g. "health", "function") leave it out.
- Do NOT put the comparison in the query.""",
        "rubric_rule": """Start with "KEEP": observational studies of the designs the form asks for (cohort,
case-control, analytical cross-sectional) and systematic reviews or meta-analyses of them,
that examine the ASSOCIATION between the Exposure (compared with C if given) and the Outcome
in the Population. Name E, C, O and P explicitly. Then "DROP": intervention trials (unless
the form allows them), studies that do not analyse the exposure-outcome association, study
protocols, case reports, and everything the form says to exclude.""",
        "mesh_of": "P and E",
    },
    "PIRD": {
        "name": "診斷準確度（PIRD）",
        "fields": {"P 族群（Population）": "p", "I 指標檢測（Index test：要評估的工具或檢查）": "i",
                   "R 參考檢測（Reference test：黃金標準，選填但建議填）": "r", "D 目標診斷（Diagnosis of interest）": "d"},
        "required": ["label", "i", "d"],
        "search": "指標檢測與目標診斷", "screen": "參考檢測、族群、排除（不加研究設計濾鏡）",
        "query_rule": """built from I (index test) and D (target diagnosis). Add P only if it is a specific
clinical group AND the query would otherwise be very broad.
- Do NOT add any study-design or accuracy filter words (diagnostic accuracy search filters
  are not recommended; Leeflang 2008). Do NOT put the reference test in the query.""",
        "rubric_rule": """Start with "KEEP": diagnostic test accuracy studies, and systematic reviews or
meta-analyses of them, that evaluate the Index test for detecting the target Diagnosis in the
Population AND report accuracy measures (sensitivity, specificity, AUC, likelihood ratios or
predictive values) against a reference standard (name R if given). Then "DROP": studies that
use the test only as an outcome measure, studies without a reference standard comparison,
prevalence-only studies, study protocols, case reports, and everything the form says to
exclude.""",
        "mesh_of": "I and D",
    },
    "COSMIN": {
        "name": "評估工具的測量特性（COSMIN）",
        "fields": {"構念（Construct：要測的能力或狀態）": "construct", "族群（Population）": "population",
                   "工具類型（Type of instrument）": "instrument", "要看的測量特性": "properties"},
        "required": ["label", "construct", "population", "instrument"],
        "search": "構念、族群、工具類型，加測量特性詞（四項都要）", "screen": "測量特性、排除",
        "query_rule": """built from ALL FOUR elements (COSMIN asks for all four in the search):
  construct, population, type of instrument, and a block of measurement-property words such as
  (reliability OR validity OR validation OR psychometric OR "measurement properties" OR responsiveness).
- Put construct and population in TITLE:. Put the instrument type and the measurement-property
  block in ABSTRACT:.
- Write the construct as short core words and synonyms, not the whole phrase from the form
  (e.g. "upper limb function" -> ("upper limb" OR "upper extremity" OR arm OR hand)).
- For the instrument type use broad words such as (scale OR test OR assessment OR questionnaire
  OR instrument OR measure) unless the form names a specific instrument.""",
        "rubric_rule": """Start with "KEEP": studies whose aim is to evaluate measurement properties (as listed
under 要看的測量特性, e.g. reliability, validity, responsiveness, measurement error) of
instruments of the given type that measure the Construct in the Population, and systematic
reviews of such studies. Name the construct, population and instrument type. Then "DROP":
studies that only USE an instrument as an outcome measure, instrument descriptions without an
evaluation, study protocols, and everything the form says to exclude.""",
        "mesh_of": "the construct and the population",
    },
    "PICo": {
        "name": "經驗與感受（PICo）",
        "fields": {"P 族群（Population）": "p", "I 關注的現象（phenomenon of Interest）": "i",
                   "Co 情境（Context，選填）": "context", "研究類型": "design"},
        "required": ["label", "p", "i"],
        "search": "族群與關注的現象", "screen": "情境、研究類型、排除",
        "query_rule": """built from P (population) and I (phenomenon of interest).
- If the form asks for qualitative or mixed-methods research, you MAY add ONE block such as
  ABSTRACT:(qualitative OR interview OR interviews OR "focus group" OR "lived experience" OR phenomenological).
- Do NOT put the context in the query; the rubric checks it.""",
        "rubric_rule": """Start with "KEEP": qualitative or mixed-methods studies (as the form asks), and
qualitative evidence syntheses, that explore the phenomenon of interest (name it) as
experienced by the Population, in the Context if given. Then "DROP": purely quantitative
studies (unless the form allows them), studies of a different population, study protocols,
and everything the form says to exclude.""",
        "mesh_of": "P and I",
    },
}


def all_fields(fw):
    f = dict(COMMON)
    f.update(FRAMEWORKS[fw]["fields"])
    return f


def detect(headings):
    """Which framework a submitted form belongs to, judged by its headings (the issue title
    can be edited by anyone with access, the headings come from the form)."""
    best, score = "PICO", 0
    for fw, spec in FRAMEWORKS.items():
        s = sum(1 for h in spec["fields"] if h in headings)
        if s > score:
            best, score = fw, s
    return best
