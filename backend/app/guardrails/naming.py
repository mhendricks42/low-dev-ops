"""CAF names that fit each resource type's Azure limits (M4).

The same algorithm lives in frontend/src/model/naming.ts; both run tests/fixtures/naming-cases.json.
"""

import re

from app.catalog.load import Catalog
from app.catalog.model import CatalogEntry, NameRules
from app.guardrails.findings import Finding, Severity
from app.model import Naming, Project

SEPARATORS = "-_."
# Function Apps share the web-site module with App Service; CAF names them func-*.
_KIND_ABBREVIATIONS = {("avm-res-web-site", "functionapp"): "func"}


def abbreviation(entry: CatalogEntry, kind: str | None = None) -> str:
    return _KIND_ABBREVIATIONS.get((entry.module, kind or ""), entry.caf_abbreviation)


def _clean(text: str, entry: CatalogEntry) -> str:
    rules = entry.name_rules
    if rules is None:
        return text
    if rules.lowercase:
        text = text.lower()
    text = re.sub(f"[^{rules.chars}]", "", text)
    # One separator at a time, never at either end.
    text = re.sub(f"[{re.escape(SEPARATORS)}]{{2,}}", lambda m: m.group(0)[0], text)
    return text.strip(SEPARATORS)


def _render(naming: Naming, entry: CatalogEntry, kind: str | None, workload: str) -> str:
    name = (
        naming.pattern.replace("{type}", abbreviation(entry, kind))
        .replace("{workload}", workload)
        .replace("{env}", naming.env)
        .replace("{region}", naming.region)
    )
    return _clean(name, entry)


def caf_name(entry: CatalogEntry, naming: Naming, kind: str | None = None) -> str:
    """Fill the project's pattern, then fit the result to the type's characters and length.

    Characters the type does not allow are dropped (so storage accounts lose their hyphens).
    A name that is too long loses characters from {workload} first, so env and region survive.
    """
    name = _render(naming, entry, kind, naming.workload)
    rules = entry.name_rules
    if rules is None or len(name) <= rules.max:
        return name
    workload = _clean(naming.workload, entry)
    excess = len(name) - rules.max
    name = _render(naming, entry, kind, workload[: max(len(workload) - excess, 0)])
    return name[: rules.max].strip(SEPARATORS)


def _name_findings(
    name: str, entry: CatalogEntry, rules: NameRules, expected: str
) -> list[tuple[str, Severity, str]]:
    found: list[tuple[str, Severity, str]] = []
    if not rules.min <= len(name) <= rules.max:
        found.append(
            (
                "LDO_NAME_LENGTH",
                "high",
                f"name '{name}' is {len(name)} characters; {entry.title} names need "
                f"{rules.min}-{rules.max}",
            )
        )
    if re.sub(f"[{rules.chars}]", "", name) or (rules.lowercase and name != name.lower()):
        allowed = f"[{rules.chars}]" + (", lowercase" if rules.lowercase else "")
        found.append(
            (
                "LDO_NAME_CHARS",
                "high",
                f"name '{name}' has characters {entry.title} names cannot use; allowed: {allowed}",
            )
        )
    # Only worth saying when the name is otherwise valid.
    if not found and name != expected:
        found.append(
            (
                "LDO_NAME_PATTERN",
                "low",
                f"name '{name}' does not follow the project pattern ('{expected}')",
            )
        )
    return found


def check_names(project: Project, catalog: Catalog) -> list[Finding]:
    """High when a name breaks its type's Azure limits; low when it is off the project pattern."""
    found: list[Finding] = []
    for r in project.resources:
        entry = catalog.entries.get(r.catalog_ref.partition("@")[0])
        rules = entry.name_rules if entry else None
        if entry is None or rules is None:
            continue  # unknown modules are reported by the catalog check
        kind = r.inputs.get("kind")
        expected = caf_name(entry, project.naming, kind if isinstance(kind, str) else None)
        for input_name, spec in entry.inputs.items():
            name = r.inputs.get(input_name)
            if spec.fill == "name" and isinstance(name, str):
                found += [
                    Finding(fid, r.id, severity, "naming", message)
                    for fid, severity, message in _name_findings(name, entry, rules, expected)
                ]
    return found
