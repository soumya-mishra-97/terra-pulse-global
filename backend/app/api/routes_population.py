from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_session
from app.repositories.population import PopulationRepository
from app.schemas.population import CityPage, CountryPage, HistoryResponse, RegionsResponse, SourceOut, WorldSummary
from app.services.cities import search_cities
from app.services.population import METRICS, PopulationService

router = APIRouter(prefix="/api/v1", tags=["population"])


def population_service(session: Session = Depends(get_session), container=Depends(get_container)) -> PopulationService:
    return PopulationService(PopulationRepository(session), container.settings.stale_after_days)


@router.get("/health")
def health(session: Session = Depends(get_session), container=Depends(get_container)) -> dict:
    db_ok, data_ok = True, False
    try:
        session.execute(text("SELECT 1"))
        data_ok = PopulationRepository(session).active_source() is not None
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok and data_ok else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "dataset_loaded": data_ok,
        "llm_mode": "claude" if container.llm is not None else "demo",
        "llm_model": container.llm.model if container.llm is not None else None,
        "version": container.version,
    }


@router.get("/population/summary", response_model=WorldSummary)
def summary(svc: PopulationService = Depends(population_service)) -> WorldSummary:
    return svc.world_summary()


@router.get("/population/countries", response_model=CountryPage)
def countries(
    q: str | None = Query(default=None, max_length=80),
    region: str | None = Query(default=None, max_length=80),
    sort: Literal["name", "population", "growth", "share"] = "population",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    svc: PopulationService = Depends(population_service),
) -> CountryPage:
    return svc.countries(q=q, region=region, sort=sort, order=order, limit=limit, offset=offset)


@router.get("/population/cities", response_model=CityPage)
def cities(
    q: str = Query(min_length=2, max_length=80),
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
    container=Depends(get_container),
) -> CityPage:
    return search_cities(container.cities, PopulationRepository(session), q, limit)


@router.get("/population/countries/{iso3}/history", response_model=HistoryResponse)
def history(
    iso3: str = Path(pattern="^[A-Za-z]{3}$", description="ISO 3166-1 alpha-3 code"),
    metric: str = Query(default="population_total", pattern="^[a-z0-9_]{3,40}$"),
    start: int | None = Query(default=None, ge=1950, le=2100),
    end: int | None = Query(default=None, ge=1950, le=2100),
    svc: PopulationService = Depends(population_service),
) -> HistoryResponse:
    return svc.history(iso3.upper(), metric, start, end)


@router.get("/population/regions", response_model=RegionsResponse)
def regions(svc: PopulationService = Depends(population_service)) -> RegionsResponse:
    return svc.regions()


@router.get("/population/metrics")
def metrics_catalog() -> dict:
    return {"metrics": list(METRICS)}


@router.get("/population/sources", response_model=list[SourceOut])
def sources(session: Session = Depends(get_session)) -> list[SourceOut]:
    return [SourceOut.model_validate(s, from_attributes=True) for s in PopulationRepository(session).list_sources()]
