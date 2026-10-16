"""B1: plan regenerates main.tf, writes runtime.tf, runs init/plan/show and records the plan."""

import hashlib
import json
from pathlib import Path

import pytest

from app.hcl.generate import generate
from app.model import Project
from app.runner import terraform
from tests.conftest import GUARDRAILS
from tests.runner.conftest import NAME, SUB, client, current_plan, finished, plan, tf_calls

CLEAN_PLAN = json.loads((GUARDRAILS / "clean" / "plan.json").read_text())


def test_plan_runs_terraform_in_the_project_with_the_backend_and_records_the_plan(
    project: Path, fake_tf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARM_CLIENT_SECRET", "leak")
    monkeypatch.setenv("TF_VAR_admin_password", "leak")
    monkeypatch.setenv("ARM_SUBSCRIPTION_ID", "ffffffff-0000-0000-0000-000000000000")
    run = plan()
    assert run.status == "succeeded", run.lines
    calls = tf_calls(fake_tf)
    assert [c["argv"] for c in calls] == [
        [
            "init", "-input=false", "-no-color", "-reconfigure",
            "-backend-config=resource_group_name=rg-lowdevops-state",
            "-backend-config=storage_account_name=stlowdevopsabc",
            "-backend-config=container_name=tfstate",
            f"-backend-config=key={NAME}.tfstate",
            "-backend-config=use_azuread_auth=true",
            f"-backend-config=subscription_id={SUB}",
        ],
        ["plan", "-input=false", "-no-color", "-out=plan.tfplan"],
        ["show", "-no-color", "-json", "plan.tfplan"],
    ]  # fmt: skip
    for call in calls:
        assert call["cwd"] == str(project)
        assert call["env"] == {
            "ARM_USE_CLI": "true",
            "ARM_SUBSCRIPTION_ID": SUB,
            "TF_IN_AUTOMATION": "1",
            "TF_INPUT": "0",
        }
    model = (project / "project.json").read_bytes()
    assert (project / "main.tf").read_text() == generate(Project.model_validate_json(model))
    assert (project / "runtime.tf").read_text() == terraform.RUNTIME_TF
    record = current_plan()
    assert record is not None
    assert (
        record["planSha256"] == hashlib.sha256((project / "plan.tfplan").read_bytes()).hexdigest()
    )
    assert record["modelSha256"] == hashlib.sha256(model).hexdigest()
    assert record["summary"]["text"] == "5 to add, 0 to change, 0 to destroy"
    assert record["summary"]["destroys"] == []
    assert [c["action"] for c in record["summary"]["changes"]] == ["create"] * 5
    guardrails = record["guardrails"]
    assert isinstance(guardrails, dict) and guardrails["apply_allowed"] is True
    assert guardrails["scanners"] == ["naming", "tags", "conftest", "checkov", "trivy"]
    log = (project / "run.log").read_text().splitlines()
    assert log[0].startswith("$ terraform init") and log[-1] == run.lines[-1]
    assert run.lines[-1] == "Plan ready: 5 to add, 0 to change, 0 to destroy."


def test_plan_needs_the_projects_own_subscription(project: Path, fake_tf: Path) -> None:
    other = "ffffffff-0000-0000-0000-000000000000"
    response = client.post(f"/api/projects/{NAME}/runs/plan", json={"subscriptionId": other})
    assert response.status_code == 422
    assert tf_calls(fake_tf) == []
    assert plan(SUB.upper()).status == "succeeded"  # ids compare case-insensitively


def test_plan_needs_az_access_and_a_bootstrapped_backend(
    project: Path, fake_az: Path, fake_tf: Path, tmp_path: Path
) -> None:
    (fake_az / "logged_out").write_text("")
    response = client.post(f"/api/projects/{NAME}/runs/plan", json={"subscriptionId": SUB})
    assert response.status_code == 409 and "az login" in response.json()["detail"]["message"]
    (fake_az / "logged_out").unlink()
    (tmp_path / "ws" / "settings.json").unlink()
    response = client.post(f"/api/projects/{NAME}/runs/plan", json={"subscriptionId": SUB})
    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "Bootstrap the state backend first"
    assert tf_calls(fake_tf) == []


def test_a_failed_plan_leaves_nothing_to_apply(project: Path, fake_tf: Path) -> None:
    assert plan().status == "succeeded" and current_plan() is not None
    (fake_tf / "fail_plan").write_text("")
    run = plan()
    assert (run.status, run.exit_code) == ("failed", 1)
    assert current_plan() is None and not (project / "plan.tfplan").exists()


def test_a_second_run_while_one_plans_is_409_with_its_id(project: Path, fake_tf: Path) -> None:
    (fake_tf / "block").write_text("")
    first = client.post(f"/api/projects/{NAME}/runs/plan", json={"subscriptionId": SUB})
    assert first.status_code == 202
    run_id = first.json()["runId"]
    try:
        second = client.post(f"/api/projects/{NAME}/runs/plan", json={"subscriptionId": SUB})
        assert second.status_code == 409 and second.json()["detail"]["runId"] == run_id
        running = client.get(f"/api/projects/{NAME}/runs/current").json()["run"]
        assert running["id"] == run_id and running["status"] == "running"
    finally:
        (fake_tf / "block").unlink()
        finished(run_id)


def test_summary_counts_replaces_and_lists_what_is_destroyed() -> None:
    changes = [
        {"address": "a", "mode": "managed", "change": {"actions": ["create"]}},
        {"address": "b", "mode": "managed", "change": {"actions": ["update"]}},
        {"address": "c", "mode": "managed", "change": {"actions": ["delete"]}},
        {"address": "d", "mode": "managed", "change": {"actions": ["delete", "create"]}},
        {"address": "e", "mode": "managed", "change": {"actions": ["create", "delete"]}},
        {"address": "f", "mode": "managed", "change": {"actions": ["no-op"]}},
        {"address": "g", "mode": "data", "change": {"actions": ["read"]}},
    ]
    summary = terraform.summarize({"resource_changes": changes})
    assert [(c.address, c.action) for c in summary.changes] == [
        ("a", "create"), ("b", "update"), ("c", "delete"), ("d", "replace"), ("e", "replace"),
    ]  # fmt: skip
    assert summary.destroys == ["c", "d", "e"]
    assert summary.text() == "3 to add, 1 to change, 3 to destroy"
    assert terraform.summarize(CLEAN_PLAN).count("create") == 5
