"""Check a project against the catalog: known pins, listed inputs and allowed refs."""

from dataclasses import dataclass
from typing import Literal

from app.catalog.load import Catalog
from app.model import Project


@dataclass(frozen=True, order=True)
class CatalogIssue:
    resource: str
    severity: Literal["error", "warning"]
    message: str


def check_project(project: Project, catalog: Catalog) -> list[CatalogIssue]:
    modules = {r.id: r.catalog_ref.partition("@")[0] for r in project.resources}
    issues: list[CatalogIssue] = []
    for r in project.resources:
        module = modules[r.id]
        entry = catalog.get(r.catalog_ref)
        if entry is None:
            known = catalog.entries.get(module)
            message = (
                f"pins {r.catalog_ref}, but the catalog pins {known.version}"
                if known is not None
                else f"'{module}' is not in the catalog"
            )
            issues.append(CatalogIssue(r.id, "error", message))
        else:
            # Unlisted module inputs stay allowed: the catalog lists only the ones worth showing.
            issues += [
                CatalogIssue(r.id, "warning", f"input '{name}' is not listed in the catalog entry")
                for name in r.inputs
                if name not in entry.inputs
            ]
        allowed = {(a.input, a.from_, a.output) for a in entry.refs} if entry else set()
        for ref in r.refs:
            if (ref.input, modules[ref.to], ref.output) not in allowed:
                issues.append(
                    CatalogIssue(
                        r.id,
                        "error",
                        f"ref {ref.input} <- {modules[ref.to]}.{ref.output} is not allowed",
                    )
                )
    return sorted(issues)
