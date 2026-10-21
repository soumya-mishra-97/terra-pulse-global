"""Supervisor synthesis: attach citations, limitations and mode metadata to the answer."""

from __future__ import annotations

import re

from app.agents.nodes.common import AgentDeps, traced

OUT_OF_SCOPE = ("I can only help with population and demographic questions answered by TerraPulse's imported "
                "dataset and approved methodology documents. Try asking about a country's population trend, a "
                "comparison between countries, or how population estimates are produced.")


def make_finalize(deps: AgentDeps):
    @traced("finalize", "Supervisor Agent")
    def finalize(state: dict) -> dict:
        plan = state.get("plan")
        if plan is None:
            return {"answer": "The request could not be planned. Please rephrase your question.", "refused": True,
                    "mode": "fallback", "citations": [], "limitations": ["Planning failed."], "_status": "degraded"}
        if plan["intent"] == "out_of_scope":
            return {"answer": OUT_OF_SCOPE, "refused": True, "mode": "demo" if deps.llm is None else "claude",
                    "citations": [], "limitations": ["Question is outside the supported demographic scope."],
                    "_detail": "out of scope: refused without calling tools"}

        answer = state.get("answer", "")
        prov = state.get("provenance") or {}
        docs = state.get("documents") or []
        cited = set(re.findall(r"\b(D\d+)\b", answer))
        citations = []
        if prov:
            citations.append({"label": "S1", "kind": "dataset", "title": prov.get("dataset_name"),
                              "publisher": prov.get("publisher"), "url": prov.get("landing_page") or prov.get("source_url"),
                              "published": prov.get("release_version"), "reference_date": prov.get("reference_date"),
                              "license": prov.get("license")})
        for d in docs:
            if not cited or d["label"] in cited:
                citations.append({"label": d["label"], "kind": "document", "title": d["title"], "publisher": d["publisher"],
                                  "url": d["source_url"], "published": d["published"], "section": d["heading"]})

        limitations = []
        if prov:
            limitations.append(prov.get("uncertainty_note") or "Uncertainty not quantified by the source.")
            limitations.append("Figures are midyear estimates with a reference date, not real-time counts.")
            if (prov.get("freshness") or {}).get("status") == "stale":
                limitations.append("The dataset is stale relative to TerraPulse's freshness threshold.")
            if prov.get("is_synthetic"):
                limitations.append("DEMO DATA: values are synthetic and must not be used as statistics.")
        for c in (state.get("evidence") or {}).get("checks", []):
            if not c["passed"]:
                limitations.append(c["detail"])
        mode = state.get("mode", "demo")
        if mode == "demo":
            limitations.append("Demo mode: no LLM configured; the answer is a deterministic template.")
        elif mode == "fallback":
            limitations.append("The AI explanation was unavailable or failed validation; a deterministic answer is shown.")
        return {"citations": citations, "limitations": list(dict.fromkeys(limitations)), "refused": False,
                "_detail": f"{len(citations)} citation(s), mode={mode}"}

    return finalize
