"""Render the structured report content as Markdown. All dynamic text is escaped."""

from __future__ import annotations

import re

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+!|])")


def esc(text: object) -> str:
    """Escape Markdown/HTML control characters so data or LLM text cannot inject markup or links."""
    s = str(text if text is not None else "")
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = _MD_SPECIAL.sub(r"\\\1", s)
    return " ".join(s.split()) if "\n" not in s else s


def _cite(text: str) -> str:
    # escape everything, then restore our own citation markers like \[F3\] -> [F3]
    return re.sub(r"\\\[((?:[FDS]\d+(?:, )?)+)\\\]", r"[\1]", esc(text))


def render_markdown(content: dict) -> str:
    c = content["country"]
    prov = content.get("provenance") or {}
    out = [f"# {esc(content['title'])}", ""]
    out.append(f"**Country:** {esc(c['name'])} ({esc(c['iso3'])})  ")
    out.append(f"**Reporting period:** {esc(content['period']['label'])} "
               f"({content['period']['start_year']}–{content['period']['end_year']})  ")
    out.append(f"**Generated:** {esc(content['generated_at'])}  ")
    out.append(f"**Data reference date:** {esc(content.get('data_reference_date') or 'Data unavailable')}  ")
    out.append(f"**Source:** {esc(prov.get('dataset_name'))}, {esc(prov.get('publisher'))}, release "
               f"{esc(prov.get('release_version'))} [S1]  ")
    mode = content.get("mode")
    out.append(f"**Narrative mode:** {esc(mode)}" + (f" ({esc(content.get('model'))})" if content.get("model") else ""))
    out += ["", f"> {esc(content['disclaimer'])}", "", "## Contents", ""]
    for s in content["sections"]:
        anchor = re.sub(r"[^a-z0-9]+", "-", s["title"].lower()).strip("-")
        out.append(f"{s['number']}. [{esc(s['title'])}](#{s['number']}-{anchor})")
    out.append("")
    for s in content["sections"]:
        out.append(f"## {s['number']}. {esc(s['title'])}")
        if s["status"] != "ok":
            out.append(f"*Status: {esc(s['status'])}*")
        out.append("")
        if s.get("narrative"):
            out += [_cite(s["narrative"]), "", "*AI-generated explanation, validated against the figures below.*", ""]
        for p in s.get("summary_points", []):
            out.append(f"- {_cite(p)}")
        for p in s.get("implications", []):
            out.append(f"- {_cite(p)}")
        if s.get("summary_points") or s.get("implications"):
            out.append("")
        if s.get("metrics"):
            out += ["| Metric | Value | Basis |", "|---|---|---|"]
            for m in s["metrics"]:
                basis = esc(m["kind"]) + (f" [{m['fact_id']}]" if m.get("fact_id") else "")
                out.append(f"| {esc(m['label'])} | {esc(m['value'])} | {basis} |")
            out.append("")
        t = s.get("table")
        if t:
            out.append("| " + " | ".join(esc(x) for x in t["columns"]) + " |")
            out.append("|" + "---|" * len(t["columns"]))
            for row in t["rows"]:
                out.append("| " + " | ".join(esc(x) for x in row) + " |")
            out.append("")
        for u in s.get("unavailable", []):
            out.append(f"- **Data unavailable:** {esc(u)}")
        for n in s.get("notes", []):
            out.append(f"- *Note:* {esc(n)}")
        if s.get("citations"):
            out.append(f"\nSources: {', '.join('[' + esc(x) + ']' for x in s['citations'])}")
        out.append("")
    out += ["## References", ""]
    for src in content.get("sources", []):
        out.append(f"- [{esc(src['label'])}] {esc(src['title'])}. {esc(src.get('publisher'))}. "
                   f"{esc(src.get('published'))}. {esc(src.get('url'))}")
    out += ["", "## Limitations", ""] + [f"- {esc(x)}" for x in content.get("limitations", [])]
    v = content.get("validation") or {}
    out += ["", "## Validation", "", f"Overall status: **{esc(v.get('status'))}**", ""]
    for ch in v.get("checks", []):
        out.append(f"- {'✔' if ch['passed'] else '✖'} {esc(ch['name'])}: {esc(ch['detail'])}")
    out.append("")
    return "\n".join(out)
