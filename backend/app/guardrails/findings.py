"""Guardrail findings and severity tiers (M4, PRD "Guardrail failures")."""

from dataclasses import dataclass
from typing import Literal

Severity = Literal["critical", "high", "medium", "low"]
Source = Literal["naming", "tags", "conftest", "checkov", "trivy", "guardrails"]

SEVERITY_ORDER: dict[Severity, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}
BLOCKING: frozenset[Severity] = frozenset({"critical", "high"})  # never waivable


@dataclass(frozen=True)
class Finding:
    id: str  # e.g. LDO_NAME_LENGTH, CKV_AZURE_35, AVD-AZU-0012
    resource: str  # resource id, or "project"
    severity: Severity
    source: Source
    message: str

    @property
    def waivable(self) -> bool:
        return self.severity not in BLOCKING

    def sort_key(self) -> tuple[int, str, str]:
        return (SEVERITY_ORDER[self.severity], self.resource, self.id)
