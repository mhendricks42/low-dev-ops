import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import settings
from app.main import app
from app.runner import terraform
from app.runner.runs import REGISTRY, Run
from tests.conftest import GUARDRAILS, STUB_BIN

SUB = "00000000-0000-0000-0000-000000000000"
NAME = "guardrails"  # meta.name of the clean guardrail fixture
client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture
def fake_tf(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Put the fake terraform (tests/bin/terraform) first on PATH; returns its state dir."""
    state = tmp_path / "tf-state"
    state.mkdir()
    monkeypatch.setenv("PATH", f"{STUB_BIN}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("LOWDEVOPS_FAKE_TF_STATE", str(state))
    return state


@pytest.fixture
def project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_az: Path,
    fake_tf: Path,
    stub_scanners: Path,
) -> Path:
    """A saved project with a bootstrapped backend; returns the project dir."""
    monkeypatch.setenv("LOWDEVOPS_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setattr(terraform, "_PLANS", {})
    body = json.loads((GUARDRAILS / "clean" / "project.json").read_text())
    assert client.put(f"/api/projects/{NAME}", json={"project": body}).status_code == 200
    settings.record_backend(
        SUB,
        settings.Backend(
            resource_group="rg-lowdevops-state",
            storage_account="stlowdevopsabc",
            container="tfstate",
            location="westeurope",
        ),
    )
    return (tmp_path / "ws" / NAME).resolve()


def tf_calls(state: Path) -> list[Any]:
    log = state / "calls.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def finished(run_id: str) -> Run:
    run = REGISTRY.get(run_id)
    assert run is not None and run.wait(30), "run did not finish"
    return run


def plan(subscription_id: str = SUB) -> Run:
    response = client.post(
        f"/api/projects/{NAME}/runs/plan", json={"subscriptionId": subscription_id}
    )
    assert response.status_code == 202, response.text
    return finished(response.json()["runId"])


def current_plan() -> Any:
    plan_record: Any = client.get(f"/api/projects/{NAME}/runs/current").json()["plan"]
    return plan_record
