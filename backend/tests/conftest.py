from pathlib import Path

from app.model import Project

FIXTURES = Path(__file__).parent / "fixtures"
VALID = sorted(p.name for p in (FIXTURES / "valid").iterdir())
INVALID = sorted(p.stem for p in (FIXTURES / "invalid").glob("*.json"))


def load_project(name: str) -> Project:
    return Project.model_validate_json((FIXTURES / "valid" / name / "project.json").read_text())
