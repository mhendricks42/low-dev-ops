"""JSON Schemas generated from the models. Run `make schema` after model changes."""

import json
import sys
from typing import Any

from app.catalog.model import CatalogEntry
from app.model import Project


def project_json_schema() -> dict[str, Any]:
    return Project.model_json_schema(by_alias=True)


def catalog_json_schema() -> dict[str, Any]:
    return CatalogEntry.model_json_schema(by_alias=True)


def _render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def render_schema() -> str:
    return _render(project_json_schema())


def render_catalog_schema() -> str:
    return _render(catalog_json_schema())


if __name__ == "__main__":
    print(render_catalog_schema() if sys.argv[1:] == ["catalog"] else render_schema(), end="")
