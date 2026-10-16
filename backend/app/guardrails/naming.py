"""CAF names that fit each resource type's Azure limits (M4).

The same algorithm lives in frontend/src/model/naming.ts; both run tests/fixtures/naming-cases.json.
"""

import re

from app.catalog.model import CatalogEntry
from app.model import Naming

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
