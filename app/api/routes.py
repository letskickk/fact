"""REST API routes."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api")

FACTS_DIR = Path("data/facts")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/reference-files")
async def list_reference_files() -> dict:
    """List reference files loaded from data/facts/."""
    if not FACTS_DIR.exists():
        return {"files": []}
    files = []
    for f in sorted(FACTS_DIR.rglob("*")):
        if f.is_file() and not f.name.startswith("."):
            size = f.stat().st_size
            if size >= 1024 * 1024:
                size_str = f"{round(size / (1024 * 1024), 1)}MB"
            else:
                size_str = f"{round(size / 1024, 1)}KB"
            rel_path = f.relative_to(FACTS_DIR)
            files.append({
                "name": str(rel_path).replace("\\", "/"),
                "size": size_str,
            })
    return {"files": files}
