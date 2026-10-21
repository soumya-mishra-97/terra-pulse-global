"""Supervisor planning: turn a question into a validated execution plan.

Rules-based planning always runs. When Claude is configured it proposes a plan as JSON, which is
accepted only if it validates against the allowed intents/metrics and resolves to known countries;
otherwise the rules plan is used. Either way the plan only selects deterministic tools.
"""

from __future__ import annotations

import json
import re

from app.agents.state import Plan
from app.domain.models import Country

INTENTS = ("world", "country", "compare", "ranking", "methodology", "out_of_scope")
METRIC_KEYWORDS: list[tuple[str, list[str]]] = [
    (r"fertility|tfr|children per woman|births per woman", ["fertility_rate"]),
    (r"life expectancy|lifespan|longevity", ["life_expectancy_years"]),
    (r"birth rate|births", ["birth_rate_per_1000"]),
    (r"death rate|deaths|mortality", ["death_rate_per_1000"]),
    (r"\bage\b|ageing|aging|elderly|older|young|youth|dependency|65", ["age_0_14_pct", "age_15_64_pct", "age_65_plus_pct"]),
    (r"urban|rural|cities|urbani[sz]ation", ["urban_pct", "rural_pct"]),
    (r"density|dense|land area|crowded", ["density_per_km2", "land_area_km2"]),
    (r"migration|migrants|immigra|emigra", ["net_migration"]),
    (r"grow|growth|increase|decline|shrink|change", ["population_growth_pct"]),
]
# Generic words such as "world", "country" or "data" are deliberately absent: "Who will win the world cup?"
# must be refused rather than answered with population figures.
DOMAIN_WORDS = re.compile(
    r"popul|people|demograph|grow|birth|death|fertil|life expect|\bages?\b|ageing|aging|elder|urban|rural|densit|"
    r"migra|census|estimat|projection|counter|dataset|data source|uncertain|inhabitant|resident|mortality|"
    r"methodolog|\bwdi\b|world bank|dependency ratio", re.I,
)
METHOD_WORDS = re.compile(r"how (is|are|do|does)\b.*\b(estimat|calculat|measur|count|produc|defin|made|work)|"
                          r"defin|methodolog|uncertain|reliable|accura|what does .* mean|difference between|"
                          r"\bcounter\b|where does .* data|data source|why (are|is|do)", re.I)
DATA_ASK = re.compile(r"how many people|population (of|in|now|today|right now|currently|size)|current population|"
                      r"(world|global|earth)'?s? population|total population", re.I)
RANK_WORDS = re.compile(r"which countr|top \d*|largest|biggest|smallest|fastest|slowest|most|least|rank|"
                        r"contribut|highest|lowest", re.I)
YEAR = re.compile(r"\b(19[5-9]\d|20\d\d)\b")
LAST_N = re.compile(r"last (\d{1,2}) years|past (\d{1,2}) years")

ALIASES = {
    # No bare "us"/"america": they collide with "tell us" and "Latin America".
    "usa": "USA", "u.s.": "USA", "united states of america": "USA",
    "uk": "GBR", "britain": "GBR", "great britain": "GBR", "england": "GBR",
    "russia": "RUS", "south korea": "KOR", "korea": "KOR", "north korea": "PRK", "iran": "IRN", "egypt": "EGY",
    "vietnam": "VNM", "turkey": "TUR", "drc": "COD", "dr congo": "COD", "democratic republic of the congo": "COD",
    "republic of the congo": "COG", "syria": "SYR", "venezuela": "VEN", "yemen": "YEM", "laos": "LAO",
    "czech republic": "CZE", "slovakia": "SVK", "kyrgyzstan": "KGZ", "hong kong": "HKG", "macau": "MAC",
    "gambia": "GMB", "bahamas": "BHS", "ivory coast": "CIV", "cote d'ivoire": "CIV", "world": "WLD", "global": "WLD",
    "globally": "WLD", "earth": "WLD", "micronesia": "FSM", "st lucia": "LCA", "brunei": "BRN",
    "latin america": "LCN", "middle east": "MEA",
}
NAMED_ASK = re.compile(r"(?:population|people|inhabitants|residents) (?:of|in) "
                       r"((?:the )?[A-Z][\w'’.-]*(?: [A-Z][\w'’.-]*)*(?:(?:,| and| or) (?:the )?[A-Z][\w'’.-]*(?: [A-Z][\w'’.-]*)*)*)")
PROFILE_ASK = re.compile(r"tell me about|overview|profile|summary|statistic|stats|compare|\bvs\.?\b|versus|trend",
                         re.I)


def build_name_index(countries: list[Country]) -> dict[str, str]:
    index: dict[str, str] = {}
    short_counts: dict[str, int] = {}
    for c in countries:
        index[c.name.lower()] = c.iso3
        if ", " in c.name:
            short = c.name.split(", ")[0].lower()
            short_counts[short] = short_counts.get(short, 0) + 1
    for c in countries:
        if ", " in c.name:
            short = c.name.split(", ")[0].lower()
            if short_counts[short] == 1:
                index.setdefault(short, c.iso3)
    known = {c.iso3 for c in countries}
    for alias, iso3 in ALIASES.items():
        if iso3 in known:
            index[alias] = iso3
    return index


