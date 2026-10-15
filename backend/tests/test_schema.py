import json
from pathlib import Path

from app.schema import project_json_schema, render_schema

COMMITTED = Path(__file__).parents[1] / "schema" / "project.schema.json"


def test_committed_schema_matches_model() -> None:
    assert COMMITTED.read_text() == render_schema(), "schema drifted: run `make schema`"


def test_schema_uses_json_field_names() -> None:
    schema = project_json_schema()
    assert {"schemaVersion", "customHcl", "resources"} <= schema["properties"].keys()
    assert json.loads(render_schema()) == schema
