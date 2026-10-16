"""EC4: generated names follow the CAF pattern and each resource type's Azure limits."""

import json
import re

import pytest

from app.catalog.load import CATALOG_DIR, load_catalog
from app.guardrails.naming import caf_name
from app.model import Naming
from tests.conftest import FIXTURES

CATALOG = load_catalog(CATALOG_DIR)
CASES = json.loads((FIXTURES / "naming-cases.json").read_text())
STANDARD = Naming(
    workload="webapp", env="dev", region="weu", pattern="{type}-{workload}-{env}-{region}"
)
NAMINGS = [
    STANDARD,
    Naming(
        workload="a" * 120,
        env="production",
        region="westeurope",
        pattern="{type}-{workload}-{env}-{region}",
    ),
    Naming(
        workload="Web_App!", env="DEV", region="weu", pattern="{type}-{workload}-{env}-{region}"
    ),
    Naming(workload="", env="dev", region="weu", pattern="{type}-{workload}-{env}-{region}"),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_shared_vectors(case: dict[str, object]) -> None:
    # The same vectors run in frontend/src/model/naming.test.ts, so both sides agree.
    # Each vector carries the entry fields it needs, so the frontend test needs no catalog.
    vector = case["entry"]
    assert isinstance(vector, dict)
    entry = CATALOG.entries[vector["module"]]
    assert vector["cafAbbreviation"] == entry.caf_abbreviation  # vectors match the catalog
    assert entry.name_rules and vector["nameRules"] == entry.name_rules.model_dump(by_alias=True)
    naming = Naming.model_validate(case["naming"])
    kind = case.get("kind")
    assert caf_name(entry, naming, kind=str(kind) if kind else None) == case["expected"]


@pytest.mark.parametrize("module", sorted(CATALOG.entries))
@pytest.mark.parametrize("naming", NAMINGS, ids=["standard", "long", "odd-chars", "empty-workload"])
def test_every_generated_name_fits_its_type(module: str, naming: Naming) -> None:
    entry = CATALOG.entries[module]
    rules = entry.name_rules
    assert rules is not None
    name = caf_name(entry, naming)
    assert rules.min <= len(name) <= rules.max, name
    assert re.fullmatch(f"[{rules.chars}]+", name), name
    assert not rules.lowercase or name == name.lower()
    assert not re.search(r"[-_.]{2}", name) and name[0] not in "-_." and name[-1] not in "-_."


@pytest.mark.parametrize("module", sorted(CATALOG.entries))
def test_short_names_follow_the_pattern_exactly(module: str) -> None:
    entry = CATALOG.entries[module]
    expected = f"{entry.caf_abbreviation}-webapp-dev-weu"
    if entry.name_rules and not re.fullmatch(f"[{entry.name_rules.chars}]", "-"):
        expected = expected.replace("-", "")
    assert caf_name(entry, STANDARD) == expected


def test_function_apps_use_func() -> None:
    entry = CATALOG.entries["avm-res-web-site"]
    assert caf_name(entry, STANDARD, kind="functionapp") == "func-webapp-dev-weu"
    assert caf_name(entry, STANDARD, kind="webapp") == "app-webapp-dev-weu"


def test_long_workloads_are_trimmed_before_env_and_region() -> None:
    entry = CATALOG.entries["avm-res-keyvault-vault"]  # max 24
    naming = Naming(workload="inventoryservice", env="prod", region="weu", pattern=STANDARD.pattern)
    assert caf_name(entry, naming) == "kv-inventoryser-prod-weu"
