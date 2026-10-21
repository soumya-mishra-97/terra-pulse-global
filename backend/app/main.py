"""FastAPI application factory (API/BFF layer of the modular monolith)."""

from __future__ import annotations

import logging
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import routes_copilot, routes_docs, routes_population, routes_reports
from app.api.deps import RateLimiter
from app.config import Settings, get_settings
from app.db import get_session_factory, make_engine
from app.domain.errors import DataUnavailableError, DomainError, NotFoundError
from app.integrations.llm import LLMClient, build_llm
from app.integrations.storage import build_storage
from app.knowledge.retriever import BM25Retriever, Retriever
from app.observability import configure_logging, correlation_id_var, metrics, new_correlation_id
from app.services.cities import CityIndex
from app.services.reports import ReportLimitError, ReportNotReadyError, ReportService

VERSION = "0.1.0"
log = logging.getLogger("terrapulse.api")
CID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


@dataclass
class Container:
    settings: Settings
    session_factory: sessionmaker[Session]
    retriever: Retriever
    llm: LLMClient | None
    reports: ReportService
    rate_limiter: RateLimiter
    cities: CityIndex | None = None
    version: str = VERSION


def build_container(settings: Settings, session_factory: sessionmaker[Session] | None = None,
                    llm: LLMClient | None = None, use_llm_from_settings: bool = True) -> Container:
    factory = session_factory or (get_session_factory() if settings is get_settings()
                                  else sessionmaker(bind=make_engine(settings.database_url), expire_on_commit=False))
    retriever = BM25Retriever.from_directory(settings.methodology_dir)
    llm = llm if llm is not None else (build_llm(settings) if use_llm_from_settings else None)
    reports = ReportService(factory, settings, retriever, llm, build_storage(settings))
    return Container(settings=settings, session_factory=factory, retriever=retriever, llm=llm, reports=reports,
                     rate_limiter=RateLimiter(), cities=CityIndex.from_directory(settings.city_dir))


def create_app(container: Container | None = None) -> FastAPI:
    settings = container.settings if container else get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not hasattr(app.state, "container"):
            app.state.container = build_container(settings)
        recovered = app.state.container.reports.recover_interrupted()
        if recovered:
            log.warning("marked interrupted report jobs as failed", extra={"count": recovered})
        log.info("TerraPulse API started", extra={"llm_mode": "claude" if app.state.container.llm else "demo"})
        yield
        app.state.container.reports.shutdown()

    app = FastAPI(title="TerraPulse Global AI API", version=VERSION, lifespan=lifespan,
                  description="Population estimation and demographic intelligence. Figures are dated estimates.")
    if container is not None:
        app.state.container = container

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "DELETE"],
                       allow_headers=["Content-Type", "X-User-Id", "X-Request-ID", "Idempotency-Key"],
                       expose_headers=["X-Request-ID", "Content-Disposition", "Retry-After"])

    @app.middleware("http")
    async def correlation_and_logging(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        cid = incoming if CID_RE.match(incoming) else new_correlation_id()
        token = correlation_id_var.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            ms = (time.perf_counter() - start) * 1000
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)  # templated path keeps metric cardinality low
            metrics.incr(f"http.{response.status_code // 100}xx")
            metrics.observe(f"http {request.method} {path}", ms)
            response.headers["X-Request-ID"] = cid
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            log.info("request", extra={"method": request.method, "path": path, "status": response.status_code,
                                       "latency_ms": round(ms, 1)})
            return response
        finally:
            correlation_id_var.reset(token)

    def problem(status_code: int, title: str, detail, request: Request) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={
            "error": {"status": status_code, "title": title, "detail": detail,
                      "request_id": correlation_id_var.get()}})

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return problem(404, "Not found", str(exc), request)

    @app.exception_handler(DataUnavailableError)
    async def unavailable(request: Request, exc: DataUnavailableError):
        return problem(503, "Data unavailable", str(exc), request)

    @app.exception_handler(ReportLimitError)
    async def limit(request: Request, exc: ReportLimitError):
        return problem(409, "Conflict", str(exc), request)

    @app.exception_handler(ReportNotReadyError)
    async def not_ready(request: Request, exc: ReportNotReadyError):
        return problem(409, "Report not ready", str(exc), request)

    @app.exception_handler(DomainError)
    async def domain(request: Request, exc: DomainError):
        return problem(422, "Unprocessable request", str(exc), request)

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
        return problem(422, "Invalid request", errors, request)

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        resp = problem(exc.status_code, "Request failed", exc.detail, request)
        for k, v in (exc.headers or {}).items():
            resp.headers[k] = v
        return resp

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return problem(500, "Internal error", "An unexpected error occurred. Quote the request id when reporting it.",
                       request)

    @app.get("/api/v1/metrics", tags=["ops"])
    def get_metrics() -> dict:
        return metrics.snapshot()

    app.include_router(routes_population.router)
    app.include_router(routes_copilot.router)
    app.include_router(routes_reports.router)
    app.include_router(routes_docs.router)
    return app


app = create_app()
