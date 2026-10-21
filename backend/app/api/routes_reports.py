from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status

from app.api.deps import current_user, get_container
from app.schemas.reports import (
    GenerateReportRequest,
    ReportCountry,
    ReportDetail,
    ReportOptions,
    ReportPage,
    ReportSummary,
)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
REPORT_ID = Path(pattern="^[a-f0-9]{32}$", description="Report identifier")
IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")


@router.get("/countries", response_model=list[ReportCountry])
def supported_countries(container=Depends(get_container)) -> list[ReportCountry]:
    return container.reports.countries()


@router.get("/options", response_model=ReportOptions)
def options(container=Depends(get_container)) -> dict:
    return container.reports.options()


@router.post("/generate", response_model=ReportSummary, status_code=status.HTTP_202_ACCEPTED)
def generate(body: GenerateReportRequest, response: Response, user: str = Depends(current_user),
             idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
             container=Depends(get_container)) -> ReportSummary:
    if idempotency_key is not None and not IDEMPOTENCY_RE.match(idempotency_key):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Idempotency-Key header.")
    container.rate_limiter.check(f"reports:{user}", container.settings.report_requests_per_hour, 3600)
    report, created = container.reports.create(user, body, idempotency_key)
    if not created:
        response.status_code = status.HTTP_200_OK
        response.headers["X-Idempotent-Replay"] = "true"
    return report


@router.post("/{report_id}/regenerate", response_model=ReportSummary, status_code=status.HTTP_202_ACCEPTED)
def regenerate(report_id: str = REPORT_ID, user: str = Depends(current_user),
               container=Depends(get_container)) -> ReportSummary:
    container.rate_limiter.check(f"reports:{user}", container.settings.report_requests_per_hour, 3600)
    return container.reports.regenerate(user, report_id)


@router.get("", response_model=ReportPage)
def history(limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
            user: str = Depends(current_user), container=Depends(get_container)) -> ReportPage:
    return container.reports.list(user, limit, offset)


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: str = REPORT_ID, user: str = Depends(current_user),
               container=Depends(get_container)) -> ReportDetail:
    return container.reports.get(user, report_id)


@router.get("/{report_id}/download")
def download(report_id: str = REPORT_ID, format: Literal["pdf", "md"] = Query(default="pdf"),
             user: str = Depends(current_user), container=Depends(get_container)) -> Response:
    data, media, filename = container.reports.download(user, report_id, format)
    return Response(content=data, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    })


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(report_id: str = REPORT_ID, user: str = Depends(current_user), container=Depends(get_container)) -> Response:
    container.reports.delete(user, report_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
