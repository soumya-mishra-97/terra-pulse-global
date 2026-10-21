"""Country Intelligence Report service: job creation, background execution, export and access control."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.agents.nodes.common import AgentDeps
from app.agents.report_graph import build_report_graph
from app.agents.tools import DataTools
from app.config import Settings
from app.domain.errors import DataUnavailableError, DomainError, NotFoundError
from app.integrations.llm import LLMClient
from app.integrations.storage import Storage, StorageError
from app.knowledge.retriever import Retriever
from app.observability import correlation_id_var, metrics
from app.reports.catalog import (
    PERIODS,
    REQUIRED_SECTIONS,
    SECTION_GROUPS,
    SECTIONS,
    flag_emoji,
    normalise_sections,
)
from app.reports.markdown import render_markdown
from app.reports.pdf import render_pdf
from app.repositories.audit import AuditRepository
from app.repositories.orm import CountryReportRow, ReportGenerationRunRow
from app.repositories.population import PopulationRepository
from app.repositories.reports import ReportRepository
from app.schemas.reports import GenerateReportRequest, ReportCountry, ReportDetail, ReportPage, ReportSummary
from app.services.population import PopulationService

log = logging.getLogger(__name__)
TRANSIENT = (OperationalError, TimeoutError)


class ReportLimitError(DomainError):
    pass


class ReportNotReadyError(DomainError):
    pass


def _request_hash(owner: str, req: GenerateReportRequest, sections: list[str], source_id: int) -> str:
    raw = json.dumps({"o": owner, "c": req.country_code, "p": req.period, "s": sections, "src": source_id},
                     sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _filename(row: CountryReportRow, name: str, ext: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in name).strip("-").lower()[:40] or row.country_iso3.lower()
    date = (row.generated_at or row.created_at).strftime("%Y%m%d")
    return f"terrapulse-{safe}-{row.period}-{date}.{ext}"


class ReportService:
    def __init__(self, factory: sessionmaker[Session], settings: Settings, retriever: Retriever,
                 llm: LLMClient | None, storage: Storage) -> None:
        self.factory = factory
        self.settings = settings
        self.retriever = retriever
        self.llm = llm
        self.storage = storage
        self.executor = ThreadPoolExecutor(max_workers=settings.report_workers, thread_name_prefix="report")

    # ---- catalogue -----------------------------------------------------------
    @staticmethod
    def options() -> dict:
        return {"sections": [{"id": s, "title": t, "required": s in REQUIRED_SECTIONS} for s, t in SECTIONS],
                "groups": SECTION_GROUPS, "periods": PERIODS, "required": list(REQUIRED_SECTIONS)}

    def countries(self) -> list[ReportCountry]:
        with self.factory() as s:
            svc = PopulationService(PopulationRepository(s), self.settings.stale_after_days)
            latest = svc.latest_values("population_total")
            return [ReportCountry(iso3=c.iso3, iso2=c.iso2, name=c.name, region=c.region, income_level=c.income_level,
                                  flag=flag_emoji(c.iso2), latest_population_year=latest.get(c.iso3, (None,))[0])
                    for c in svc.all_countries()]

    # ---- create --------------------------------------------------------------
    def create(self, owner: str, req: GenerateReportRequest, idempotency_key: str | None) -> tuple[ReportSummary, bool]:
        """Returns (report, created). Duplicate submissions return the existing report."""
        sections = normalise_sections(list(req.sections))
        with self.factory.begin() as s:
            repo = ReportRepository(s)
            if idempotency_key:
                existing = repo.by_idempotency_key(owner, idempotency_key)
                if existing:
                    return self._summary(s, existing), False
            pop_repo = PopulationRepository(s)
            src = pop_repo.active_source()
            if src is None:
                raise DataUnavailableError("No dataset imported; reports cannot be generated.")
            country = pop_repo.get_country(req.country_code)
            if country is None or country.is_aggregate:
                raise NotFoundError(f"Country {req.country_code} is not supported.")
            rhash = _request_hash(owner, req, sections, src.id)
            recent = repo.recent_same_request(owner, rhash, self.settings.idempotency_window_seconds)
            if recent and not idempotency_key:
                return self._summary(s, recent), False
            if repo.count_active(owner) >= self.settings.max_active_reports_per_user:
                raise ReportLimitError("Too many reports are being generated. Wait for one to finish.")
            row = CountryReportRow(
                id=uuid.uuid4().hex, owner_id=owner, country_iso3=country.iso3, period=req.period, sections=sections,
                status="queued", progress=0, current_step="queued", validation={}, request_hash=rhash,
                idempotency_key=idempotency_key, source_id=src.id, export_meta={}, attempts=0,
            )
            repo.add(row)
            AuditRepository(s).log(owner, "report.requested", "country_report", row.id,
                                   {"country": country.iso3, "period": req.period, "sections": sections})
            summary = self._summary(s, row)
        metrics.incr("reports.requested")
        cid = correlation_id_var.get()
        if self.settings.report_execution == "inline":
            self.run(summary.id, cid)
            with self.factory() as s:
                summary = self._summary(s, ReportRepository(s).get(summary.id))
        else:
            self.executor.submit(self.run, summary.id, cid)
        return summary, True

    def regenerate(self, owner: str, report_id: str) -> ReportSummary:
        with self.factory() as s:
            row = ReportRepository(s).get_for_owner(report_id, owner)
            if row is None:
                raise NotFoundError("Report not found.")
            req = GenerateReportRequest(country_code=row.country_iso3, period=row.period, sections=row.sections)
        return self.create(owner, req, idempotency_key=f"regen-{uuid.uuid4().hex}")[0]

    # ---- run (background) ----------------------------------------------------
    def _progress(self, report_id: str, pct: int, step: str) -> None:
        with self.factory.begin() as s:
            ReportRepository(s).set_progress(report_id, "running", pct, step)

    def run(self, report_id: str, correlation_id: str = "-") -> None:
        token = correlation_id_var.set(correlation_id)
        try:
            for attempt in range(1, self.settings.report_max_attempts + 1):
                try:
                    self._run_once(report_id, attempt)
                    return
                except TRANSIENT as exc:
                    log.warning("report attempt failed (transient)", extra={"report_id": report_id, "attempt": attempt})
                    if attempt == self.settings.report_max_attempts:
                        self._fail(report_id, f"Generation failed after {attempt} attempts ({type(exc).__name__}).")
                    else:
                        time.sleep(0.5 * attempt)
                except Exception as exc:
                    log.exception("report generation failed", extra={"report_id": report_id})
                    self._fail(report_id, f"Generation failed ({type(exc).__name__}). Please try again.")
                    return
        finally:
            correlation_id_var.reset(token)

    def _fail(self, report_id: str, message: str) -> None:
        with self.factory.begin() as s:
            repo = ReportRepository(s)
            row = repo.get(report_id)
            if row:
                row.status, row.error, row.current_step = "failed", message, None
                for run in repo.runs(report_id):
                    if run.status == "running":
                        run.status, run.error, run.finished_at = "failed", message, datetime.now(UTC)
                AuditRepository(s).log(row.owner_id, "report.failed", "country_report", report_id, {"error": message})
        metrics.incr("reports.failed")

    def _run_once(self, report_id: str, attempt: int) -> None:
        started = time.perf_counter()
        with self.factory.begin() as s:
            row = ReportRepository(s).get(report_id)
            if row is None:
                return
            row.status, row.attempts, row.current_step, row.progress = "running", attempt, "starting", 1
            iso3, period, sections = row.country_iso3, row.period, list(row.sections)
            run_row = ReportRepository(s).add_run(report_id=report_id, attempt=attempt, status="running", trace=[],
                                                  correlation_id=correlation_id_var.get())
            run_id = run_row.id

        with self.factory() as s:
            svc = PopulationService(PopulationRepository(s), self.settings.stale_after_days)
            deps = AgentDeps(service=svc, tools=DataTools(svc), retriever=self.retriever, llm=self.llm,
                             settings=self.settings)
            graph = build_report_graph(deps, on_progress=lambda pct, step: self._progress(report_id, pct, step))
            state = graph.invoke({"report_id": report_id, "iso3": iso3, "period": period, "sections": sections,
                                  "deadline": time.monotonic() + self.settings.report_timeout_seconds, "trace": []},
                                 {"recursion_limit": 30})

        content = state.get("content")
        trace = state.get("trace", [])
        if not content:
            failed = next((t for t in trace if t["status"] == "failed"), None)
            raise RuntimeError(f"workflow produced no content ({failed['node'] if failed else 'unknown node'})")

        status = state.get("status", "completed")
        export_meta: dict = {}
        pdf_key = md_key = None
        if status == "completed":
            self._progress(report_id, 95, "rendering exports")
            md = render_markdown(content).encode("utf-8")
            pdf = render_pdf(content)
            pdf_key, md_key = f"reports/{report_id}.pdf", f"reports/{report_id}.md"
            self.storage.put(pdf_key, pdf, "application/pdf")
            self.storage.put(md_key, md, "text/markdown")
            export_meta = {
                "pdf": {"bytes": len(pdf), "sha256": hashlib.sha256(pdf).hexdigest()},
                "md": {"bytes": len(md), "sha256": hashlib.sha256(md).hexdigest()},
            }
        with self.factory.begin() as s:
            repo = ReportRepository(s)
            row = repo.get(report_id)
            row.status = status
            row.progress = 100
            row.current_step = None
            row.content = content
            row.validation = content.get("validation") or {}
            row.validation_status = (content.get("validation") or {}).get("status")
            row.mode, row.model = content.get("mode"), content.get("model")
            row.pdf_key, row.md_key, row.export_meta = pdf_key, md_key, export_meta
            row.generated_at = datetime.now(UTC)
            row.error = ("Essential data-integrity checks failed; the report was not published."
                         if status == "blocked" else None)
            repo.replace_sources(report_id, content.get("sources", []))
            run = s.get(ReportGenerationRunRow, run_id)
            run.status, run.trace, run.finished_at = status, trace, datetime.now(UTC)
            AuditRepository(s).log(row.owner_id, f"report.{status}", "country_report", report_id,
                                   {"validation": row.validation_status, "mode": row.mode,
                                    "sources": [x["label"] for x in content.get("sources", [])],
                                    "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
        metrics.incr(f"reports.{status}")
        metrics.observe("reports.latency", (time.perf_counter() - started) * 1000)

    # ---- read/delete ---------------------------------------------------------
    def _summary(self, s: Session, row: CountryReportRow) -> ReportSummary:
        country = PopulationRepository(s).get_country(row.country_iso3)
        downloads = {}
        if row.status == "completed":
            downloads = {"pdf": f"/api/v1/reports/{row.id}/download?format=pdf",
                         "md": f"/api/v1/reports/{row.id}/download?format=md"}
        return ReportSummary(
            id=row.id, country_code=row.country_iso3, country_name=country.name if country else row.country_iso3,
            period=row.period, sections=row.sections, status=row.status, progress=row.progress,
            current_step=row.current_step, error=row.error, validation_status=row.validation_status, mode=row.mode,
            created_at=row.created_at, generated_at=row.generated_at, downloads=downloads,
        )

    def get(self, owner: str, report_id: str) -> ReportDetail:
        with self.factory() as s:
            repo = ReportRepository(s)
            row = repo.get_for_owner(report_id, owner)
            if row is None:  # same response for "missing" and "not yours": no existence oracle
                raise NotFoundError("Report not found.")
            summ = self._summary(s, row)
            sources = [{"label": x.label, "kind": x.kind, "title": x.title, "publisher": x.publisher, "url": x.url,
                        "published": x.published, "reference": x.reference} for x in repo.sources(report_id)]
            runs = [{"attempt": r.attempt, "status": r.status, "trace": r.trace, "error": r.error,
                     "started_at": r.started_at, "finished_at": r.finished_at} for r in repo.runs(report_id)]
            return ReportDetail(**summ.model_dump(), content=row.content, sources=sources, runs=runs)

    def list(self, owner: str, limit: int, offset: int) -> ReportPage:
        with self.factory() as s:
            rows, total = ReportRepository(s).list_for_owner(owner, limit, offset)
            return ReportPage(items=[self._summary(s, r) for r in rows], total=total, limit=limit, offset=offset)

    def download(self, owner: str, report_id: str, fmt: str) -> tuple[bytes, str, str]:
        with self.factory.begin() as s:
            row = ReportRepository(s).get_for_owner(report_id, owner)
            if row is None:
                raise NotFoundError("Report not found.")
            if row.status != "completed":
                raise ReportNotReadyError(f"Report is {row.status}; downloads are available once it is completed.")
            key = row.pdf_key if fmt == "pdf" else row.md_key
            country = PopulationRepository(s).get_country(row.country_iso3)
            AuditRepository(s).log(owner, "report.downloaded", "country_report", report_id, {"format": fmt})
        try:
            data = self.storage.get(key)
        except StorageError as exc:
            raise NotFoundError("Export file is missing; regenerate the report.") from exc
        media = "application/pdf" if fmt == "pdf" else "text/markdown; charset=utf-8"
        return data, media, _filename(row, country.name if country else row.country_iso3, fmt)

    def delete(self, owner: str, report_id: str) -> None:
        with self.factory.begin() as s:
            repo = ReportRepository(s)
            row = repo.get_for_owner(report_id, owner)
            if row is None:
                raise NotFoundError("Report not found.")
            if row.status in ("queued", "running"):
                raise ReportLimitError("A report cannot be deleted while it is being generated.")
            keys = [k for k in (row.pdf_key, row.md_key) if k]
            repo.delete(row)
            AuditRepository(s).log(owner, "report.deleted", "country_report", report_id, {})
        for k in keys:
            try:
                self.storage.delete(k)
            except StorageError:
                log.warning("could not delete export", extra={"key": k})

    def recover_interrupted(self) -> int:
        with self.factory.begin() as s:
            return ReportRepository(s).mark_interrupted()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
