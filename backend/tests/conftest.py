import json
import os
from pathlib import Path

import pytest

from app.model import Project

FIXTURES = Path(__file__).parent / "fixtures"
VALID = sorted(p.name for p in (FIXTURES / "valid").iterdir())
INVALID = sorted(p.stem for p in (FIXTURES / "invalid").glob("*.json"))


def load_project(name: str) -> Project:
    return Project.model_validate_json((FIXTURES / "valid" / name / "project.json").read_text())


GUARDRAILS = FIXTURES / "guardrails"
STUB_BIN = Path(__file__).parent / "bin"


@pytest.fixture
def stub_scanners(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Put the replaying conftest/checkov/trivy stubs first on PATH; returns their argv log."""
    monkeypatch.setenv("PATH", f"{STUB_BIN}{os.pathsep}{os.environ.get('PATH', '')}")
    log = tmp_path / "scanner-calls.log"
    monkeypatch.setenv("LOWDEVOPS_STUB_LOG", str(log))
    monkeypatch.delenv("LOWDEVOPS_STUB_DIR", raising=False)
    monkeypatch.delenv("LOWDEVOPS_STUB_MODE", raising=False)
    return log


def load_guardrail_fixture(name: str) -> tuple[Project, dict[str, object]]:
    d = GUARDRAILS / name
    plan = json.loads((d / "plan.json").read_text())
    return Project.model_validate_json((d / "project.json").read_text()), plan
