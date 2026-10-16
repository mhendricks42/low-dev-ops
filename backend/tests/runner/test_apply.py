"""EC1: apply only takes the saved, reviewed plan.tfplan, behind every gate, and only once."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.runner import terraform
from app.runner.runs import Run
from tests.conftest import GUARDRAILS
from tests.runner.conftest import NAME, client, current_plan, finished, plan, tf_calls

APPLY = ["apply", "-input=false", "-no-color", "plan.tfplan"]


def apply(sha: str, name: str = NAME, destroy: bool = False) -> tuple[int, Any]:
    response = client.post(
        f"/api/projects/{NAME}/runs/apply",
        json={"planSha256": sha, "confirmName": name, "confirmDestroy": destroy},
    )
    return response.status_code, response.json()


def planned_sha() -> str:
    assert plan().status == "succeeded"
    record = current_plan()
    assert record is not None
    return str(record["planSha256"])


def applies(fake_tf: Path) -> list[Any]:
    return [c["argv"] for c in tf_calls(fake_tf) if c["argv"][0] == "apply"]


def test_a_reviewed_plan_is_applied_once_from_the_saved_file(project: Path, fake_tf: Path) -> None:
    sha = planned_sha()
    status, body = apply(sha)
    assert status == 202
    run = finished(str(body["runId"]))
    assert run.status == "succeeded", run.lines
    assert applies(fake_tf) == [APPLY]
    assert [c["cwd"] for c in tf_calls(fake_tf)][-1] == str(project)
    assert not (project / "plan.tfplan").exists() and current_plan() is None
    status, body = apply(sha)  # single use
    assert status == 409 and body["detail"]["message"].startswith("Plan again")
    assert len(applies(fake_tf)) == 1


def test_apply_without_a_plan_is_409(project: Path, fake_tf: Path) -> None:
    status, _ = apply("0" * 64)
    assert status == 409 and applies(fake_tf) == []


def test_apply_with_another_sha_is_409(project: Path, fake_tf: Path) -> None:
    planned_sha()
    status, _ = apply("0" * 64)
    assert status == 409 and applies(fake_tf) == []


def test_a_changed_plan_file_is_409(project: Path, fake_tf: Path) -> None:
    sha = planned_sha()
    (project / "plan.tfplan").write_text("swapped\n")
    status, _ = apply(sha)
    assert status == 409 and applies(fake_tf) == []
    (project / "plan.tfplan").unlink()
    status, _ = apply(sha)
    assert status == 409 and applies(fake_tf) == []


def test_a_changed_model_is_409(project: Path, fake_tf: Path) -> None:
    sha = planned_sha()
    body = json.loads((project / "project.json").read_text())
    body["tags"]["owner"] = "someone-else"
    assert client.put(f"/api/projects/{NAME}", json={"project": body}).status_code == 200
    status, detail = apply(sha)
    assert status == 409 and "changed" in detail["detail"]["message"]
    assert applies(fake_tf) == []


def test_the_project_name_must_be_typed(project: Path, fake_tf: Path) -> None:
    sha = planned_sha()
    assert apply(sha, name="guardrail")[0] == 422
    assert apply(sha, name="")[0] == 422
    assert applies(fake_tf) == []


def test_destroys_need_a_second_confirmation(project: Path, fake_tf: Path) -> None:
    (fake_tf / "destroy").write_text("")
    sha = planned_sha()
    record = current_plan()
    assert record is not None and record["summary"]["destroys"] == [
        "module.rg1.azurerm_resource_group.this",
        "module.st1.azurerm_storage_account.this",
    ]
    status, body = apply(sha)
    assert status == 422 and "destroys or replaces 2 resources" in body["detail"]["message"]
    status, body = apply(sha, destroy=True)
    assert status == 202 and finished(str(body["runId"])).status == "succeeded"
    assert applies(fake_tf) == [APPLY]


def test_guardrails_that_block_also_block_apply(
    project: Path, fake_tf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOWDEVOPS_STUB_DIR", str(GUARDRAILS / "high"))
    sha = planned_sha()
    status, body = apply(sha)
    assert status == 409 and body["detail"]["message"] == "Guardrails block apply"
    assert body["detail"]["findings"]
    assert applies(fake_tf) == []


def test_a_failed_apply_still_uses_up_the_plan(project: Path, fake_tf: Path) -> None:
    sha = planned_sha()
    (fake_tf / "fail_apply").write_text("")
    status, body = apply(sha)
    run = finished(str(body["runId"]))
    assert (status, run.status, run.exit_code) == (202, "failed", 1)
    assert not (project / "plan.tfplan").exists() and current_plan() is None


def test_a_change_between_the_checks_and_the_run_is_caught(
    project: Path, fake_tf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The gates run before the run holds the project; the run checks again before applying.
    sha = planned_sha()
    start = terraform._start

    def save_in_between(name: str, kind: str, work: Callable[[Run], int]) -> Run:
        body = json.loads((project / "project.json").read_text())
        body["tags"]["owner"] = "someone-else"
        (project / "project.json").write_text(json.dumps(body))
        return start(name, kind, work)

    monkeypatch.setattr(terraform, "_start", save_in_between)
    status, body = apply(sha)
    run = finished(str(body["runId"]))
    assert (status, run.status) == (202, "failed") and run.lines[-1].startswith("Error: Plan again")
    assert applies(fake_tf) == [] and current_plan() is None
