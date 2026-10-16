"""Plan and apply a project with Terraform (M5). Runs stream at /api/runs/{runId}/log."""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.api.guardrails import report_json
from app.api.projects import Name
from app.runner import terraform
from app.runner.runs import REGISTRY

router = APIRouter(prefix="/api/projects/{name}/runs")


class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PlanRequest(_Body):
    subscription_id: str = Field(max_length=64)


class ApplyRequest(_Body):
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_name: str = Field(max_length=64)
    confirm_destroy: bool = False


@router.post("/plan", status_code=202)
def plan(name: Name, body: PlanRequest) -> dict[str, str]:
    return {"runId": terraform.start_plan(name, body.subscription_id).id}


@router.post("/apply", status_code=202)
def apply(name: Name, body: ApplyRequest) -> dict[str, str]:
    run = terraform.start_apply(name, body.plan_sha256, body.confirm_name, body.confirm_destroy)
    return {"runId": run.id}


@router.get("/current")
def current(name: Name) -> dict[str, Any]:
    run = REGISTRY.current(terraform.key(name))
    record = terraform.plan_record(name)
    return {
        "run": run.summary() if run else None,
        "plan": None
        if record is None
        else {
            "planSha256": record.plan_sha256,
            "modelSha256": record.model_sha256,
            "subscriptionId": record.subscription_id,
            "createdAt": record.created_at,
            "summary": {
                "changes": [asdict(c) for c in record.summary.changes],
                "destroys": record.summary.destroys,
                "text": record.summary.text(),
            },
            "guardrails": report_json(record.report),
        },
    }
