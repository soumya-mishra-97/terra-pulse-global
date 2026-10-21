# Production-readiness review

* **Scope:** this repository as of 2026-10-21 (backend, frontend, migrations, Docker files).
* **Method:** code reading, the automated suite (105 backend tests, 4 frontend tests, 12 evals), and targeted manual
  requests against a running API.

> **Verdict:** a solid MVP with honest data handling and strong numeric grounding. It is **not production-ready**,
> mainly because there is no real authentication and the job queue and rate limits are in-process. No security
> certification is claimed.

## 1. Checklist

| Question | Answer | Evidence |
|---|---|---|
| Are domain calculations independent of the web framework and LLM? | **Yes** | `app/domain/*` imports only the standard library and `app.domain`; `tests/test_calculations.py` exercises it alone |
| Can every population figure be traced to a dated, versioned source? | **Yes** | `country_baselines.source_id` → `data_sources` (release, checksum, retrieved_at); API `provenance` on every data response; report `sources` plus `[S1]` |
| Are demo values visibly marked in the UI and API? | **Yes** | `is_synthetic` → `data_label="DEMO DATA…"`, red *Demo data* tag in the banner and reports; demo **LLM mode** labelled on every answer |
| Can LLM text alter numeric facts or make unsupported claims? | **No for numbers; partly for wording** | Facts come only from `analysis.py`/`builder.py`; `numeric_guard.check_numbers` and citation checks; see O6 for the residual risk |
| Are request and response payloads validated? | **Yes** | Pydantic schemas with enums and regexes; `response_model` on every route; 422 envelope |
| Timeouts, bounded retries, graceful degradation, user-safe errors? | **Mostly** | LLM timeout and retries, workflow deadline, one regeneration, template fallback, error envelope without stack traces; see O4 for worst-case latency |
| Secrets excluded from source control and frontend bundles? | **Yes** | `.gitignore` covers `.env*`; key is a `SecretStr` read server-side; `grep` of `frontend/dist` finds only UI text mentioning the variable name |
| SQL parameterised, writes transactional? | **Yes** | SQLAlchemy expressions only; `factory.begin()` units of work; import is all-or-nothing |
| Tests cover normal, boundary, stale, malformed and dependency-failure cases? | **Yes** | See README → Testing; LLM timeout and refusal, failed node, blocked report, checksum tampering, stale data |
| Structured logging, correlation IDs, metrics, audit metadata? | **Yes (in-process)** | JSON logs with `correlation_id`; `X-Request-ID`; `/api/v1/metrics`; `agent_runs`, `audit_logs`, `report_generation_runs` |
| Citations and uncertainty displayed honestly? | **Yes** | Provenance banner, "Uncertainty not quantified by the source", `Data unavailable`, projections explicitly unavailable |

## 2. Findings fixed during this review

| ID | Severity | Finding | Reproduction (before fix) | Fix | Regression test |
|---|---|---|---|---|---|
| F1 | **High** (correctness) | History endpoint truncated the path parameter to 3 characters | `GET /api/v1/population/countries/INDONESIA/history` returned **India** (`IND`) | `Path(pattern="^[A-Za-z]{3}$")`, no truncation | `test_history_rejects_non_iso3_instead_of_truncating` |
| F2 | Medium (correctness) | Copilot answered "population of Atlantis" with world figures | Eval `insufficient-01` showed `facts` scoped to `WLD` | Planner records unresolved named entities; Validation Agent marks evidence insufficient | eval `insufficient-01/02`, `tests/test_evals.py::i,m` |
| F3 | Medium (performance) | Report rank computation rebuilt the country set per row (one query per row, about 300) | `report_graph.country_data` generator expression | Compute the set once | Covered functionally by `tests/test_reports.py` |
| F4 | Medium (reliability) | Deadline check used fixed 8–20 s margins unrelated to the LLM timeout | `responder` called the LLM with 8 s left and a 45 s timeout | Require `time_left > llm_timeout_seconds` (responder) and `2×` (planner); deadline raised to 150 s | `test_llm_failure_degrades_gracefully` |
| F5 | Medium (grounding) | The ranking eligibility threshold ("1 million") failed the numeric guard in demo mode | `output_validator` replaced a correct answer with the template | Register parameters as `kind="parameter"` facts | `test_ranking_uses_same_reference_years` |
| F6 | Low (security hygiene) | Markdown export only backslash-escaped `<`/`>` | `esc("<img src=x>")` → `\<img…` | HTML-entity encode `<`, `>`, `&` | `test_markdown_escapes_untrusted_text` |

