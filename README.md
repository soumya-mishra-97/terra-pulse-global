# TerraPulse Global AI

**Multi-Agent Demographic Intelligence Platform**

TerraPulse Global AI is a demographic intelligence platform that explores global and country-level population trends using dated population datasets, deterministic calculations, retrieval-augmented generation (RAG), and a LangGraph-orchestrated agent workflow. When configured, Anthropic Claude generates evidence-grounded explanations; it does not calculate or override authoritative population figures.

> **Data integrity:** TerraPulse does not count every person on Earth in real time. Population values are source estimates tied to reference dates, or deterministic calculations derived from those estimates. The animated counter is an illustrative projection with its assumptions disclosed.

**Screenshot:**
<img width="500" height="700" alt="tera-pulse" src="https://github.com/user-attachments/assets/2cac642f-f3bc-4bfa-a46d-deb93caebf35" />


## Contents

- [Project Objective](#project-objective)
- [Key Capabilities](#key-capabilities)
- [User Interface](#user-interface)
- [System Architecture](#system-architecture)
- [Agent Responsibilities](#agent-responsibilities)
- [Agent Workflow](#agent-workflow)
- [Country Intelligence Reports](#country-intelligence-reports)
- [Technology Stack](#technology-stack)
- [Data Sources and Provenance](#data-sources-and-provenance)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Testing and Evaluation](#testing-and-evaluation)
- [Project Structure](#project-structure)
- [Security and Reliability](#security-and-reliability)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## Project Objective

Build a reliable demographic intelligence application that helps users explore population estimates, compare countries, understand demographic trends, and generate source-backed country reports. The project demonstrates how full-stack engineering and controlled agent orchestration can work together without allowing an LLM to invent or alter numeric facts.

## Key Capabilities

- **Global dashboard:** Population estimates, historical trends, annual changes, country comparisons, and data freshness indicators.
- **AI Copilot:** Natural-language questions answered through a controlled multi-agent workflow.
- **Country intelligence reports:** Generate country reports for a selected period, preview the report, and download it as PDF or Markdown.
- **Evidence-grounded answers:** Numeric claims are checked against structured facts or cited source documents.
- **Data ingestion:** Import a dated World Bank World Development Indicators snapshot with manifest and checksum validation.
- **Agent tracing:** Capture node status, execution latency, and run details for observability.
- **Graceful fallback:** Provide deterministic responses when Claude is not configured or a model call fails.
- **Responsive interface:** React dashboard with light and dark themes, visualizations, country search, the Pulse AI Copilot panel, report preview, and in-app AI Docs and Project Structure pages.

## User Interface

The top bar holds the breadcrumb, API status, light/dark theme toggle and user identity. Pill tabs switch between pages, and the **Pulse AI** Copilot is docked on the right of every page.

| Page | What it shows |
|---|---|
| **Overview** | Provenance banner, KPI tiles, illustrative counter, urban vs rural, age structure by region, world population trend, world map, regional indicators, and most populous / fastest growing tables |
| **Countries** | Country table searchable by country name, capital city or ISO3 code, with sorting, indicator history, derived change and CAGR; matching cities (e.g. Pune) appear with their population above the table |
| **Country Reports** | Report form, report history, and a sectioned preview with PDF and Markdown download |
| **AI Docs** | Live LangGraph workflow, agent responsibilities, deterministic tools, RAG corpus, and the project documentation viewer with Swagger UI, ReDoc and OpenAPI links |
| **Project Structure** | The documentation viewer opened on the annotated repository tree, routes and documentation/API URLs |
| **Swagger API** | FastAPI's interactive API documentation in a new tab |
| **Pulse AI** | Suggested prompts and chat answers with inline charts, cited sources, limitations and an agent trace |

See the [UI guide](docs/ui-guide.md) for page-by-page details.

## System Architecture

TerraPulse starts as a **modular monolith**. Logical modules have clear responsibilities, but do not communicate through unnecessary network calls. Modules can be extracted into separate services later if scaling, security, or team ownership requires it.

```text
React + TypeScript Dashboard
          |
          | HTTPS / REST
          v
FastAPI Application Layer
          |
          +----------------------+-----------------------+
          |                      |                       |
          v                      v                       v
Population Services       Copilot Workflow       Report Workflow
          |                (LangGraph)             (LangGraph)
          |                      |                       |
          v                      +-----------+-----------+
PostgreSQL / Data Store          |                       |
                                v                       v
                       Deterministic Tools        Report Assembly
                       RAG / Research             PDF + Markdown
                       Claude via LangChain       Export Storage
                                |
                                v
                     Evidence and Output Validation
```

### Architecture principles

- Keep domain calculations independent of FastAPI and LLM frameworks.
- Treat PostgreSQL as the source of truth for imported demographic data and report metadata.
- Use typed state and explicit graph transitions for agent workflows.
- Validate evidence before generating a response and validate the response before returning it.
- Apply bounded retries, timeouts, output limits, and deterministic fallbacks.
- Avoid premature microservices; preserve module boundaries so extraction remains possible.

## Agent Responsibilities

| Agent / Component | Responsibility | LLM usage |
|---|---|---|
| **Supervisor Agent** | Validates intent, identifies countries, metrics, and time period, and chooses which workflow nodes to run. | Optional Claude-assisted planning; proposed plans must pass schema and allowlist validation. |
| **Data Agent** | Retrieves population series, reference dates, and provenance through application services. | No |
| **Analysis Agent** | Calculates absolute change, percentage change, CAGR, rankings, and comparisons using comparable reference years. | No; deterministic Python calculations. |
| **Research Agent** | Retrieves relevant passages from approved methodology documents using the retrieval layer. | No; retrieval and sanitization are deterministic. |
| **Validation Agent** | Checks source provenance, data coverage, comparability, freshness, numeric claims, and citations. | No; rule-based validation. |
| **Response Generator** | Explains validated facts and retrieved evidence with citations and limitations. | Claude via LangChain when configured; deterministic template in demo mode. |
| **Report Supervisor** | Coordinates data retrieval, research, analysis, validation, narrative generation, and report assembly. | Uses the shared report workflow and optional LLM narrative generation. |

Not every component is an LLM agent. Deterministic Python is intentionally used for calculations and validation because it is more testable and reliable for numeric operations.

## Agent Workflow

```text
User Question
     |
     v
Supervisor / Planner
     |
     v
Data Agent ---> Analysis Agent ---> Research Agent
                                      |
                                      v
                              Evidence Validation
                                      |
                                      v
                           Response Generator
                           (Claude / template)
                                      |
                                      v
                              Output Validation
                                |         |
                             Pass       Fail
                                |         |
                                v         v
                            Finalize   Regenerate once
                                           |
                                           v
                                  Deterministic fallback
```

### Workflow controls

- Out-of-scope questions are declined without unnecessary tool execution.
- Methodology questions can bypass population-data retrieval when it is not needed.
- Retrieved text is treated as untrusted input and sanitized before use.
- Numeric claims must be traceable to structured facts or cited documents.
- Failed or insufficient evidence triggers bounded retries or a clear limitation message.
- Workflow node status and latency are recorded for inspection in the UI trace.

## Country Intelligence Reports

Users can select a country, reporting period, and report sections. The system generates a report job, tracks progress, presents a preview, and offers PDF and Markdown downloads.

### Report workflow

```text
Report Request
      |
      v
Report Supervisor
      |
      v
Country Data Agent ---> Research / RAG Agent
      |                         |
      v                         v
Demographic Analysis Agent ---> Validation Agent
                                      |
                         +------------+------------+
                         |                         |
                      Valid                    Essential failure
                         |                         |
                         v                         v
                Narrative Generation        Block publication
                         |
                         v
                Report Validation
                         |
                         v
                  Report Assembly
                         |
                         v
                  PDF / Markdown Export
```

### Report sections

Depending on data availability, reports may include:

1. Executive summary
2. Country overview
3. Current population estimate
4. Historical population trends
5. Annual population change and growth rate
6. Birth rate, death rate, fertility, and life expectancy
7. Age distribution and demographic structure
8. Urban and rural population
9. Population density and geographic distribution
10. Migration trends
11. Regional and global comparisons
12. Official future population projections, when available
13. Key findings and implications
14. Data sources, methodology, limitations, and uncertainty

Unavailable indicators are labelled **Data unavailable** rather than invented. Future projections are not inferred from historical trends; they require an official projection dataset.

### Export and persistence

- PDF generation uses ReportLab and includes report metadata, headings, tables, charts where supported, source references, and page numbers.
- Markdown export provides a portable text version of the report.
- Report records, source metadata, generation runs, status, and validation results are persisted.
- Export files use a storage abstraction, with local storage for development and an S3 adapter for deployment.
- Downloads are restricted to authorized users and validated server-generated storage keys.

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React, TypeScript, Vite | Dashboard, chat, reports, and interactive UI |
| Visualization | Recharts, d3-geo | Population charts and geographic views |
| Backend | Python, FastAPI, Pydantic | REST APIs, validation, and application services |
| Agent orchestration | LangGraph | Typed state, routing, retries, and workflow control |
| LLM integration | LangChain, Anthropic Claude API | Planning and evidence-grounded narrative generation |
| Data processing | Python | Deterministic calculations and data validation |
| Retrieval | BM25-based RAG retriever | Search approved methodology documents |
| Database | PostgreSQL, SQLAlchemy, Alembic | Structured data, migrations, report records, and run metadata |
| PDF export | ReportLab | Downloadable country reports |
| Testing | pytest, Ruff, frontend type-check/build | Correctness, code quality, and regression checks |
| Local orchestration | Docker Compose, nginx | Local multi-container environment and frontend serving |
| Optional file storage | S3-compatible storage | Persist report exports in deployed environments |

## Data Sources and Provenance

| Item | Details |
|---|---|
| Primary dataset | World Bank World Development Indicators (WDI), demographic subset |
| Licence | CC BY 4.0, subject to the source dataset's terms |
| Snapshot location | `backend/data/snapshots/wdi-2026-10-08/` |
| Retrieval script | `backend/scripts/fetch_worldbank_snapshot.py` using World Bank API v2 |
| Provenance | Dataset release, reference date, import timestamp, and SHA-256 checksums |
| Value type | Source estimates and deterministic derived values; illustrative counter clearly labelled |
| Uncertainty | Not quantified unless the source provides it; no invented confidence intervals |
| Projections | Unavailable until an official projection dataset is imported |
| City populations | GeoNames `cities5000` (places > 5,000 inhabitants), CC BY 4.0, in `backend/data/cities/<snapshot_id>/`, retrieved with `backend/scripts/fetch_geonames_cities.py`; the source does not state a reference year per city (often the latest census) |

Population estimates are tied to their reference dates; WDI population values are midyear estimates. The latest year is 2025 because WDI publishes a year's midyear estimate only after that year: the World Bank API returns no 2026 values yet. The illustrative counter is the only figure projected to today, and it is labelled as such. Freshness is evaluated against a configurable threshold. The import pipeline validates checksums and required metadata, rejects invalid rows, audits skipped rows when requested, checks coverage, and imports a new baseline transactionally.

## Getting Started

### Prerequisites

- Python 3.12 recommended
- Node.js and npm
- Docker Compose for the containerized setup (optional)

### Option A: Local development

#### 1. Start the backend

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
# Alternative: python -m venv .venv && pip install -e ".[dev]"
.venv/bin/python -m app.ingestion.cli bootstrap
.venv/bin/uvicorn app.main:app --reload --port 8000
```

The bootstrap command applies migrations and imports the bundled WDI snapshot. SQLite is used by default for local development; PostgreSQL can be configured with `DATABASE_URL`.

#### 2. Start the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually <http://localhost:5173>. The UI provides **AI Docs** at <http://localhost:5173/ai-docs>, **Project Structure** at <http://localhost:5173/project-structure>, **Swagger** at <http://localhost:5173/docs> and **ReDoc** at <http://localhost:5173/redoc>. The backend Swagger UI is also available directly at <http://localhost:8000/docs>.

### Option B: Docker Compose

From the project root:

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD and optionally ANTHROPIC_API_KEY in .env
docker compose up --build
```

The UI is served at <http://localhost:8080>; AI Docs are at <http://localhost:8080/ai-docs>, Project Structure at <http://localhost:8080/project-structure>, Swagger at <http://localhost:8080/docs> and ReDoc at <http://localhost:8080/redoc>. The backend Swagger UI is also available directly at <http://localhost:8000/docs>.

## Configuration

Configure settings using environment variables. See `.env.example` and `backend/app/config.py`.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file in `backend/var/` | Database connection; use PostgreSQL for deployment |
| `ANTHROPIC_API_KEY` | Empty | Enables Claude integration; empty means deterministic demo mode |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | Model identifier configured for planning and explanations |
| `LLM_TIMEOUT_SECONDS` | `45` | Maximum time for an LLM call |
| `LLM_MAX_RETRIES` | `2` | Bounded SDK retries |
| `LLM_MAX_OUTPUT_TOKENS` | `1500` | Copilot response token cap |
| `LLM_REPORT_MAX_OUTPUT_TOKENS` | `4000` | Report narrative token cap |
| `STALE_AFTER_DAYS` | `730` | Data freshness threshold |
| `STORAGE_BACKEND` | `local` | Local or S3-backed report storage |
| `REPORT_EXECUTION` | `thread` | Report job execution mode; `inline` supports tests |
| `COPILOT_REQUESTS_PER_MINUTE` | `20` | Per-user Copilot rate limit |
| `REPORT_REQUESTS_PER_HOUR` | `20` | Per-user report-generation rate limit |

Keep API keys on the server. Never commit secrets or expose them in frontend environment variables.

## API Reference

Interactive Swagger UI: <http://localhost:8000/docs> (backend direct), <http://localhost:5173/docs> (local frontend), or <http://localhost:8080/docs> (Docker UI). ReDoc and the raw OpenAPI schema are at `/redoc` and `/openapi.json` on the same hosts.

AI and architecture documentation is available in the UI at `/ai-docs` (or the previous `/how-it-works` route).

API errors use a consistent envelope with status, title, detail, and request ID. Responses include `X-Request-ID` for correlation.

| Method and path | Purpose |
|---|---|
| `GET /api/v1/health` | Database, dataset, and LLM mode status without exposing secrets |
| `GET /api/v1/population/summary` | Global estimate, history, annual change, leading countries, and provenance |
| `GET /api/v1/population/countries` | Searchable and pageable country list |
| `GET /api/v1/population/countries/{iso3}/history` | Historical series for a country and metric |
| `GET /api/v1/population/regions` | Regional aggregates |
| `GET /api/v1/population/cities?q=` | City population search (GeoNames), linked to the World Bank country |
| `GET /api/v1/population/sources` | Imported dataset versions |
| `POST /api/v1/copilot/chat` | Execute the multi-agent Copilot workflow |
| `GET /api/v1/copilot/architecture` | Agent graph, tools, and knowledge-base metadata |
| `GET /api/v1/reports/countries` | Countries supported by report generation |
| `GET /api/v1/reports/options` | Available report sections and periods |
| `POST /api/v1/reports/generate` | Create a report-generation job; supports `Idempotency-Key` |
| `GET /api/v1/reports/{id}` | Retrieve status, progress, content, sources, and run trace |
| `GET /api/v1/reports/{id}/download?format=pdf` | Download a completed PDF report |
| `GET /api/v1/reports/{id}/download?format=md` | Download a completed Markdown report |
| `GET /api/v1/reports` | Paginated report history |
| `POST /api/v1/reports/{id}/regenerate` | Regenerate a report using its parameters |
| `DELETE /api/v1/reports/{id}` | Delete an authorized report and its files |
| `GET /api/v1/docs/{slug}` | Serve project documentation to the in-app documentation page |
| `GET /api/v1/metrics` | In-process request counters and latency percentiles |

The current identity mechanism uses a demo `X-User-Id` header. Replace it with OIDC/JWT authentication before real deployment.

## Testing and Evaluation

Run the backend checks from the `backend` directory:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check app tests evals scripts migrations
.venv/bin/python -m evals.run_evals
.venv/bin/python -m evals.run_evals --llm  # Uses API credits
```

Run frontend checks from `frontend`:

```bash
npm run typecheck
npm test
npm run build
```

Test coverage includes:

- Domain calculations, rankings, missing periods, and illustrative projections.
- Data ingestion, checksums, invalid rows, coverage, duplicate imports, and stale data.
- API validation, error handling, request IDs, and rate limits.
- Agent planning, numeric validation, out-of-scope refusal, retries, fallbacks, and prompt-injection handling.
- Report PDF/Markdown generation, downloads, authorization, idempotency, missing indicators, blocked publication, and job recovery.
- Copilot groundedness, numeric consistency, source correctness, and insufficient-evidence handling.

## Project Structure

The full annotated tree, every route, and a table of documentation and API entry points live in
[docs/project-structure.md](docs/project-structure.md). It is also shown in the app under the **Project Structure** tab.

```text
terrapulse-global-ai/
├── backend/     # FastAPI modular monolith: api, services, domain, agents (LangGraph), reports, ingestion
├── frontend/    # React + TypeScript dashboard (Vite dev proxy, nginx for Docker)
├── docs/        # Architecture, ADRs, production review, UI guide, project structure
├── docker-compose.yml
└── .env.example
```

## Security and Reliability

- The Anthropic API key is stored and used on the backend only; it is not returned by APIs or bundled into the frontend.
- Request and response payloads are validated with Pydantic and bounded input parameters.
- Database access uses parameterized SQLAlchemy expressions and transactional writes.
- Retrieved documents are sanitized and treated as untrusted content.
- LLM calls have timeouts, bounded retries, output limits, and deterministic fallback behavior.
- Report downloads use strict identifiers and server-generated storage keys resolved within the configured storage root.
- Markdown output is escaped, and the UI does not render arbitrary raw HTML from model responses.
- Rate limits and report-generation concurrency limits help prevent accidental resource exhaustion.
- The project does not claim security certification or production readiness.

See [docs/architecture.md](docs/architecture.md) and [docs/production-readiness-review.md](docs/production-readiness-review.md) for additional architecture and risk details.

## Known Limitations

- **Authentication:** The current identity mechanism is a demo header; production deployment requires OIDC/JWT and an authorization policy.
- **Database verification:** The automated test suite uses SQLite. Run Docker Compose to verify PostgreSQL runtime behavior.
- **Docker verification:** Build and run the images in an environment with Docker installed before deployment.
- **Live Claude calls:** Automated tests use a scripted fake model. Run the LLM evaluation with a valid API key to verify the live integration and cost.
- **Rate limiting and jobs:** In-process controls are suitable for a single API replica; multiple replicas require shared infrastructure.
- **RAG corpus:** The initial BM25 retriever uses a small curated methodology corpus. Official full reports and a vector-search layer can be added later.
- **Geographic detail:** Current demographic data is national-level; subnational distribution is not included.
- **Projection data:** Future projections remain unavailable until an official projection dataset is imported.

## Roadmap

1. Add embeddings and pgvector behind the existing retriever interface; ingest official demographic reports and methodology.
2. Import official UN World Population Prospects projection variants.
3. Replace demo identity with OIDC/JWT; introduce Redis-backed rate limiting and a durable job queue if multiple API replicas are required.
4. Stream agent progress over Server-Sent Events and add OpenTelemetry tracing.
5. Extract modules into independent services only when a concrete operational need justifies it.

---

**License and attribution:** The World Bank WDI dataset is provided under CC BY 4.0. Review source-specific attribution and licensing requirements when redistributing data or generated reports.
