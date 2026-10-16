"""POST /api/guardrails/check: naming, tags, policies and scanners for a project (M4)."""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.catalog import CATALOG
from app.guardrails.findings import Finding
from app.guardrails.run import Report, check
from app.model import Project, Waiver

router = APIRouter(prefix="/api/guardrails")


class CheckRequest(BaseModel):
    project: Project
    # `terraform show -json` output; M5 passes the real one. Without it only naming, tags and
    # Conftest run, because AVM module calls are opaque to the scanners before `terraform init`.
    plan: dict[str, Any] | None = None


def _finding(f: Finding) -> dict[str, Any]:
    return {**asdict(f), "waivable": f.waivable}


def _waiver(w: Waiver) -> dict[str, Any]:
    data: dict[str, Any] = w.model_dump(mode="json", by_alias=True)
    return data


# Plain `def`: the scanners are blocking subprocesses, so FastAPI runs this in a worker thread.
@router.post("/check")
def run_check(body: CheckRequest) -> dict[str, Any]:
    return report_json(check(body.project, CATALOG, body.plan))


def report_json(report: Report) -> dict[str, Any]:
    return {
        "findings": [_finding(f) for f in report.findings],
        "waived": [{"finding": _finding(f), "waiver": _waiver(w)} for f, w in report.waived],
        "ignored_waivers": [{"waiver": _waiver(w), "reason": r} for w, r in report.ignored_waivers],
        "unused_waivers": [_waiver(w) for w in report.unused_waivers],
        "scanners": report.scanners,
        "plan_scanned": report.plan_scanned,
        "blocked": report.blocked,
        "apply_allowed": report.apply_allowed,
    }
