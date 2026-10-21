"""Validation Agent: rule-based checks before generation (evidence) and after it (output)."""

from __future__ import annotations

import re

from app.agents.nodes.common import AgentDeps, traced
from app.agents.numeric_guard import check_citations, check_numbers

MAX_RESEARCH_ATTEMPTS = 2
MAX_GENERATION_ATTEMPTS = 2


def make_evidence_validator(deps: AgentDeps):
    @traced("evidence_validator", "Validation Agent")
    def evidence_validator(state: dict) -> dict:
        plan = state["plan"]
        data = state.get("data") or {}
        prov = state.get("provenance") or {}
        facts = state.get("facts") or []
        docs = state.get("documents") or []
        checks = []

        def check(name: str, ok: bool, detail: str, severity: str = "error") -> None:
            checks.append({"name": name, "passed": ok, "detail": detail, "severity": severity if not ok else "info"})

        if plan.get("unresolved"):
            check("entities_resolved", False,
                  f"not found in the dataset: {', '.join(plan['unresolved'])}",
                  severity="error" if not plan.get("countries") else "warning")
        if plan["needs_data"]:
            check("data_available", not data.get("error"), data.get("error") or "dataset reachable")
            check("facts_present", bool(facts), f"{len(facts)} deterministic facts")
            check("provenance_present", bool(prov.get("release_version") and prov.get("reference_date")),
                  f"{prov.get('dataset_name', 'unknown')} release {prov.get('release_version', '?')}")
            fresh = (prov.get("freshness") or {}).get("status")
            check("data_fresh", fresh != "stale", f"freshness={fresh}", severity="warning")
            check("not_synthetic", not prov.get("is_synthetic"), "synthetic demo data in use", severity="warning")
            for issue in data.get("issues", []):
                check("comparability", False, issue, severity="warning")
        if plan["needs_research"]:
            check("documents_present", bool(docs), f"{len(docs)} approved passages",
                  severity="error" if plan["intent"] == "methodology" else "warning")
            flagged = [line for d in docs for line in d.get("flagged_lines", [])]
            check("retrieval_injection_scan", not flagged,
                  f"{len(flagged)} instruction-like line(s) removed from retrieved text" if flagged else "clean",
                  severity="warning")
        errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
        retry = (plan["needs_research"] and not docs and state.get("research_attempts", 0) < MAX_RESEARCH_ATTEMPTS)
        sufficient = not errors
        evidence = {"sufficient": sufficient, "checks": checks, "retry_research": retry}
        return {"evidence": evidence, "_status": "ok" if sufficient else "degraded",
                "_detail": "sufficient" if sufficient else f"insufficient: {', '.join(c['name'] for c in errors)}"
                + (" -> retrying research" if retry else "")}

    return evidence_validator


def validate_answer(state: dict) -> dict:
    answer = state.get("answer", "")
    facts = state.get("facts") or []
    docs = state.get("documents") or []
    plan = state.get("plan") or {}
    years = {f["year"] for f in facts if f.get("year")}
    years |= {y for y in (plan.get("start_year"), plan.get("end_year")) if y}
    years |= {int(y) for y in re.findall(r"\b(19[5-9]\d|20\d\d)\b", state.get("question", ""))}
    prov = state.get("provenance") or {}
    context = [d["text"] for d in docs] + [state.get("question", ""), str(prov.get("release_version", ""))]
    num = check_numbers(answer, [f["value"] for f in facts], years, context)
    labels = {f["id"] for f in facts} | {d["label"] for d in docs} | {"S1"}
    bad_cites = check_citations(answer, labels)
    passed = num.passed and not bad_cites
    feedback = []
    if num.unsupported:
        feedback.append(f"These numbers are not in the facts and must be removed: {', '.join(num.unsupported[:8])}.")
    if bad_cites:
        feedback.append(f"These citation ids do not exist: {', '.join(bad_cites)}.")
    feedback += [f"Problem: {i}." for i in num.issues]
    return {"passed": passed, "numbers_checked": num.checked, "unsupported_numbers": num.unsupported,
            "invalid_citations": bad_cites, "issues": num.issues, "feedback": " ".join(feedback)}


def make_output_validator(deps: AgentDeps):
    @traced("output_validator", "Validation Agent")
    def output_validator(state: dict) -> dict:
        result = validate_answer(state)
        update: dict = {"output_validation": result}
        if result["passed"]:
            update["_detail"] = f"passed ({result['numbers_checked']} numbers checked)"
            return update
        if state.get("mode") == "claude" and state.get("generation_attempts", 0) < MAX_GENERATION_ATTEMPTS:
            update["generation_feedback"] = result["feedback"]
            update["_status"], update["_detail"] = "degraded", "failed -> asking responder to regenerate"
            return update
        # Out of retries: replace the LLM text with the deterministic template.
        from app.agents.nodes.responder import template_answer

        update["answer"] = template_answer(state)
        update["mode"] = "fallback" if state.get("mode") == "claude" else state.get("mode")
        update["output_validation"] = {**result, "replaced_with_template": True}
        update["_status"], update["_detail"] = "degraded", "failed twice -> deterministic template used"
        return update

    return output_validator
