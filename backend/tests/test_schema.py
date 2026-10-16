import json
from pathlib import Path

from app.schema import (
    catalog_json_schema,
    project_json_schema,
    render_catalog_schema,
    render_schema,
)

COMMITTED = Path(__file__).parents[1] / "schema" / "project.schema.json"


def test_committed_schema_matches_model() -> None:
    assert COMMITTED.read_text() == render_schema(), "schema drifted: run `make schema`"


def test_schema_uses_json_field_names() -> None:
    schema = project_json_schema()
    assert {"schemaVersion", "customHcl", "resources"} <= schema["properties"].keys()
    assert json.loads(render_schema()) == schema


CATALOG_COMMITTED = Path(__file__).parents[2] / "catalog" / "catalog.schema.json"


def test_committed_catalog_schema_matches_model() -> None:
    assert CATALOG_COMMITTED.read_text() == render_catalog_schema(), (
        "catalog schema drifted: run `make schema`"
    )


def test_catalog_schema_uses_yaml_field_names() -> None:
    schema = catalog_json_schema()
    assert {"schemaVersion", "cafAbbreviation", "inputs", "refs"} <= schema["properties"].keys()
    assert "from" in schema["$defs"]["AllowedRef"]["properties"]
