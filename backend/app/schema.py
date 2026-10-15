"""JSON Schema for project.json, generated from the model. Run `make schema` after model changes."""

import json
from typing import Any

from app.model import Project


def project_json_schema() -> dict[str, Any]:
    return Project.model_json_schema(by_alias=True)


def render_schema() -> str:
    return json.dumps(project_json_schema(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    print(render_schema(), end="")
