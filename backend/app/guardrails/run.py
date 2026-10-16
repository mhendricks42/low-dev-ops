"""Run every guardrail and apply waivers (M4). High/critical findings block apply."""

import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.catalog.load import Catalog
from app.guardrails import scanners
from app.guardrails.findings import Finding
from app.guardrails.naming import check_names
from app.guardrails.tags import check_tags
from app.model import Project, Waiver

IGNORED_REASON = "high findings cannot be waived"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)  # unwaived, most severe first
    waived: list[tuple[Finding, Waiver]] = field(default_factory=list)
    ignored_waivers: list[tuple[Waiver, str]] = field(default_factory=list)
    unused_waivers: list[Waiver] = field(default_factory=list)
    scanners: list[str] = field(default_factory=list)  # which checks ran

    @property
    def apply_allowed(self) -> bool:
        # Waivers only ever cover medium/low, so anything still blocking is here.
        return all(f.waivable for f in self.findings)


def apply_waivers(findings: list[Finding], waivers: list[Waiver]) -> Report:
    report = Report()
    used: set[int] = set()
    for f in sorted(findings, key=Finding.sort_key):
        match = next(
            (i for i, w in enumerate(waivers) if (w.finding_id, w.resource) == (f.id, f.resource)),
            None,
        )
        if match is None:
            report.findings.append(f)
        elif not f.waivable:
            report.findings.append(f)
            if match not in used:
                report.ignored_waivers.append((waivers[match], IGNORED_REASON))
        else:
            report.waived.append((f, waivers[match]))
        if match is not None:
            used.add(match)
    report.unused_waivers = [w for i, w in enumerate(waivers) if i not in used]
    return report


def _scan(tool: str, scan: Callable[[Path], list[Finding]], files: dict[str, str]) -> list[Finding]:
    # A fresh dir per tool holding only what it scans; deleted afterwards.
    with tempfile.TemporaryDirectory(prefix=f"lowdevops-{tool}-") as tmp:
        workdir = Path(tmp)
        for name, text in files.items():
            (workdir / name).write_text(text)
        try:
            return scan(workdir)
        except scanners.ScannerError as e:
            return [scanners.failed(tool, e)]


def check(project: Project, catalog: Catalog, plan: dict[str, Any] | None = None) -> Report:
    """Naming, tags and Conftest always; Checkov and Trivy when a plan JSON is given.

    AVM module calls are opaque until `terraform init`, so the scanners look at the plan (M5
    passes its real `terraform show -json`).
    """
    found = check_names(project, catalog) + check_tags(project)
    found += _scan("conftest", lambda d: scanners.conftest(project, d), {})
    ran = ["naming", "tags", "conftest"]
    if plan is not None:
        files = {"plan.json": json.dumps(plan)}
        found += _scan("checkov", lambda d: scanners.checkov(project, d), files)
        found += _scan("trivy", lambda d: scanners.trivy(project, plan, d), files)
        ran += ["checkov", "trivy"]
    report = apply_waivers(found, project.waivers)
    report.scanners = ran
    return report
