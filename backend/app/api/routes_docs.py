"""Serve whitelisted project documentation (README, architecture, ADR, review) to the UI."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.config import PROJECT_DIR

router = APIRouter(prefix="/api/v1/docs", tags=["docs"])

DOCS = {
    "readme": ("README", PROJECT_DIR / "README.md"),
    "project-structure": ("Project structure", PROJECT_DIR / "docs" / "project-structure.md"),
    "architecture": ("Architecture & service boundaries", PROJECT_DIR / "docs" / "architecture.md"),
    "adr-001": ("ADR-001: Modular monolith", PROJECT_DIR / "docs" / "adr" / "ADR-001-modular-monolith.md"),
    "review": ("Production-readiness review", PROJECT_DIR / "docs" / "production-readiness-review.md"),
    "ui-guide": ("UI guide", PROJECT_DIR / "docs" / "ui-guide.md"),
}


@router.get("")
def list_docs() -> list[dict]:
    return [{"slug": k, "title": t, "available": p.is_file()} for k, (t, p) in DOCS.items()]


IMAGE_RE = re.compile(r"^[a-z0-9-]{1,60}\.png$")


@router.get("/images/{name}")
def get_image(name: str) -> FileResponse:
    """Screenshots referenced by the docs (docs/images/*.png). Strict name pattern: no path traversal."""
    path = PROJECT_DIR / "docs" / "images" / name
    if not IMAGE_RE.match(name) or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/{slug}")
def get_doc(slug: str) -> dict:
    if slug not in DOCS:  # whitelist lookup: the slug never becomes a path
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    title, path = DOCS[slug]
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not available in this deployment.")
    return {"slug": slug, "title": title, "markdown": path.read_text(encoding="utf-8")}