def find_countries(question: str, name_index: dict[str, str], known_iso3: set[str]) -> list[str]:
    found: list[tuple[int, str]] = []
    q = question.lower()
    taken = [False] * len(q)
    for name in sorted(name_index, key=len, reverse=True):
        for m in re.finditer(rf"(?<![\w]){re.escape(name)}(?![\w])", q):
            if any(taken[m.start(): m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            found.append((m.start(), name_index[name]))
    for m in re.finditer(r"\b[A-Z]{3}\b", question):
        if m.group(0) in known_iso3 and m.group(0) not in ("THE", "AND"):
            found.append((m.start(), m.group(0)))
    ordered: list[str] = []
    for _, iso3 in sorted(found):
        if iso3 not in ordered:
            ordered.append(iso3)
    return ordered[:6]


def rules_plan(question: str, countries: list[Country], latest_year: int) -> Plan:
    name_index = build_name_index(countries)
    isos = find_countries(question, name_index, {c.iso3 for c in countries})
    metrics: list[str] = []
    for pattern, ms in METRIC_KEYWORDS:
        if re.search(pattern, question, re.I):
            metrics += [m for m in ms if m not in metrics]
    if "population_total" not in metrics:
        metrics.insert(0, "population_total")

    years = sorted(int(y) for y in YEAR.findall(question))
    start, end = None, latest_year
    m = LAST_N.search(question.lower())
    if m:
        start = latest_year - int(m.group(1) or m.group(2))
    elif len(years) >= 2:
        start, end = years[0], min(years[-1], latest_year)
    elif len(years) == 1:
        start = years[0] if re.search(r"since|from|after", question, re.I) else None
        if start is None:
            end = min(years[0], latest_year)
    start = start if start is not None else max(2000, end - 10)

    non_world = [i for i in isos if i != "WLD"]
    # A country name alone is not enough ("What is the capital of France?" is out of scope).
    in_domain = bool(DOMAIN_WORDS.search(question)) or bool(non_world and PROFILE_ASK.search(question))
    if not in_domain:
        intent = "out_of_scope"
    elif RANK_WORDS.search(question) and len(non_world) < 2:
        intent = "ranking"
    elif len(non_world) >= 2:
        intent = "compare"
    elif len(non_world) == 1:
        intent = "country"
    elif METHOD_WORDS.search(question) or (not DATA_ASK.search(question) and re.match(r"\s*what (is|are)\b", question, re.I)
                                           and not re.search(r"\d", question)):
        intent = "methodology"
    else:
        intent = "world"
    # Named places the user asked about that are not in the dataset ("population of Atlantis").
    unresolved = []
    m_named = NAMED_ASK.search(question)
    if m_named:
        for name in re.split(r",| and | or ", m_named.group(1)):
            name = re.sub(r"^the ", "", name.strip(), flags=re.I).rstrip("?.!")
            if name and name.lower() not in name_index and name.upper() not in {c.iso3 for c in countries}:
                unresolved.append(name)
    if intent == "world" and unresolved:
        isos = []  # do not silently substitute world figures for unknown places
    elif intent == "world" and "WLD" not in isos:
        isos = ["WLD"]
    if intent == "country":
        isos = non_world
    if intent == "compare":
        isos = non_world

    return Plan(
        intent=intent, countries=isos if intent not in ("ranking", "methodology", "out_of_scope") else [],
        metrics=metrics, start_year=start, end_year=end,
        needs_data=intent in ("world", "country", "compare", "ranking"),
        needs_analysis=intent in ("world", "country", "compare", "ranking"),
        needs_research=intent != "out_of_scope",
        research_query=question, planner="rules", unresolved=unresolved,
    )


PLANNER_SYSTEM = """You are the planning step of a demographic data assistant. Return ONLY a JSON object with keys:
intent (one of: world, country, compare, ranking, methodology, out_of_scope), countries (list of country names
exactly as the user wrote them), metrics (subset of: {metrics}), start_year (int or null), end_year (int or null).
Use out_of_scope for anything not about population or demographic data. Do not answer the question."""


def parse_llm_plan(raw: str, base: Plan, name_index: dict[str, str], allowed_metrics: tuple[str, ...], latest_year: int) -> Plan | None:
    """Validate a Claude-proposed plan. Returns None if anything is off, so rules win."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    intent = data.get("intent")
    if intent not in INTENTS:
        return None
    isos = []
    for name in data.get("countries") or []:
        iso = name_index.get(str(name).strip().lower())
        if iso is None:
            return None  # unknown entity: do not trust the plan
        if iso not in isos:
            isos.append(iso)
    metrics = [x for x in (data.get("metrics") or []) if x in allowed_metrics]
    if "population_total" not in metrics:
        metrics.insert(0, "population_total")

    def year(v, default):
        return v if isinstance(v, int) and 1960 <= v <= latest_year else default

    plan = Plan(**base)
    plan.update(intent=intent, countries=isos, metrics=metrics,
                start_year=year(data.get("start_year"), base.get("start_year")),
                end_year=year(data.get("end_year"), base.get("end_year")), planner="claude")
    plan["needs_data"] = plan["needs_analysis"] = intent in ("world", "country", "compare", "ranking")
    plan["needs_research"] = intent != "out_of_scope"
    if intent == "world":
        plan["countries"] = ["WLD"]
    if intent in ("country", "compare") and not isos:
        return None
    return plan
