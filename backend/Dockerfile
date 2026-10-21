# Build context: repository root (see docker-compose.yml)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
# Liberation Serif (Times New Roman metrics) gives the PDF renderer Unicode coverage for country names with diacritics.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-liberation && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install .
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/data ./data
COPY backend/scripts ./scripts
COPY backend/evals ./evals
# Documentation served on the AI Docs and Project Structure pages
COPY README.md /srv/README.md
COPY docs /srv/docs

RUN useradd --create-home --uid 10001 terrapulse && mkdir -p /srv/backend/var/reports && chown -R terrapulse /srv/backend/var
USER terrapulse
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')"
CMD ["sh", "-c", "python -m app.ingestion.cli bootstrap && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
