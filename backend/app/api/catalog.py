from typing import Any

from fastapi import APIRouter

from app.catalog.load import load_catalog

router = APIRouter(prefix="/api")
CATALOG = load_catalog()


@router.get("/catalog")
def catalog() -> dict[str, list[dict[str, Any]]]:
    entries = [CATALOG.entries[m] for m in sorted(CATALOG.entries)]
    return {"entries": [e.model_dump(mode="json", by_alias=True) for e in entries]}
