"""LangGraph workflow for Country Intelligence Reports.

    START -> report_supervisor -> country_data -> research -> demographic_analysis -> validation
    validation --(period needs realignment, once)--> country_data
               --(essential integrity check failed)--> assembly (status=blocked, not published)
               --(ok)--> narrative -> narrative_validation -> assembly -> END

Reuses the Copilot building blocks: PopulationService (data), the BM25 retriever (research),
FactBook + domain calculations (analysis), numeric_guard (validation) and the Claude client.
"""

from __future__ import annotations

import json
import operator
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.analysis import FactBook
from app.agents.nodes.common import AgentDeps, time_left, traced
from app.agents.numeric_guard import check_citations, check_numbers
from app.agents.prompts import REPORT_SYSTEM, report_user_prompt
from app.domain.errors import DataUnavailableError, NotFoundError
from app.integrations.llm import LLMError
from app.reports.builder import SectionBuilder
from app.reports.catalog import PERIODS, SECTION_TITLES, flag_emoji, period_years

RESEARCH_TOPICS = {
    "population": "total population midyear estimate definition source",
    "vital": "total fertility rate births per woman replacement life expectancy crude birth death rate",
    "age": "age structure dependency ratio ageing urban population definition",
    "migration": "net migration immigrants emigrants uncertainty",
    "projection": "projections estimates counts uncertainty illustrative",
    "quality": "revisions comparability aggregates missing values freshness",
}
DISCLAIMER = ("All population figures are estimates or derived calculations based on the cited dataset and its "
              "reference dates; they are not real-time counts. Indicators marked 'Data unavailable' were not "
              "estimated or filled in. No projections are presented unless an official projection dataset is "
              "loaded. AI-generated narrative (where present) explains the figures and is validated against them.")


class ReportState(TypedDict, total=False):
    report_id: str
    iso3: str
    period: str
    sections: list[str]
    deadline: float
    start_year: int
    end_year: int
    period_note: str | None
    data_attempts: int
    ctx: dict
    provenance: dict
    documents: list[dict]
    docs_by_topic: dict
    built: dict
    facts: list[dict]
    validation: dict
    narratives: dict
    narrative_validation: dict
    mode: str
    model: str | None
    content: dict
    status: str
    trace: Annotated[list, operator.add]


