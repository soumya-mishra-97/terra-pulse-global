"""Deterministic section builders for Country Intelligence Reports.

Every number in a section comes from the imported dataset or from app.domain.calculations and is
registered in a FactBook. Indicators with no data are marked "Data unavailable", never estimated.
"""

from __future__ import annotations

from app.agents.analysis import FactBook
from app.domain import calculations as calc
from app.domain.errors import CalculationError
from app.domain.formatting import METRIC_LABELS, fmt_metric, fmt_pct, fmt_people
from app.reports.catalog import SECTION_TITLES

UNAVAILABLE = "Data unavailable"


def _window(s: dict[int, float] | None, start: int, end: int) -> dict[int, float]:
    return {y: v for y, v in (s or {}).items() if start <= y <= end}


class SectionBuilder:
    def __init__(self, fb: FactBook, ctx: dict) -> None:
        """ctx keys: country (Country), series, region_series, region_name, world_series, start, end,
        rank (int|None), rank_total, docs_by_topic (topic -> doc label)."""
        self.fb = fb
        self.ctx = ctx
        self.name = ctx["country"].name
        self.iso3 = ctx["country"].iso3
        self.start, self.end = ctx["start"], ctx["end"]

    # ---- helpers -------------------------------------------------------------
    def s(self, metric: str, scope: str = "country") -> dict[int, float]:
        src = {"country": self.ctx["series"], "region": self.ctx.get("region_series") or {},
               "world": self.ctx.get("world_series") or {}}[scope]
        return _window(src.get(metric), self.start, self.end)

    def fact(self, metric: str, year: int, value: float, scope_name: str | None = None, scope: str | None = None,
             kind: str = "estimate", label: str | None = None, display: str | None = None) -> str:
        nm = scope_name or self.name
        return self.fb.add(label or f"{nm} {METRIC_LABELS.get(metric, metric).lower()} ({year})", value,
                           display or fmt_metric(metric, value), year=year, scope=scope or self.iso3, metric=metric,
                           kind=kind)

    def section(self, sid: str, **kw) -> dict:
        base = {"id": sid, "title": SECTION_TITLES[sid], "status": "ok", "summary_points": [], "metrics": [],
                "table": None, "chart": None, "notes": [], "unavailable": [], "citations": ["S1"],
                "narrative": None, "narrative_source": None}
        base.update(kw)
        if base["unavailable"] and base["status"] == "ok":
            base["status"] = "partial" if (base["metrics"] or base["table"]) else "unavailable"
        return base

    def metric_row(self, label: str, display: str, year: int | None, fid: str | None, kind: str = "estimate") -> dict:
        return {"label": label, "value": display, "year": year, "fact_id": fid, "kind": kind}

    def first_last(self, metric: str, out: dict, scope: str = "country") -> tuple | None:
        s = self.s(metric, scope)
        if not s:
            out["unavailable"].append(METRIC_LABELS.get(metric, metric))
            out["metrics"].append(self.metric_row(METRIC_LABELS.get(metric, metric), UNAVAILABLE, None, None))
            return None
        y0, y1 = min(s), max(s)
        f1 = self.fact(metric, y1, s[y1])
        out["metrics"].append(self.metric_row(f"{METRIC_LABELS[metric]} ({y1})", fmt_metric(metric, s[y1]), y1, f1))
        f0 = None
        if y0 != y1:
            f0 = self.fact(metric, y0, s[y0])
            out["metrics"].append(self.metric_row(f"{METRIC_LABELS[metric]} ({y0})", fmt_metric(metric, s[y0]), y0, f0))
        return y0, s[y0], f0, y1, s[y1], f1

    def table(self, metrics: list[str]) -> dict | None:
        cols = [m for m in metrics if self.s(m)]
        if not cols:
            return None
        years = sorted({y for m in cols for y in self.s(m)})
        rows = [[str(y)] + [fmt_metric(m, self.s(m).get(y)) if self.s(m).get(y) is not None else "–" for m in cols]
                for y in years]
        return {"columns": ["Year"] + [METRIC_LABELS[m] for m in cols], "rows": rows}

    def doc(self, topic: str) -> str | None:
        return (self.ctx.get("docs_by_topic") or {}).get(topic)

    # ---- sections ------------------------------------------------------------
    def country_overview(self) -> dict:
        c = self.ctx["country"]
        out = self.section("country_overview")
        for label, val in (("ISO 3166 alpha-3 code", c.iso3), ("Region (World Bank)", c.region),
                           ("Income group (World Bank)", c.income_level), ("Capital city", c.capital)):
            out["metrics"].append(self.metric_row(label, val or UNAVAILABLE, None, None, kind="metadata"))
        land = self.s("land_area_km2")
        if land:
            y = max(land)
            fid = self.fact("land_area_km2", y, land[y])
            out["metrics"].append(self.metric_row(f"Land area ({y})", fmt_metric("land_area_km2", land[y]), y, fid))
            out["summary_points"].append(f"{self.name} has a land area of {fmt_metric('land_area_km2', land[y])} [{fid}].")
        else:
            out["unavailable"].append("Land area")
        out["summary_points"].insert(0, f"{self.name} is classified by the World Bank in the {c.region or 'unknown'} "
                                        f"region and the {c.income_level or 'unknown'} income group.")
        return out

    def current_population(self) -> dict:
        out = self.section("current_population")
        pop = self.s("population_total")
        if not pop:
            return self.section("current_population", status="unavailable", unavailable=["Total population"],
                                notes=["No population estimate is available for the selected period."])
        y = max(pop)
        fid = self.fact("population_total", y, pop[y])
        out["metrics"].append(self.metric_row(f"Total population ({y}, midyear estimate)", fmt_people(pop[y]), y, fid))
        out["metrics"].append(self.metric_row("Exact published value", f"{pop[y]:,.0f}", y, fid))
        pts = [f"The latest source estimate for {self.name} is {fmt_people(pop[y])} for 1 July {y} [{fid}]."]
        world = self.s("population_total", "world")
        if y in world:
            share = calc.share_percent(pop[y], world[y])
            fs = self.fb.add(f"{self.name} share of world population ({y})", share, fmt_pct(share, 2), unit="%", year=y,
                             scope=self.iso3, metric="share_of_world", kind="derived")
            out["metrics"].append(self.metric_row("Share of world population", fmt_pct(share, 2), y, fs, "derived"))
            pts.append(f"This is {fmt_pct(share, 2)} of the world population estimate for the same year [{fs}].")
        if self.ctx.get("rank"):
            fr = self.fb.add(f"{self.name} population rank ({y})", self.ctx["rank"], f"#{self.ctx['rank']}", year=y,
                             scope=self.iso3, metric="rank", kind="derived")
            out["metrics"].append(self.metric_row(f"Rank among {self.ctx['rank_total']} economies",
                                                  f"#{self.ctx['rank']}", y, fr, "derived"))
            pts.append(f"{self.name} ranks #{self.ctx['rank']} by population among the economies in the dataset [{fr}].")
        out["summary_points"] = pts
        out["notes"].append("Midyear estimate published by the source; not a census count or a real-time figure.")
        return out

    def historical_trends(self) -> dict:
        out = self.section("historical_trends")
        pop = self.s("population_total")
        if len(pop) < 2:
            return self.section("historical_trends", status="unavailable", unavailable=["Population history"],
                                notes=["At least two annual observations are needed to describe a trend."])
        ch = calc.change_over_period(pop)
        f0 = self.fact("population_total", ch.start_year, ch.start_value)
        f1 = self.fact("population_total", ch.end_year, ch.end_value)
        fa = self.fb.add(f"{self.name} absolute change {ch.start_year}-{ch.end_year}", ch.absolute, fmt_people(ch.absolute),
                         year=ch.end_year, scope=self.iso3, metric="population_change", kind="derived")
        fp = self.fb.add(f"{self.name} percent change {ch.start_year}-{ch.end_year}", ch.percent,
                         fmt_pct(ch.percent, 1, signed=True), year=ch.end_year, scope=self.iso3,
                         metric="population_change_pct", kind="derived")
        out["metrics"] += [
            self.metric_row(f"Population {ch.start_year}", fmt_people(ch.start_value), ch.start_year, f0),
            self.metric_row(f"Population {ch.end_year}", fmt_people(ch.end_value), ch.end_year, f1),
            self.metric_row("Absolute change", fmt_people(ch.absolute), ch.end_year, fa, "derived"),
            self.metric_row("Percent change", fmt_pct(ch.percent, 1, signed=True), ch.end_year, fp, "derived"),
        ]
        direction = "increased" if ch.absolute > 0 else "decreased"
        out["summary_points"] = [f"Between {ch.start_year} and {ch.end_year} the population {direction} from "
                                 f"{fmt_people(ch.start_value)} [{f0}] to {fmt_people(ch.end_value)} [{f1}], "
                                 f"a change of {fmt_people(ch.absolute)} [{fa}] ({fmt_pct(ch.percent, 1, signed=True)} [{fp}])."]
        out["table"] = self.table(["population_total"])
        out["chart"] = {"type": "line", "title": f"{self.name}: total population", "unit": "persons",
                        "series": [{"name": self.name, "points": [{"year": y, "value": v} for y, v in sorted(pop.items())]}]}
        return out

    def annual_change(self) -> dict:
        out = self.section("annual_change")
        pop = self.s("population_total")
        changes = calc.annual_changes(pop)
        if not changes:
            return self.section("annual_change", status="unavailable", unavailable=["Annual change"],
                                notes=["Consecutive annual observations are required."])
        out["table"] = {"columns": ["Year", "Change (persons)", "Change (%)"],
                        "rows": [[str(c["year"]), f"{c['absolute']:+,.0f}",
                                  fmt_pct(c["percent"], 2, signed=True) if c["percent"] is not None else "–"]
                                 for c in changes]}
        hi = max(changes, key=lambda c: (c["absolute"], -c["year"]))
        lo = min(changes, key=lambda c: (c["absolute"], c["year"]))
        fh = self.fb.add(f"{self.name} largest annual change ({hi['year']})", hi["absolute"], f"{hi['absolute']:+,.0f}",
                         year=hi["year"], scope=self.iso3, metric="annual_change", kind="derived")
        fl = self.fb.add(f"{self.name} smallest annual change ({lo['year']})", lo["absolute"], f"{lo['absolute']:+,.0f}",
                         year=lo["year"], scope=self.iso3, metric="annual_change", kind="derived")
        out["metrics"] += [self.metric_row(f"Largest annual change ({hi['year']})", f"{hi['absolute']:+,.0f}", hi["year"], fh, "derived"),
                           self.metric_row(f"Smallest annual change ({lo['year']})", f"{lo['absolute']:+,.0f}", lo["year"], fl, "derived")]
        out["summary_points"] = [f"The largest year-on-year change was {hi['absolute']:+,.0f} people in {hi['year']} [{fh}]; "
                                 f"the smallest was {lo['absolute']:+,.0f} in {lo['year']} [{fl}]."]
        out["chart"] = {"type": "bar", "title": f"{self.name}: annual population change", "unit": "persons",
                        "series": [{"name": str(c["year"]), "value": c["absolute"]} for c in changes]}
        return out

    def growth_rate(self) -> dict:
        out = self.section("growth_rate")
        r = self.first_last("population_growth_pct", out)
        pop = self.s("population_total")
        if len(pop) >= 2:
            try:
                ch = calc.change_over_period(pop)
                if ch.cagr_percent is not None:
                    fc = self.fb.add(f"{self.name} compound annual growth {ch.start_year}-{ch.end_year}", ch.cagr_percent,
                                     fmt_pct(ch.cagr_percent, 2), year=ch.end_year, scope=self.iso3, metric="cagr",
                                     kind="derived")
                    out["metrics"].append(self.metric_row(f"Compound annual growth {ch.start_year}-{ch.end_year}",
                                                          fmt_pct(ch.cagr_percent, 2), ch.end_year, fc, "derived"))
                    out["summary_points"].append(f"Compounded over {ch.start_year}-{ch.end_year}, the population grew "
                                                 f"{fmt_pct(ch.cagr_percent, 2)} per year [{fc}].")
            except CalculationError:
                pass
        if r:
            y0, v0, f0, y1, v1, f1 = r
            trend = "slowed" if v1 < v0 else "accelerated" if v1 > v0 else "was unchanged"
            pts = f"The source's annual growth rate was {fmt_pct(v1, 2)} in {y1} [{f1}]"
            if f0:
                pts += f", compared with {fmt_pct(v0, 2)} in {y0} [{f0}]: growth {trend}."
            out["summary_points"].insert(0, pts if pts.endswith(".") else pts + ".")
            if v1 < 0:
                out["notes"].append("A negative growth rate means the population is estimated to be shrinking.")
        out["table"] = self.table(["population_growth_pct"])
        out["notes"].append("WDI growth rates are exponential rates of change of midyear population.")
        return out

    def birth_death(self) -> dict:
        out = self.section("birth_death")
        b = self.first_last("birth_rate_per_1000", out)
        d = self.first_last("death_rate_per_1000", out)
        if b and d and b[3] == d[3]:
            y = b[3]
            ni = calc.natural_increase_per_1000(b[4], d[4])
            fn = self.fb.add(f"{self.name} rate of natural increase ({y})", ni, f"{ni:.1f} per 1,000", year=y,
                             scope=self.iso3, metric="natural_increase", kind="derived")
            out["metrics"].append(self.metric_row(f"Natural increase ({y})", f"{ni:.1f} per 1,000", y, fn, "derived"))
            out["summary_points"].append(
                f"In {y} the crude birth rate was {b[4]:.1f} per 1,000 [{b[5]}] and the crude death rate {d[4]:.1f} "
                f"per 1,000 [{d[5]}], giving natural increase of {ni:.1f} per 1,000 [{fn}] before migration.")
        elif b or d:
            out["notes"].append("Birth and death rates are not available for the same year; natural increase not computed.")
        out["table"] = self.table(["birth_rate_per_1000", "death_rate_per_1000"])
        if self.doc("vital"):
            out["citations"].append(self.doc("vital"))
        return out

    def fertility_life(self) -> dict:
        out = self.section("fertility_life")
        f = self.first_last("fertility_rate", out)
        le = self.first_last("life_expectancy_years", out)
        if f:
            out["summary_points"].append(
                f"The total fertility rate was {f[4]:.2f} births per woman in {f[3]} [{f[5]}]"
                + (f", down from {f[1]:.2f} in {f[0]} [{f[2]}]." if f[2] and f[4] < f[1] else
                   f", up from {f[1]:.2f} in {f[0]} [{f[2]}]." if f[2] and f[4] > f[1] else "."))
        if le:
            out["summary_points"].append(
                f"Life expectancy at birth was {le[4]:.1f} years in {le[3]} [{le[5]}]"
                + (f" compared with {le[1]:.1f} years in {le[0]} [{le[2]}]." if le[2] else "."))
        out["table"] = self.table(["fertility_rate", "life_expectancy_years"])
        if self.doc("vital"):
            out["citations"].append(self.doc("vital"))
        return out

    def age_structure(self) -> dict:
        out = self.section("age_structure")
        parts = {m: self.first_last(m, out) for m in ("age_0_14_pct", "age_15_64_pct", "age_65_plus_pct")}
        if all(parts.values()) and len({p[3] for p in parts.values()}) == 1:
            y = parts["age_0_14_pct"][3]
            dr = calc.dependency_ratio(parts["age_0_14_pct"][4], parts["age_15_64_pct"][4], parts["age_65_plus_pct"][4])
            fd = self.fb.add(f"{self.name} age dependency ratio ({y})", dr, f"{dr:.1f} per 100 working-age people",
                             year=y, scope=self.iso3, metric="dependency_ratio", kind="derived")
            out["metrics"].append(self.metric_row(f"Age dependency ratio ({y})", f"{dr:.1f} per 100", y, fd, "derived"))
            c, w, o = parts["age_0_14_pct"], parts["age_15_64_pct"], parts["age_65_plus_pct"]
            out["summary_points"].append(
                f"In {y}, {c[4]:.1f}% of the population was aged 0-14 [{c[5]}], {w[4]:.1f}% aged 15-64 [{w[5]}] and "
                f"{o[4]:.1f}% aged 65+ [{o[5]}]; there were {dr:.1f} dependants per 100 working-age people [{fd}].")
            if o[2] and c[2] and o[4] > o[1] and c[4] < c[1]:
                out["summary_points"].append(
                    f"The 65+ share rose from {o[1]:.1f}% in {o[0]} [{o[2]}] while the 0-14 share fell from {c[1]:.1f}% "
                    f"[{c[2]}], a pattern consistent with population ageing" + (f" [{self.doc('age')}]." if self.doc("age") else "."))
            out["chart"] = {"type": "bar", "title": f"{self.name}: age structure ({y})", "unit": "%",
                            "series": [{"name": "0-14", "value": c[4]}, {"name": "15-64", "value": w[4]},
                                       {"name": "65+", "value": o[4]}]}
        out["table"] = self.table(["age_0_14_pct", "age_15_64_pct", "age_65_plus_pct"])
        if self.doc("age"):
            out["citations"].append(self.doc("age"))
        return out

    def urban_rural(self) -> dict:
        out = self.section("urban_rural")
        u = self.first_last("urban_pct", out)
        r = self.first_last("rural_pct", out)
        if u:
            out["summary_points"].append(
                f"{u[4]:.1f}% of people lived in urban areas in {u[3]} [{u[5]}]"
                + (f", compared with {u[1]:.1f}% in {u[0]} [{u[2]}]." if u[2] else "."))
        if r:
            out["summary_points"].append(f"The rural share was {r[4]:.1f}% in {r[3]} [{r[5]}].")
        out["notes"].append("Urban areas are defined by each national statistical office, which limits cross-country comparison.")
        out["table"] = self.table(["urban_pct", "rural_pct"])
        if self.doc("age"):
            out["citations"].append(self.doc("age"))
        return out

    def density(self) -> dict:
        out = self.section("density")
        d = self.first_last("density_per_km2", out)
        if d:
            out["summary_points"].append(f"Average population density was {d[4]:,.1f} people per km² in {d[3]} [{d[5]}].")
        out["unavailable"].append("Sub-national geographic distribution")
        out["notes"].append("TerraPulse holds national figures only; distribution within the country cannot be described.")
        out["table"] = self.table(["density_per_km2"])
        out = {**out, "status": "partial" if d else "unavailable"}
        return out

    def migration(self) -> dict:
        out = self.section("migration")
        s = self.s("net_migration")
        if not s:
            return self.section("migration", status="unavailable", unavailable=["Net migration"],
                                notes=["Migration analysis is unavailable because the dataset has no net migration values "
                                       "for this country and period."])
        y = max(s)
        f1 = self.fact("net_migration", y, s[y])
        total = sum(s.values())
        ft = self.fb.add(f"{self.name} cumulative net migration {min(s)}-{y}", total, f"{total:+,.0f} people",
                         year=y, scope=self.iso3, metric="net_migration_cumulative", kind="derived")
        out["metrics"] += [self.metric_row(f"Net migration ({y})", fmt_metric("net_migration", s[y]), y, f1),
                           self.metric_row(f"Cumulative {min(s)}-{y} ({len(s)} years)", f"{total:+,.0f} people", y, ft, "derived")]
        direction = "net inflow" if s[y] > 0 else "net outflow" if s[y] < 0 else "balanced flows"
        out["summary_points"].append(f"Net migration in {y} was {s[y]:+,.0f} people ({direction}) [{f1}]; summed over "
                                     f"the available years it was {total:+,.0f} [{ft}].")
        out["notes"].append("Migration estimates carry large uncertainty and are often derived indirectly.")
        out["table"] = self.table(["net_migration"])
        if self.doc("migration"):
            out["citations"].append(self.doc("migration"))
        return out

    def comparison(self) -> dict:
        out = self.section("comparison")
        region_name = self.ctx.get("region_name") or "Region"
        metrics = ["population_growth_pct", "fertility_rate", "life_expectancy_years", "urban_pct", "age_65_plus_pct",
                   "birth_rate_per_1000"]
        rows, points = [], []
        for m in metrics:
            row = [METRIC_LABELS[m]]
            vals = {}
            for scope, nm, iso in (("country", self.name, self.iso3), ("region", region_name, "REG"),
                                   ("world", "World", "WLD")):
                ser = self.s(m, scope)
                if ser:
                    y = max(ser)
                    fid = self.fact(m, y, ser[y], scope_name=nm, scope=iso)
                    row.append(f"{fmt_metric(m, ser[y])} ({y})")
                    vals[scope] = (ser[y], fid, y)
                else:
                    row.append(UNAVAILABLE)
            rows.append(row)
            if "country" in vals and "world" in vals and vals["country"][2] == vals["world"][2]:
                rel = "higher than" if vals["country"][0] > vals["world"][0] else "lower than" \
                    if vals["country"][0] < vals["world"][0] else "equal to"
                points.append(f"{METRIC_LABELS[m]}: {fmt_metric(m, vals['country'][0])} [{vals['country'][1]}], "
                              f"{rel} the world figure of {fmt_metric(m, vals['world'][0])} [{vals['world'][1]}].")
        out["table"] = {"columns": ["Indicator", self.name, region_name, "World"], "rows": rows}
        out["summary_points"] = points[:4]
        cs = self.s("population_growth_pct")
        ws = self.s("population_growth_pct", "world")
        if cs and ws:
            series = [{"name": self.name, "points": [{"year": y, "value": v} for y, v in sorted(cs.items())]},
                      {"name": "World", "points": [{"year": y, "value": v} for y, v in sorted(ws.items())]}]
            rs = self.s("population_growth_pct", "region")
            if rs:
                series.insert(1, {"name": region_name, "points": [{"year": y, "value": v} for y, v in sorted(rs.items())]})
            out["chart"] = {"type": "line", "title": "Population growth rate (%)", "unit": "%", "series": series}
        out["notes"].append(f"Regional figures are World Bank aggregates for {region_name}.")
        if not self.ctx.get("region_series"):
            out["unavailable"].append("Regional aggregate")
        return out

    def projections(self) -> dict:
        return self.section(
            "projections", status="unavailable", unavailable=["Official population projections"],
            notes=["No official projection dataset (for example UN World Population Prospects projection variants) "
                   "has been imported into TerraPulse. Projections are therefore not shown, and TerraPulse does not "
                   "extrapolate historical trends into the future in reports."],
            citations=["S1"] + ([self.doc("projection")] if self.doc("projection") else []),
        )

    def key_findings(self, sections: dict[str, dict]) -> dict:
        out = self.section("key_findings")
        pts: list[str] = []
        for sid in ("current_population", "historical_trends", "growth_rate", "fertility_life", "age_structure",
                    "urban_rural", "migration"):
            if sid in sections and sections[sid]["summary_points"]:
                pts.append(sections[sid]["summary_points"][0])
        implications = []
        tfr = self.s("fertility_rate")
        if tfr and self.doc("vital"):
            y = max(tfr)
            fid = self.fact("fertility_rate", y, tfr[y])
            if tfr[y] < 2.1:
                implications.append(f"Fertility of {tfr[y]:.2f} births per woman [{fid}] is below the level of about 2.1 "
                                    f"commonly described as replacement fertility in low-mortality settings [{self.doc('vital')}]; "
                                    "without migration, this points towards slower growth or decline over time.")
            else:
                implications.append(f"Fertility of {tfr[y]:.2f} births per woman [{fid}] is above the level of about 2.1 "
                                    f"commonly described as replacement fertility [{self.doc('vital')}], which supports "
                                    "continued natural growth.")
        g = self.s("population_growth_pct")
        if g and g[max(g)] < 0:
            implications.append(f"The negative growth rate in {max(g)} indicates an estimated population decline.")
        out["summary_points"] = pts
        out["implications"] = implications
        out["notes"].append("Implications are rule-based interpretations of the figures above; they are not forecasts.")
        return out

    def sources_methodology(self, provenance: dict, documents: list[dict]) -> dict:
        out = self.section("sources_methodology")
        out["metrics"] = [
            self.metric_row("Dataset", provenance.get("dataset_name", UNAVAILABLE), None, None, "metadata"),
            self.metric_row("Publisher", provenance.get("publisher", UNAVAILABLE), None, None, "metadata"),
            self.metric_row("Release / version", provenance.get("release_version", UNAVAILABLE), None, None, "metadata"),
            self.metric_row("Licence", provenance.get("license", UNAVAILABLE), None, None, "metadata"),
            self.metric_row("Data reference date", str(provenance.get("reference_date") or UNAVAILABLE), None, None, "metadata"),
            self.metric_row("Imported", str(provenance.get("imported_at", ""))[:19], None, None, "metadata"),
            self.metric_row("Freshness", (provenance.get("freshness") or {}).get("status", "unknown"), None, None, "metadata"),
        ]
        out["summary_points"] = [
            "Historical values are midyear estimates published by the source; derived values (changes, compound growth, "
            "shares, ratios, ranks) are computed deterministically by TerraPulse from those estimates.",
            "AI-generated narrative, where present, explains these figures and is validated so that it cannot introduce "
            "numbers that are not in the evidence.",
            f"Uncertainty: {provenance.get('uncertainty_note', 'not quantified by the source')}",
            "Projections: no official projection dataset is loaded, so no projections are presented.",
        ]
        out["citations"] = ["S1"] + [d["label"] for d in documents]
        return out