## 3. Open findings (prioritised)

### O1. High: identity is a spoofable header
* **Evidence:** `app/api/deps.py::current_user` trusts `X-User-Id`. `curl -H 'X-User-Id: alice' /api/v1/reports`
  lists Alice's reports from any client.
* **Impact:** anyone can read or delete another user's reports, and per-user rate limits can be dodged by rotating the header.
* **Fix plan:** add an OIDC/JWT dependency (`pyjwt` with JWKS caching): verify `iss`, `aud`, `exp` and signature,
  and map `sub` to `owner_id`. Keep the demo header only when `AUTH_MODE=demo` *and* `APP_ENV=local`. Rate-limit by
  `sub` and IP.
* **Tests to add:** missing or invalid token → 401; expired → 401; valid token for another `sub` → 404 on
  get/download/delete; demo header ignored when `APP_ENV=production`.

### O2. Medium: PostgreSQL is not exercised by the test suite
* **Evidence:** fixtures use SQLite. PostgreSQL DDL was only rendered offline (`alembic upgrade head --sql`, which
  produces JSONB and BIGSERIAL as expected).
* **Fix plan:** CI job with a `postgres:16` service, running the whole suite with `DATABASE_URL` pointed at it.
* **Tests to add:** parameterise the `settings` fixture on `TEST_DATABASE_URL`.

### O3. Medium: in-process rate limiter and job executor
* **Evidence:** `RateLimiter` and `ThreadPoolExecutor` live in process memory. Interrupted jobs are marked failed
  at startup, not resumed.
* **Fix plan (only when running more than one replica):** Redis-backed limiter at the gateway, plus a
  PostgreSQL `SKIP LOCKED` job table or Arq/RQ worker; the status model stays the same.
* **Tests to add:** two app instances sharing a limiter; a job claimed exactly once.

### O4. Medium: worst-case Copilot latency exceeds the nominal timeout
* **Evidence:** the Anthropic SDK retries up to `LLM_MAX_RETRIES` times, so one call can take about
  `timeout × (retries + 1)` = 135 s. The planner and responder may each make a call.
* **Fix plan:** use `LLM_MAX_RETRIES=1` on the interactive path, keep 2 for background reports, and enforce a total
  per-request budget with a wall-clock timeout around `graph.invoke`.
* **Tests to add:** a fake LLM that sleeps past the budget → answer in `fallback` within the budget.

### O5. Medium: synchronous Copilot endpoint ties up a worker thread
* **Evidence:** `POST /copilot/chat` is a sync route running the whole graph.
* **Fix plan:** `graph.ainvoke` with the async Anthropic client, or Server-Sent Events streaming of node progress
  (which also improves UX).
* **Tests to add:** concurrent load test (for example 50 parallel requests with a slow fake LLM) keeps
  `/health` responsive.

### O6. Low: numeric guard allows some context numbers anywhere
* **Evidence:** `numeric_guard.check_numbers` accepts integers ≤ 10 and any number that appears in retrieved
  documents. An LLM could attach "2.1" to the wrong subject.
* **Fix plan:** claim-level attribution: require each restated fact value to sit near its own `[F#]` citation and
  check the value matches that specific fact.
* **Tests to add:** "Japan's fertility is 2.1 [F3]" where F3 is 1.20 → rejected.

### O7. Low: metrics endpoint is unauthenticated
* **Fix plan:** expose it only on an internal port or behind an admin token; export via OpenTelemetry.

### O8. Low: live Claude path not exercised against the real API
* **Evidence:** all LLM tests use `FakeLLM`. The request shape (beta fallback header, `extra_body.fallbacks`,
  `reasoning_effort`) was verified against the installed `langchain-anthropic` source, not a live call.
* **Fix plan:** `python -m evals.run_evals --llm` in a gated CI job with a budget cap; record a contract fixture.

### O9. Low: frontend bundle size (1.07 MB minified, 326 KB gzipped)
* **Fix plan:** route-level `React.lazy` and lazy-load the map topology.

### O10. Low: PDF Unicode outside Docker
* **Evidence:** without DejaVu or Arial Unicode installed, the renderer falls back to Helvetica and replaces
  characters it cannot draw.
* **Fix plan:** vendor a Unicode TTF in the repository or require `PDF_FONT_PATH`.

## 4. Fix order

1. O1 (auth) before any shared deployment.
2. O2 (PostgreSQL CI) and O4 (latency budget). Both are small and remove uncertainty.
3. O5 and O3 when traffic or replica count requires it.
4. O6–O10 as hardening.
