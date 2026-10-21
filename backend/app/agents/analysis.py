"""Deterministic analysis shared by the Copilot and the report workflow.

Produces numbered facts (F1, F2, ...) that are the only numbers an LLM is allowed to restate.
"""

from __future__ import annotations

from app.agents.state import Fact
from app.domain import calculations as calc
from app.domain.errors import CalculationError
from app.domain.formatting import METRIC_LABELS, fmt_metric, fmt_pct, fmt_people


class FactBook:
    def __init__(self, source_label: str = "S1") -> None:
        self.facts: list[Fact] = []
        self.source = source_label

    def add(self, label: str, value: float, display: str, *, unit: str = "", year: int | None = None,
            scope: str = "", metric: str = "", kind: str = "estimate") -> str:
        fid = f"F{len(self.facts) + 1}"
        self.facts.append(Fact(id=fid, label=label, value=float(value), display=display, unit=unit, year=year,
                               scope=scope, metric=metric, kind=kind, source=self.source))
        return fid


def _bounds(series: dict[int, float], start: int | None, end: int | None) -> dict[int, float]:
    return {y: v for y, v in series.items() if (start is None or y >= start) and (end is None or y <= end)}


def analyse_scope(fb: FactBook, name: str, iso3: str, series: dict[str, dict[int, float]], metrics: list[str],
                  start: int | None, end: int | None) -> dict:
    """Facts for one country/aggregate. Returns summary dict with change info and findings."""
    findings: list[str] = []
    summary: dict = {"iso3": iso3, "name": name}
    pop = _bounds(series.get("population_total", {}), start, end)
    if pop:
        y1 = max(pop)
        f_latest = fb.add(f"{name} population ({y1})", pop[y1], fmt_people(pop[y1]), unit="persons", year=y1,
                          scope=iso3, metric="population_total")
        summary["latest"] = (y1, pop[y1], f_latest)
        if len(pop) >= 2:
            try:
                ch = calc.change_over_period(pop)
                f0 = fb.add(f"{name} population ({ch.start_year})", ch.start_value, fmt_people(ch.start_value),
                            unit="persons", year=ch.start_year, scope=iso3, metric="population_total")
                fa = fb.add(f"{name} absolute change {ch.start_year}-{ch.end_year}", ch.absolute, fmt_people(ch.absolute),
                            unit="persons", year=ch.end_year, scope=iso3, metric="population_change", kind="derived")
                fp = fb.add(f"{name} percent change {ch.start_year}-{ch.end_year}", ch.percent,
                            fmt_pct(ch.percent, 1, signed=True), unit="%", year=ch.end_year, scope=iso3,
                            metric="population_change_pct", kind="derived")
                fc = None
                if ch.cagr_percent is not None:
                    fc = fb.add(f"{name} compound annual growth {ch.start_year}-{ch.end_year}", ch.cagr_percent,
                                fmt_pct(ch.cagr_percent, 2), unit="% per year", year=ch.end_year, scope=iso3,
                                metric="cagr", kind="derived")
                summary["change"] = ch
                summary["cagr_fact"] = fc
                direction = "grew" if ch.absolute > 0 else "declined"
                findings.append(
                    f"{name}'s population {direction} from {fmt_people(ch.start_value)} in {ch.start_year} [{f0}] to "
                    f"{fmt_people(ch.end_value)} in {ch.end_year} [{f_latest}], a change of {fmt_people(ch.absolute)} "
                    f"[{fa}] ({fmt_pct(ch.percent, 1, signed=True)} [{fp}]"
                    + (f"; {fmt_pct(ch.cagr_percent, 2)} per year compounded [{fc}])." if fc else ").")
                )
            except CalculationError:
                pass
        else:
            findings.append(f"{name}'s population was {fmt_people(pop[y1])} in {y1} [{f_latest}].")
    for metric in metrics:
        if metric == "population_total":
            continue
        s = _bounds(series.get(metric, {}), start, end)
        if not s:
            summary.setdefault("missing", []).append(metric)
            continue
        y1 = max(s)
        fid = fb.add(f"{name} {METRIC_LABELS.get(metric, metric).lower()} ({y1})", s[y1], fmt_metric(metric, s[y1]),
                     year=y1, scope=iso3, metric=metric)
        y0 = min(s)
        if y0 != y1:
            fid0 = fb.add(f"{name} {METRIC_LABELS.get(metric, metric).lower()} ({y0})", s[y0], fmt_metric(metric, s[y0]),
                          year=y0, scope=iso3, metric=metric)
            findings.append(f"{METRIC_LABELS.get(metric, metric)} in {name}: {fmt_metric(metric, s[y0])} in {y0} "
                            f"[{fid0}] and {fmt_metric(metric, s[y1])} in {y1} [{fid}].")
        else:
            findings.append(f"{METRIC_LABELS.get(metric, metric)} in {name}: {fmt_metric(metric, s[y1])} in {y1} [{fid}].")
    summary["findings"] = findings
    return summary


