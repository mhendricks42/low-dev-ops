"""M4 exit criteria EC1-EC3 through the API (stub scanners replay real scanner output)."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import GUARDRAILS

client = TestClient(app, base_url="http://127.0.0.1:8000")
pytestmark = pytest.mark.usefixtures("stub_scanners")


def run(fixture: str, monkeypatch: pytest.MonkeyPatch, with_plan: bool = True) -> dict[str, Any]:
    d = GUARDRAILS / fixture
    monkeypatch.setenv("LOWDEVOPS_STUB_DIR", str(d))
    body = {
        "project": json.loads((d / "project.json").read_text()),
        "plan": json.loads((d / "plan.json").read_text()) if with_plan else None,
    }
    response = client.post("/api/guardrails/check", json=body)
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def test_high_finding_blocks_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    # EC1: storage with TLS 1.0 is a high finding, and its waiver is ignored.
    data = run("high", monkeypatch)
    assert data["apply_allowed"] is False
    assert {
        "id": "LDO_ST_TLS",
        "resource": "st1",
        "severity": "high",
        "source": "conftest",
    }.items() <= next(f for f in data["findings"] if f["id"] == "LDO_ST_TLS").items()
    assert [w["waiver"]["findingId"] for w in data["ignored_waivers"]] == ["LDO_ST_TLS"]
    assert data["ignored_waivers"][0]["reason"] == "high findings cannot be waived"
    assert all(f["waivable"] is False for f in data["findings"])


def test_waived_medium_allows_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    # EC2: public storage is medium; with waivers it is allowed and the waivers are listed.
    data = run("waived-medium", monkeypatch)
    assert data["apply_allowed"] is True
    assert data["findings"] == []
    waived = {
        (w["finding"]["id"], w["finding"]["severity"], w["waiver"]["reason"][:7])
        for w in data["waived"]
    }
    assert waived == {("LDO_ST_PUBLIC", "medium", "Sandbox"), ("CKV_AZURE_59", "medium", "Sandbox")}


def test_clean_fixture_has_no_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    # EC3
    data = run("clean", monkeypatch)
    assert data == {
        "findings": [],
        "waived": [],
        "ignored_waivers": [],
        "unused_waivers": [],
        "scanners": ["naming", "tags", "conftest", "checkov", "trivy"],
        "plan_scanned": True,
        "blocked": False,
        "apply_allowed": True,
    }


def test_without_a_plan_apply_is_not_allowed_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    # The plan is optional for checking, but apply needs one: the request's plan is also never
    # trusted for apply (M5 re-runs the checks on the plan the backend produced itself).
    data = run("clean", monkeypatch, with_plan=False)
    assert data["scanners"] == ["naming", "tags", "conftest"]
    assert (data["blocked"], data["plan_scanned"], data["apply_allowed"]) == (False, False, False)


def test_a_plan_that_is_not_an_object_is_422() -> None:
    project = json.loads((GUARDRAILS / "clean" / "project.json").read_text())
    response = client.post("/api/guardrails/check", json={"project": project, "plan": [1, 2]})
    assert response.status_code == 422


def test_check_is_a_write_route_so_foreign_origins_are_refused() -> None:
    project = json.loads((GUARDRAILS / "clean" / "project.json").read_text())
    response = client.post(
        "/api/guardrails/check",
        json={"project": project},
        headers={"origin": "http://evil.example"},
    )
    assert response.status_code == 403
