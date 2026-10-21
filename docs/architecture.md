# Architecture, service boundaries and operations

Status: describes the code in this repository as of 2026-10-21. Decision record: [ADR-001](adr/ADR-001-modular-monolith.md).

## 1. Shape of the system

TerraPulse is a **modular monolith**: one FastAPI process, one PostgreSQL database, one React SPA. Modules talk
through Python interfaces, not the network, but each has an explicit contract and owns its tables, so it can be
extracted later without rewriting callers.

```
React SPA ──HTTP /api──► API / BFF (app/api) ──► Application services (app/services)
                                                   │            │              │
                                    Population & Demographic   AI Copilot /    Reports
                                    Data (domain, repos)       Orchestration   (report graph, exports)
                                                   ▲            │      │
                                    Data Ingestion ┘   Knowledge/RAG  Claude (LangChain)
                                    (CLI, importer)    (retriever)    integration
                                                   │
                                               PostgreSQL (source of truth)   File storage (local / S3)
```

Dependency rule: `domain` imports nothing from the web, database or LLM layers. `repositories` depend on `domain`.
`services` depend on both. `agents` depend on services through `DataTools` and never on the ORM directly. `api`
depends on services. A test enforces the domain rule indirectly: `tests/test_calculations.py` imports only
`app.domain`.

## 2. Module contracts

| Module | Owns (tables) | Public contract (in-process today) | Must not |
|---|---|---|---|
| **API / BFF** (`app/api`) | — | REST under `/api/v1`, Pydantic schemas, error envelope, `X-Request-ID`, identity, rate limits | Contain business rules or SQL |
| **Population & Demographic Data** (`app/domain`, `app/services/population.py`, `app/repositories/population.py`) | `countries`, `country_baselines`, `population_estimates`, `data_sources` (read) | `PopulationService.world_summary()`, `countries()`, `history()`, `regions()`, `country_profile()`, `series()`, `provenance()` | Call an LLM; mutate data |
| **Data Ingestion** (`app/ingestion`) | `data_sources` (write), `country_baselines` (write), `population_estimates` (write), `calculation_runs`, `source_events` | `import_snapshot(factory, dir, options) -> ImportResult`; CLI `bootstrap`, `import-snapshot`, `sources` | Serve user traffic |
| **AI Copilot / Agent Orchestration** (`app/agents`, `app/services/copilot.py`, `app/services/reports.py`) | `agent_runs`, `country_reports`, `report_sources`, `report_generation_runs`, `audit_logs` (append) | `CopilotService.ask(question, user) -> ChatResponse`; `ReportService.create/get/list/download/delete` | Write population tables; compute authoritative numbers in the LLM |
| **Knowledge / RAG** (`app/knowledge`) | Approved document files (`data/methodology/*.md`) | `Retriever.retrieve(query, k) -> list[RetrievedChunk]` (sanitised, labelled) | Return unapproved or unsanitised text |

## 3. When to extract a service (and when not to)

Do **not** split into deployed microservices without a concrete reason. Today there is none: one team, one
deployable, low traffic, and SQLite or PostgreSQL handle the load. The extraction triggers, and what each would look
like:

| Candidate | Trigger that would justify extraction | Shape after extraction |
|---|---|---|
| **Data Ingestion** | Imports become large or scheduled (several datasets, nightly), or need credentials the API must not hold | Batch worker or job writing to the same DB under its own role. It emits a `dataset.published` event; the API invalidates caches. |
| **AI Orchestration** | LLM latency or cost must scale independently; GPU/egress isolation; separate security boundary for prompts | `copilot-svc` exposing `POST /v1/copilot/runs` and `POST /v1/reports/jobs`. It reads population data **only through the Population API**, never directly from the tables. |
| **Population Data API** | Several consumers (external partners, other products) | Read-only service in front of the curated tables; versioned REST; aggressive caching (data changes per release). |
| **Knowledge / RAG** | Corpus grows to embeddings plus a vector store with its own refresh cadence | `knowledge-svc` with `POST /v1/search`, behind the same `Retriever` protocol. |

### Contracts if extracted

* **REST:** JSON with explicit versions (`/v1`), the same Pydantic models published as OpenAPI, and the same error
  envelope `{error: {status, title, detail, request_id}}`.
* **Events (only once there are two or more consumers):** `dataset.published {source_id, snapshot_id, checksum,
  reference_date}`, `report.completed {report_id, owner_id}`. Use an outbox table written in the same transaction
  as the state change, delivered at-least-once, with consumers idempotent on `event_id`.
* **Idempotency:** `Idempotency-Key` on every POST that creates work (already implemented for reports). Imports are
  idempotent by snapshot checksum.
* **Timeouts and retries:** callers set per-hop timeouts below the caller's own deadline. Retry only idempotent
  calls, at most two times, with jittered exponential backoff. LLM calls keep their own bounded retries.
* **Circuit breakers:** around the Claude call and any cross-service call. Open after 5 consecutive failures, wait
  30 s, then half-open. While open, the Copilot answers in `fallback` mode, which is already implemented.
* **Tracing:** propagate `X-Request-ID` (already done in-process) and W3C `traceparent`. Every log line already
  carries `correlation_id`.
* **Data ownership:** exactly one service writes each table (see section 2). Others read through APIs or a
  read replica. No shared writes after extraction.