def analyse_compare(fb: FactBook, scopes: list[dict], metrics: list[str], start: int | None, end: int | None) -> dict:
    """Compare countries on identical reference years."""
    pops = {s["iso3"]: _bounds(s["series"].get("population_total", {}), start, end) for s in scopes}
    common = set.intersection(*(set(p) for p in pops.values())) if pops else set()
    issues = []
    if len(common) < 2:
        issues.append("The selected countries do not share two common reference years; growth cannot be compared.")
        return {"summaries": [], "findings": [], "issues": issues, "common_years": None}
    y0, y1 = min(common), max(common)
    if (start and y0 != start) or (end and y1 != end):
        issues.append(f"Comparison aligned to common reference years {y0}-{y1}.")
    summaries = []
    findings = []
    for s in scopes:
        summ = analyse_scope(fb, s["name"], s["iso3"], s["series"], metrics, y0, y1)
        summaries.append(summ)
        findings += summ["findings"]
    with_cagr = [(x["name"], x["change"].cagr_percent, x.get("cagr_fact")) for x in summaries
                 if x.get("change") and x["change"].cagr_percent is not None]
    if len(with_cagr) >= 2:
        ranked = sorted(with_cagr, key=lambda t: -t[1])
        top, rest = ranked[0], ranked[1:]
        others = ", ".join(f"{n} ({fmt_pct(v, 2)} [{f}])" for n, v, f in rest)
        verb = "faster" if len(ranked) == 2 else "fastest"
        findings.insert(0, f"Between {y0} and {y1}, {top[0]} grew {verb} at {fmt_pct(top[1], 2)} per year "
                           f"[{top[2]}], compared with {others}.")
    return {"summaries": summaries, "findings": findings, "issues": issues, "common_years": (y0, y1)}


def analyse_ranking(fb: FactBook, inputs: dict, start: int, end: int, n: int = 5) -> dict:
    names, p0, p1 = inputs["names"], inputs["start"], inputs["end"]
    world = inputs["world"]
    abs_change = {k: p1[k] - p0[k] for k in p1}
    cagr = {k: calc.cagr_percent(p0[k], p1[k], end - start) for k in p1 if p0[k] >= 1_000_000 and end > start}
    findings, rows = [], []
    world_change = (world.get(end, 0) - world.get(start, 0)) if start in world and end in world else None
    fw = None
    if world_change:
        fw = fb.add(f"World population change {start}-{end}", world_change, fmt_people(world_change), year=end,
                    scope="WLD", metric="population_change", kind="derived")
    top_abs = calc.rank_desc(abs_change)[:n]
    parts = []
    for iso3, v in top_abs:
        f = fb.add(f"{names[iso3]} population change {start}-{end}", v, fmt_people(v), year=end, scope=iso3,
                   metric="population_change", kind="derived")
        share = None
        if world_change:
            share = calc.share_percent(v, world_change)
            fs = fb.add(f"{names[iso3]} share of world population change {start}-{end}", share, fmt_pct(share, 1),
                        unit="%", year=end, scope=iso3, metric="share_of_world_change", kind="derived")
            parts.append(f"{names[iso3]} (+{fmt_people(v)} [{f}], {fmt_pct(share, 1)} of world growth [{fs}])")
        else:
            parts.append(f"{names[iso3]} (+{fmt_people(v)} [{f}])")
        rows.append({"iso3": iso3, "name": names[iso3], "absolute_change": v, "share_of_world_change": share})
    findings.append(f"Largest absolute population increases {start}-{end}: " + "; ".join(parts) + ".")
    if fw:
        findings.append(f"World population changed by {fmt_people(world_change)} over the same period [{fw}].")
    top_rate = calc.rank_desc(cagr)[:n]
    ft = fb.add("Minimum population for growth-rate ranking", 1_000_000, "1 million", unit="persons",
                metric="ranking_threshold", kind="parameter")
    rate_parts = []
    for iso3, v in top_rate:
        f = fb.add(f"{names[iso3]} compound annual growth {start}-{end}", v, fmt_pct(v, 2), unit="% per year",
                   year=end, scope=iso3, metric="cagr", kind="derived")
        rate_parts.append(f"{names[iso3]} ({fmt_pct(v, 2)} per year [{f}])")
    findings.append(f"Fastest compound annual growth among countries with at least 1 million people [{ft}]: "
                    + "; ".join(rate_parts) + ".")
    bottom = sorted(abs_change.items(), key=lambda kv: (kv[1], kv[0]))[:3]
    if bottom and bottom[0][1] < 0:
        dec = []
        for iso3, v in bottom:
            if v < 0:
                f = fb.add(f"{names[iso3]} population change {start}-{end}", v, fmt_people(v), year=end, scope=iso3,
                           metric="population_change", kind="derived")
                dec.append(f"{names[iso3]} ({fmt_people(v)} [{f}])")
        findings.append("Largest absolute declines: " + "; ".join(dec) + ".")
    return {"findings": findings, "rows": rows,
            "chart": {"type": "bar", "title": f"Largest population increases {start}-{end}", "unit": "persons",
                      "series": [{"name": r["name"], "value": r["absolute_change"]} for r in rows]}}


def line_chart(title: str, series_by_name: dict[str, dict[int, float]], unit: str) -> dict:
    years = sorted({y for s in series_by_name.values() for y in s})
    return {"type": "line", "title": title, "unit": unit, "years": years,
            "series": [{"name": n, "points": [{"year": y, "value": s[y]} for y in years if y in s]}
                       for n, s in series_by_name.items()]}
