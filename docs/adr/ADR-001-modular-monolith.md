# ADR-001: Start as a modular monolith; extract services only on evidence

* **Status:** Accepted
* **Date:** 2026-10-21

## Context

TerraPulse combines five concerns: an API/BFF, population data, data ingestion, AI agent orchestration, and a
knowledge/RAG layer. The team is small, traffic is low, and the dataset changes once per release. The agent
workflows need low-latency access to population data and must be easy to test end to end.

## Decision

1. Ship **one FastAPI deployable** with strict internal module boundaries (see `docs/architecture.md` §2).
2. Agents are **logical components inside one LangGraph workflow**, not separate services.
3. **PostgreSQL is the single source of truth.** Each table has exactly one owning module.
4. Background report jobs run in an **in-process thread pool** with persisted status. No message broker,
   Kubernetes or vector database in the MVP.
5. External boundaries are defined as interfaces now (`Retriever`, `LLMClient`, `Storage`), so swapping in
   pgvector, a different model client, or S3 needs no caller changes.

## Consequences

* **Positive:** one build, one deploy, one trace; agent workflows are testable with an in-memory fake LLM; no
  distributed transactions.
* **Negative:** rate limits and the job queue are per-process, so horizontal scaling needs Redis or a queue first.
  The API process also carries LLM latency, mitigated by timeouts, a deadline and per-user limits.
* **Revisit when:** a trigger in `docs/architecture.md` §3 is met (independent scaling of LLM work, scheduled
  multi-dataset ingestion, multiple consumers of the data API, or separate team ownership).

## Alternatives considered

* **Microservice per agent:** rejected. It adds network hops, retries and distributed tracing for no scaling benefit,
  and makes the validation loops (research retry, regeneration) cross-service.
* **Celery + Redis for reports now:** rejected for the MVP. Generation takes under 2 s in demo mode; the
  thread pool plus persisted status meets the requirement without simulating anything. Reconsider when running more
  than one replica.
