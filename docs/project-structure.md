# Project structure

## Documentation and API entry points

| What | In the UI | Local dev (Vite) | Docker (nginx) | Backend direct |
|---|---|---|---|---|
| AI Docs (agent graph + project docs) | **AI Docs** tab | <http://localhost:5173/ai-docs> | <http://localhost:8080/ai-docs> | — |
| Project structure (this page) | **Project Structure** tab | <http://localhost:5173/project-structure> | <http://localhost:8080/project-structure> | — |
| Swagger UI | **Swagger API** tab | <http://localhost:5173/docs> | <http://localhost:8080/docs> | <http://localhost:8000/docs> |
| ReDoc | AI Docs → ReDoc | <http://localhost:5173/redoc> | <http://localhost:8080/redoc> | <http://localhost:8000/redoc> |
| OpenAPI schema | AI Docs → OpenAPI JSON | <http://localhost:5173/openapi.json> | <http://localhost:8080/openapi.json> | <http://localhost:8000/openapi.json> |

## Repository layout

```text
terrapulse-global-ai/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory, middleware, error handling, router wiring
│   │   ├── config.py            # Settings from environment
│   │   ├── api/                 # Routers: population, copilot, reports, docs (+ identity, rate limits)
│   │   ├── schemas/             # Pydantic request and response models
│   │   ├── domain/              # Pure calculations, models, validation, formatting
│   │   ├── services/            # Population, Copilot, and report services
│   │   ├── repositories/        # SQLAlchemy repositories and persistence
│   │   ├── ingestion/           # Snapshot importer and CLI
│   │   ├── knowledge/           # Document loading, sanitization, and BM25 retrieval
│   │   ├── agents/              # LangGraph state, planner, tools, prompts, nodes, graphs
│   │   ├── reports/             # Section builders and PDF/Markdown renderers
│   │   └── integrations/        # Claude client and file-storage adapters
│   ├── migrations/              # Alembic migrations
│   ├── data/snapshots/          # Dated WDI snapshot and manifest
│   ├── data/cities/             # Dated GeoNames city population snapshot and manifest
│   ├── data/methodology/        # Approved RAG source documents
│   ├── scripts/                 # World Bank and GeoNames snapshot retrieval
│   ├── evals/                   # Evaluation cases and runner
│   └── tests/                   # Unit and integration tests
├── frontend/
│   ├── index.html
│   ├── vite.config.ts           # Dev proxy for /api, /docs, /redoc, /openapi.json
│   ├── nginx.conf               # Docker proxy, gzip, immutable asset caching
│   └── src/
│       ├── main.tsx             # Entry point; applies the saved light/dark theme before first render
│       ├── App.tsx              # Shell: navigation, theme toggle, lazy-loaded routes
│       ├── styles.css           # Light and dark theme tokens and all component styles
│       ├── api/                 # Fetch client and response types
│       ├── lib/                 # Formatting, useAsync, theme
│       ├── components/          # Charts, world map, copilot panel, tiles, states, icons
│       └── pages/               # Overview, Countries, Reports, HowItWorks (AI Docs + Project Structure)
├── docs/                        # Architecture, ADRs, production review, UI guide, this page
├── docker-compose.yml
└── .env.example
```

## Routes

| Path | Page |
|---|---|
| `/` | Overview dashboard |
| `/countries?c=ISO3` | Country table and indicator history |
| `/reports` | Country intelligence reports |
| `/ai-docs` | Agent workflow and project documentation |
| `/project-structure` | This page |
