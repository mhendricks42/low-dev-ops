"""Run every guardrail and apply waivers (M4). High/critical findings block apply."""

from dataclasses import dataclass, field

from app.catalog.load import Catalog
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


def check(project: Project, catalog: Catalog) -> Report:
    return apply_waivers(check_names(project, catalog) + check_tags(project), project.waivers)
