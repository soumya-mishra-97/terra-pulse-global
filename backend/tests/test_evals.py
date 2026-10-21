"""Run the eval scorer against the synthetic fixture so evaluation logic itself is tested in CI."""

import pytest

from app.knowledge.retriever import BM25Retriever
from app.repositories.population import PopulationRepository
from app.services.copilot import CopilotService
from evals.run_evals import evaluate_case

CASES = [
    {"id": "g", "category": "groundedness", "question": "Compare India and Pakistan population growth since 2015",
     "expect": {"intent": "compare", "countries": ["IND", "PAK"], "output_valid": True, "cites_dataset": True}},
    {"id": "n", "category": "numeric_consistency", "question": "What is the world population right now?",
     "expect": {"intent": "world", "fact_matches_db": {"scope": "WLD", "metric": "population_total"}}},
    {"id": "s", "category": "source_correctness", "question": "How is net migration measured and how uncertain is it?",
     "expect": {"intent": "methodology", "cites_document": "Net migration: definition and limitations"}},
    {"id": "r", "category": "refusal", "question": "Who will win the next football world cup?", "expect": {"refused": True}},
    {"id": "i", "category": "refusal", "question": "What is the population of Atlantis?",
     "expect": {"insufficient_evidence": True, "not_answered_with_numbers": True}},
    {"id": "m", "category": "refusal", "question": "Compare the population of India and Narnia.",
     "expect": {"countries": ["IND"], "mentions_missing": "Narnia"}},
]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eval_case(case, factory, loaded, settings):
    with factory() as s:
        repo = PopulationRepository(s)
        src = repo.active_source()
        out = CopilotService(s, settings, BM25Retriever.from_directory(settings.methodology_dir), None).ask(
            case["question"], "eval")
        results = evaluate_case(case, out, lambda sc, m, y: repo.series(src.id, sc, m, y, y).get(y))
    failed = [r for r in results if not r[1]]
    assert not failed, failed