## 4. Database guidance (applied)

* PostgreSQL is the source of truth for curated estimates, provenance (`data_sources`, `source_events`), agent
  runs and audit logs.
* Schema changes go only through Alembic (`migrations/`). A test checks ORM-vs-migration drift.
* Indexes: `(source_id, country_iso3, metric, year)`, `(source_id, metric, year)`, `(owner_id, created_at)` for
  report history, `(entity_type, entity_id)` for audit.
* Transactions: an import is one transaction and baseline replacement is atomic. Report state changes use short
  transactions. Rejection events are written in a separate transaction so they survive the rollback.
* Repository abstraction: all SQL lives in `app/repositories`, built with SQLAlchemy expressions (bound parameters).
* Secrets: `.env` locally (git-ignored); a managed secret store (AWS Secrets Manager, GCP Secret Manager, Vault)
  injected as environment variables in deployment. Use a separate DB role per future service.

## 5. Threat model (STRIDE, MVP scope)

| Threat | Vector | Current mitigation | Gap / next step |
|---|---|---|---|
| **Spoofing** | Forge `X-User-Id` to read another user's reports | Header format validated; reports are owner-scoped (404 otherwise) | **Open (High for production):** the header is not authentication. Replace with OIDC/JWT verification. |
| **Tampering** | Edited snapshot files | SHA-256 per file checked against the manifest; snapshot checksum unique | Sign manifests if snapshots come from third parties |
| **Tampering** | Prompt injection via retrieved documents | Approved-only corpus, line-level sanitiser, `<document>` delimiters, system-prompt rule, numeric/citation output guard | Add provenance signatures for documents once the corpus is external |
| **Tampering** | Prompt injection via the user question | The LLM can only pick deterministic tools; plans are validated; output numbers are checked | — |
| **Repudiation** | Deny generating or deleting a report | `audit_logs` for request, completion, download and delete, with correlation ID | Ship audit logs to append-only storage |
| **Information disclosure** | API key leakage | Server-only `SecretStr`, log redaction, not in API responses or the bundle | Use a secret manager in deployment |
| **Information disclosure** | Path traversal on downloads or docs | Strict ID regex, server-generated keys, root-confined resolution, whitelisted doc slugs and image names | — |
| **Denial of service** | Expensive Copilot or report requests | Per-user rate limits, active-job cap, LLM timeouts, `max_tokens`, workflow deadline, recursion limit | In-process limits only; move to a gateway or Redis for multiple replicas |
| **Elevation of privilege** | Mass assignment or SQL injection | Pydantic schemas with enums and regexes; ORM-bound parameters | — |

## 6. Failure modes

| Failure | Behaviour |
|---|---|
| No dataset imported | API returns `503 Data unavailable` with instructions; UI shows an empty state |
| Data stale | Served, but flagged `stale` in API, UI, Copilot limitations and report validation |
| Claude unavailable, timeout or refusal | Copilot answers with the deterministic template (`mode=fallback`); reports omit narrative |
| LLM output ungrounded | One regeneration with feedback, then template; report paragraphs are dropped individually |
| Retrieval returns nothing | Research retried once with a broadened query; methodology questions then report insufficient evidence |
| One report section builder throws | That section is `unavailable` with a note; the report completes |
| Essential integrity check fails | Report `blocked`, not published, downloads return 409 |
| API restarts mid-job | On startup, `queued`/`running` reports are marked `failed` with a regenerate hint |
| Transient DB error during a job | Up to `REPORT_MAX_ATTEMPTS` attempts, each recorded in `report_generation_runs` |
| Unhandled exception | 500 with a user-safe message and request ID; full stack trace in logs only |

## 7. Observability plan

* **Logs:** JSON lines (`app/observability.py`) with `correlation_id`, route template, status and latency; agent
  nodes log `node`, `agent`, `status` and `latency_ms`; secret-like keys are redacted.
* **Correlation:** `X-Request-ID` is accepted (validated) or generated, echoed in responses and error bodies,
  propagated into background report jobs, and stored on `agent_runs`, `audit_logs` and `report_generation_runs`.
* **Metrics:** `GET /api/v1/metrics` exposes counters and p50/p95 latencies (HTTP by route, agent nodes, LLM calls
  and errors, Copilot mode, report outcomes). Next step: an OpenTelemetry exporter to Prometheus/Grafana.
* **Audit:** `agent_runs` (plan, trace, validation, mode, model, latency) and `audit_logs` (report lifecycle).
* **Suggested alerts:** LLM error rate above 10% over 5 minutes; `copilot.mode.fallback` share above 20%; report
  failure rate above 5%; p95 Copilot latency above 30 s; dataset `stale`.

## 8. Tests that protect these boundaries

* Domain purity and calculation correctness: `tests/test_calculations.py`
* Ingestion contract (rejects, duplicates, coverage, replacement, staleness): `tests/test_ingestion.py`
* Migrations versus ORM: `tests/test_migrations.py`
* API contract and error envelope: `tests/test_api.py`
* Agent workflow, injection and LLM failure: `tests/test_agents.py`; evals in `tests/test_evals.py` and `evals/`
* Reports (exports, authorisation, idempotency, partial failure): `tests/test_reports.py`