def build_report_graph(deps: AgentDeps, on_progress: Callable[[int, str], None] | None = None):
    progress = on_progress or (lambda pct, step: None)
    svc, tools = deps.service, deps.tools

    @traced("report_supervisor", "Report Supervisor Agent")
    def report_supervisor(state: ReportState) -> dict:
        progress(5, "planning")
        src = svc.source()
        latest = svc.repo.latest_year(src.id, "population_total", state["iso3"]) or \
            svc.repo.latest_year(src.id, "population_total")
        start, end = period_years(state["period"], latest)
        if state["period"] == "latest":
            start = max(start, end - 1)
        return {"start_year": start, "end_year": end, "data_attempts": 0, "period_note": None,
                "_detail": f"{len(state['sections'])} sections, period {start}-{end}"}

    @traced("country_data", "Country Data Agent")
    def country_data(state: ReportState) -> dict:
        progress(20, "loading country data")
        c = svc.country(state["iso3"])
        profile = svc.country_profile(c.iso3)
        region_series, region_name = {}, None
        if c.region_code:
            try:
                region = svc.country(c.region_code)
                region_name = region.name
                region_series = svc.country_profile(region.iso3)["series"]
            except NotFoundError:
                pass
        world_series = svc.country_profile("WLD")["series"]
        latest_pop = svc.latest_values("population_total")
        real = {x.iso3 for x in svc.all_countries()}  # computed once (was re-queried per row)
        ranked = sorted(((v[1], k) for k, v in latest_pop.items() if k in real and v[0] == state["end_year"]),
                        reverse=True)
        rank = next((i + 1 for i, (_, k) in enumerate(ranked) if k == c.iso3), None)
        provenance = tools.get_provenance(state["end_year"])
        ctx = {"country": c, "series": profile["series"], "region_series": region_series, "region_name": region_name,
               "world_series": world_series, "start": state["start_year"], "end": state["end_year"], "rank": rank,
               "rank_total": len(ranked)}
        pop = profile["series"].get("population_total", {})
        detail = f"{len(profile['series'])} indicators; population years {min(pop) if pop else '-'}-{max(pop) if pop else '-'}"
        return {"ctx": ctx, "provenance": provenance, "data_attempts": state.get("data_attempts", 0) + 1,
                "_detail": detail}

    @traced("research", "Research and RAG Agent")
    def research(state: ReportState) -> dict:
        progress(35, "retrieving methodology")
        docs, by_topic = [], {}
        for topic, query in RESEARCH_TOPICS.items():
            hits = deps.retriever.retrieve(query, k=1)
            if not hits:
                continue
            hit = asdict(hits[0])
            existing = next((d for d in docs if d["doc_id"] == hit["doc_id"]), None)
            if existing is None:
                hit["label"] = f"D{len(docs) + 1}"
                docs.append(hit)
                existing = hit
            by_topic[topic] = existing["label"]
        flagged = sum(len(d["flagged_lines"]) for d in docs)
        return {"documents": docs, "docs_by_topic": by_topic,
                "_detail": f"{len(docs)} documents" + (f"; {flagged} suspicious lines removed" if flagged else "")}

    @traced("demographic_analysis", "Demographic Analysis Agent")
    def demographic_analysis(state: ReportState) -> dict:
        progress(50, "calculating indicators")
        fb = FactBook()
        ctx = {**state["ctx"], "start": state["start_year"], "end": state["end_year"],
               "docs_by_topic": state.get("docs_by_topic", {})}
        b = SectionBuilder(fb, ctx)
        built: dict[str, dict] = {}
        for sid in state["sections"]:
            if sid in ("executive_summary", "key_findings", "sources_methodology"):
                continue
            try:
                built[sid] = getattr(b, sid)()
            except Exception as exc:  # partial failure: one section must not sink the report
                built[sid] = b.section(sid, status="unavailable", unavailable=[SECTION_TITLES[sid]],
                                       notes=[f"This section could not be generated ({type(exc).__name__})."])
        built["key_findings"] = b.key_findings(built)
        built["sources_methodology"] = b.sources_methodology(state["provenance"], state.get("documents", []))
        exec_pts = [p for sid in ("current_population", "historical_trends", "growth_rate", "fertility_life",
                                  "age_structure") if sid in built for p in built[sid]["summary_points"][:1]]
        built["executive_summary"] = b.section("executive_summary", summary_points=exec_pts[:5],
                                               metrics=built.get("current_population", {}).get("metrics", [])[:1])
        statuses = [s["status"] for s in built.values()]
        return {"built": built, "facts": fb.facts,
                "_detail": f"{len(fb.facts)} facts; {statuses.count('unavailable')} section(s) unavailable"}

    @traced("validation", "Validation Agent")
    def validation(state: ReportState) -> dict:
        progress(65, "validating")
        ctx, prov = state["ctx"], state.get("provenance") or {}
        series = ctx["series"]
        pop = series.get("population_total", {})
        checks = []

        def check(name, ok, detail, essential=False):
            checks.append({"name": name, "passed": bool(ok), "detail": detail,
                           "severity": "info" if ok else ("essential" if essential else "warning")})

        check("provenance", prov.get("release_version") and prov.get("source_id"),
              f"{prov.get('dataset_name')} release {prov.get('release_version')}", essential=True)
        check("population_present", bool(pop), f"{len(pop)} population observations", essential=True)
        check("population_positive", all(v > 0 for v in pop.values()), "all population values positive", essential=True)
        window = [y for y in pop if state["start_year"] <= y <= state["end_year"]]
        realign = None
        if pop and state["start_year"] not in pop and state.get("data_attempts", 0) < 2:
            first = min((y for y in pop if y >= state["start_year"]), default=None) or min(pop)
            realign = first
        check("period_coverage", bool(window) and not realign,
              f"population available for {len(window)} year(s) in {state['start_year']}-{state['end_year']}")
        latest_pop_year = max(pop) if pop else None
        lag = [m for m, s in series.items() if s and latest_pop_year and max(s) < latest_pop_year
               and m not in ("land_area_km2", "density_per_km2")]
        check("reference_year_alignment", not lag,
              "indicators lagging the population reference year: " + ", ".join(sorted(lag)) if lag else "aligned")
        for label, metrics, tol in (("age_shares_sum", ("age_0_14_pct", "age_15_64_pct", "age_65_plus_pct"), 1.0),
                                    ("urban_rural_sum", ("urban_pct", "rural_pct"), 1.0)):
            ss = [series.get(m, {}) for m in metrics]
            common = set.intersection(*(set(s) for s in ss)) if all(ss) else set()
            if common:
                y = max(common)
                total = sum(s[y] for s in ss)
                check(label, abs(total - 100) <= tol, f"{total:.2f}% in {y}")
        dens, land = series.get("density_per_km2", {}), series.get("land_area_km2", {})
        common = set(dens) & set(land) & set(pop)
        if common:
            y = max(common)
            implied = pop[y] / land[y] if land[y] else None
            ok = implied is not None and abs(implied - dens[y]) / dens[y] <= 0.03
            check("density_consistency", ok, f"published {dens[y]:.1f} vs implied {implied:.1f} per km² ({y})")
        check("data_fresh", (prov.get("freshness") or {}).get("status") != "stale",
              f"freshness={(prov.get('freshness') or {}).get('status')}")
        check("not_synthetic", not prov.get("is_synthetic"), "dataset is not synthetic demo data")
        built = state.get("built") or {}
        unavailable = [s["title"] for s in built.values() if s["status"] == "unavailable"]
        check("section_coverage", not unavailable, "unavailable: " + ", ".join(unavailable) if unavailable else "all available")
        essential_failed = [c for c in checks if c["severity"] == "essential"]
        status = "failed" if essential_failed else ("warnings" if any(not c["passed"] for c in checks) else "passed")
        update = {"validation": {"status": status, "checks": checks}}
        if realign is not None and not essential_failed:
            update.update(start_year=realign, period_note=f"Requested period starts before available data; "
                                                          f"aligned to {realign}.",
                          _status="degraded", _detail=f"period realigned to {realign}; re-running data agent")
            update["validation"]["retry"] = True
        else:
            update["_detail"] = status
        return update

    def route_validation(state: ReportState) -> str:
        v = state.get("validation") or {}
        if v.get("retry"):
            return "country_data"
        if v.get("status") == "failed":
            return "assembly"
        return "narrative"

    @traced("narrative", "Response Generator")
    def narrative(state: ReportState) -> dict:
        progress(78, "writing narrative")
        if deps.llm is None:
            return {"narratives": {}, "mode": "demo", "model": None, "_status": "skipped",
                    "_detail": "demo mode: deterministic summaries only"}
        if time_left(state) < 20:
            return {"narratives": {}, "mode": "fallback", "model": None, "_status": "degraded", "_detail": "deadline"}
        facts_by_id = {f["id"]: f for f in state["facts"]}
        per_section = {}
        for sid, sec in state["built"].items():
            ids = set(re.findall(r"\bF\d+\b", json.dumps(sec)))
            per_section[sid] = [facts_by_id[i] for i in sorted(ids, key=lambda x: int(x[1:])) if i in facts_by_id]
        prompt = report_user_prompt(state["ctx"]["country"].name, per_section, state.get("documents", []))
        try:
            res = deps.llm.generate(REPORT_SYSTEM, prompt, max_tokens=deps.settings.llm_report_max_output_tokens)
            m = re.search(r"\{.*\}", res.text, re.S)
            data = json.loads(m.group(0)) if m else {}
            narratives = {k: str(v)[:1200] for k, v in data.items() if k in state["built"] and isinstance(v, str)}
        except (LLMError, json.JSONDecodeError) as exc:
            return {"narratives": {}, "mode": "fallback", "model": None, "_status": "degraded",
                    "_detail": f"narrative unavailable ({type(exc).__name__})"}
        return {"narratives": narratives, "mode": "claude", "model": res.model,
                "_detail": f"{len(narratives)} section narratives from {res.model}"}

    @traced("narrative_validation", "Validation Agent")
    def narrative_validation(state: ReportState) -> dict:
        progress(86, "validating narrative")
        facts = state.get("facts", [])
        docs = state.get("documents", [])
        years = {f["year"] for f in facts if f.get("year")} | set(range(state["start_year"], state["end_year"] + 1))
        labels = {f["id"] for f in facts} | {d["label"] for d in docs} | {"S1"}
        accepted, rejected = {}, {}
        for sid, text in (state.get("narratives") or {}).items():
            num = check_numbers(text, [f["value"] for f in facts], years, [d["text"] for d in docs])
            bad = check_citations(text, labels)
            if num.passed and not bad:
                accepted[sid] = text
            else:
                rejected[sid] = {"unsupported_numbers": num.unsupported, "invalid_citations": bad, "issues": num.issues}
        return {"narratives": accepted, "narrative_validation": {"accepted": sorted(accepted), "rejected": rejected},
                "_status": "degraded" if rejected else "ok",
                "_detail": f"{len(accepted)} accepted, {len(rejected)} rejected"}

    @traced("assembly", "Report Assembly Node")
    def assembly(state: ReportState) -> dict:
        progress(92, "assembling")
        ctx, prov = state["ctx"], state.get("provenance") or {}
        c = ctx["country"]
        v = state.get("validation") or {}
        blocked = v.get("status") == "failed"
        built = state.get("built") or {}
        narratives = state.get("narratives") or {}
        rejected = (state.get("narrative_validation") or {}).get("rejected", {})
        sections = []
        for i, sid in enumerate(state["sections"], start=1):
            sec = dict(built.get(sid) or {"id": sid, "title": SECTION_TITLES[sid], "status": "unavailable",
                                          "summary_points": [], "metrics": [], "table": None, "chart": None,
                                          "notes": ["Not generated."], "unavailable": [SECTION_TITLES[sid]],
                                          "citations": []})
            sec["number"] = i
            if sid in narratives:
                sec["narrative"], sec["narrative_source"] = narratives[sid], "claude"
            elif sid in rejected:
                sec["notes"] = sec.get("notes", []) + ["AI narrative removed: it failed numeric/citation validation."]
            sections.append(sec)
        sources = []
        if prov:
            sources.append({"label": "S1", "kind": "dataset", "title": prov.get("dataset_name"),
                            "publisher": prov.get("publisher"), "url": prov.get("landing_page") or prov.get("source_url"),
                            "published": prov.get("release_version"),
                            "reference": f"Licence {prov.get('license')}; snapshot {prov.get('snapshot_id')}; "
                                         f"reference date {prov.get('reference_date')}"})
        for d in state.get("documents", []):
            sources.append({"label": d["label"], "kind": "document", "title": d["title"], "publisher": d["publisher"],
                            "url": d["source_url"], "published": d["published"], "reference": d["heading"]})
        limitations = [prov.get("uncertainty_note", "Uncertainty not quantified by the source."),
                       "Figures are midyear estimates, not census counts or real-time figures.",
                       "No official projection dataset is loaded; future projections are not presented."]
        if state.get("period_note"):
            limitations.append(state["period_note"])
        limitations += [ch["detail"] for ch in v.get("checks", []) if not ch["passed"]]
        content = {
            "schema_version": 1,
            "title": f"Country Intelligence Report: {c.name}",
            "country": {"iso3": c.iso3, "iso2": c.iso2, "name": c.name, "region": c.region,
                        "income_level": c.income_level, "capital": c.capital, "flag": flag_emoji(c.iso2)},
            "period": {"key": state["period"], "label": PERIODS[state["period"]]["label"],
                       "start_year": state["start_year"], "end_year": state["end_year"]},
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "data_reference_date": prov.get("reference_date"),
            "mode": state.get("mode") or ("demo" if deps.llm is None else "fallback"),
            "model": state.get("model"),
            "disclaimer": DISCLAIMER,
            "provenance": prov,
            "sections": sections,
            "facts": state.get("facts", []),
            "sources": sources,
            "validation": {**v, "narrative": state.get("narrative_validation")},
            "limitations": list(dict.fromkeys(x for x in limitations if x)),
        }
        return {"content": content, "status": "blocked" if blocked else "completed",
                "_detail": "blocked by essential validation failure" if blocked else f"{len(sections)} sections"}

    g = StateGraph(ReportState)
    for name, fn in (("report_supervisor", report_supervisor), ("country_data", country_data), ("research", research),
                     ("demographic_analysis", demographic_analysis), ("validation", validation),
                     ("narrative", narrative), ("narrative_validation", narrative_validation), ("assembly", assembly)):
        g.add_node(name, fn)
    g.add_edge(START, "report_supervisor")
    g.add_edge("report_supervisor", "country_data")
    g.add_edge("country_data", "research")
    g.add_edge("research", "demographic_analysis")
    g.add_edge("demographic_analysis", "validation")
    g.add_conditional_edges("validation", route_validation, ["country_data", "assembly", "narrative"])
    g.add_edge("narrative", "narrative_validation")
    g.add_edge("narrative_validation", "assembly")
    g.add_edge("assembly", END)
    return g.compile()


__all__ = ["build_report_graph", "DataUnavailableError"]
