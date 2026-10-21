"""Copilot evaluation harness.

    python -m evals.run_evals                 # demo mode (no LLM), against the local database
    ANTHROPIC_API_KEY=... python -m evals.run_evals --llm   # exercises Claude (costs tokens)

Each case is scored on the checks listed in its "expect" block. Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from app.config import get_settings
from app.db import get_session_factory
from app.integrations.llm import build_llm
from app.knowledge.retriever import BM25Retriever
from app.repositories.population import PopulationRepository
from app.schemas.copilot import ChatResponse
from app.services.copilot import CopilotService

CASES = Path(__file__).with_name("copilot_cases.json")


def evaluate_case(case: dict, out: ChatResponse, db_value) -> list[tuple[str, bool, str]]:
    """Return (check, passed, detail) tuples. `db_value(scope, metric, year)` reads the authoritative value."""
    e = case["expect"]
    results: list[tuple[str, bool, str]] = []
    plan = out.plan or {}
    if "intent" in e:
        results.append(("intent", plan.get("intent") == e["intent"], f"got {plan.get('intent')}"))
    if "countries" in e:
        results.append(("countries", plan.get("countries") == e["countries"], f"got {plan.get('countries')}"))
    if e.get("output_valid"):
        ok = bool((out.validation.get("output") or {}).get("passed"))
        results.append(("output_valid", ok, json.dumps((out.validation.get("output") or {}).get("unsupported_numbers"))))
    if e.get("cites_dataset"):
        results.append(("cites_dataset", any(c.kind == "dataset" for c in out.citations), ""))
    if "cites_document" in e:
        titles = [c.title for c in out.citations if c.kind == "document"]
        results.append(("cites_document", e["cites_document"] in titles, f"got {titles}"))
    for phrase in e.get("forbidden", []):
        results.append((f"forbidden:{phrase}", phrase.lower() not in out.answer.lower(), ""))
    if "forbidden_regex" in e:
        results.append(("forbidden_regex", not re.search(e["forbidden_regex"], out.answer), ""))
    if "refused" in e:
        results.append(("refused", out.refused == e["refused"], f"refused={out.refused}"))
    if e.get("not_answered_with_numbers"):
        results.append(("no_numbers_for_unknown_entities", out.refused or not out.facts or
                        all(f.scope == "WLD" for f in out.facts), f"facts={[f.scope for f in out.facts][:5]}"))
    if e.get("insufficient_evidence"):
        ok = not (out.validation.get("evidence") or {}).get("sufficient", True) and "can't answer" in out.answer
        results.append(("insufficient_evidence_declared", ok, out.answer[:80]))
    if "mentions_missing" in e:
        results.append(("limitation_mentions_missing", any(e["mentions_missing"] in x for x in out.limitations),
                        f"limitations={out.limitations[-2:]}"))
    if "fact_matches_db" in e:
        spec = e["fact_matches_db"]
        facts = [f for f in out.facts if f.scope == spec["scope"] and f.metric == spec["metric"]]
        ok = bool(facts) and all(abs(f.value - db_value(f.scope, f.metric, f.year)) < 1e-6 for f in facts)
        results.append(("fact_matches_db", ok, f"{len(facts)} fact(s) checked"))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="use Claude if ANTHROPIC_API_KEY is configured")
    args = parser.parse_args()
    settings = get_settings()
    llm = build_llm(settings) if args.llm else None
    if args.llm and llm is None:
        print("--llm requested but no ANTHROPIC_API_KEY configured", file=sys.stderr)
        return 2
    retriever = BM25Retriever.from_directory(settings.methodology_dir)
    cases = json.loads(CASES.read_text())
    failures = 0
    by_cat: dict[str, list[bool]] = {}
    with get_session_factory()() as s:
        repo = PopulationRepository(s)
        src = repo.active_source()

        def db_value(scope, metric, year):
            return repo.series(src.id, scope, metric, year, year).get(year)

        for case in cases:
            out = CopilotService(s, settings, retriever, llm).ask(case["question"], "eval-runner")
            res = evaluate_case(case, out, db_value)
            passed = all(ok for _, ok, _ in res)
            by_cat.setdefault(case["category"], []).append(passed)
            failures += not passed
            print(f"[{'PASS' if passed else 'FAIL'}] {case['id']:16} mode={out.mode:8} {case['question'][:60]}")
            for name, ok, detail in res:
                if not ok:
                    print(f"        x {name}: {detail}")
    print("\nSummary by category:")
    for cat, vals in by_cat.items():
        print(f"  {cat:22} {sum(vals)}/{len(vals)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
