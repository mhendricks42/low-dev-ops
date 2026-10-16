"""Exit criterion: every entry's basic inputs have CAF defaults, and its allowed refs point at
real outputs. Parametrized over the real catalog, so a new entry is covered automatically."""

import pytest

from app.catalog.load import CATALOG_DIR, load_catalog
from app.catalog.model import CatalogEntry
from tests.conftest import VALID, load_project

CATALOG = load_catalog(CATALOG_DIR)
MODULES = sorted(CATALOG.entries)

# ROADMAP §M2: the foundation set and the compute set.
FOUNDATION = {
    "avm-res-resources-resourcegroup",
    "avm-res-network-virtualnetwork",
    "avm-res-network-networksecuritygroup",
    "avm-res-keyvault-vault",
    "avm-res-storage-storageaccount",
}


def _entry(module: str) -> CatalogEntry:
    return CATALOG.entries[module]


def test_foundation_set_present() -> None:
    assert {m for m, e in CATALOG.entries.items() if e.category == "foundation"} == FOUNDATION


@pytest.mark.parametrize("module", MODULES)
def test_basic_inputs_have_caf_defaults(module: str) -> None:
    entry = _entry(module)
    ref_inputs = {r.input for r in entry.refs}
    for name, spec in entry.inputs.items():
        if spec.tier != "basic":
            continue
        has_value = "default" in spec.model_fields_set or spec.fill is not None
        assert has_value or name in ref_inputs, f"{module}: basic input '{name}' has no default"
        assert spec.description, f"{module}: basic input '{name}' has no description"


@pytest.mark.parametrize("module", MODULES)
def test_every_entry_fills_name(module: str) -> None:
    # Naming (M4) sets `name`, so no entry asks the user to type one from scratch.
    fills = {spec.fill for spec in _entry(module).inputs.values()}
    assert "name" in fills


@pytest.mark.parametrize("module", MODULES)
def test_allowed_refs_point_at_real_outputs(module: str) -> None:
    for ref in _entry(module).refs:
        target = CATALOG.entries[ref.from_]
        assert ref.output in target.outputs, f"{module}.{ref.input} -> {ref.from_}.{ref.output}"


@pytest.mark.parametrize("module", MODULES)
def test_hidden_telemetry_is_off(module: str) -> None:
    # AVM modules send usage telemetry by default; the app opts out for every resource.
    spec = _entry(module).inputs["enable_telemetry"]
    assert (spec.tier, spec.default) == ("hidden", False)


@pytest.mark.parametrize("name", VALID)
def test_fixture_pins_exist_in_catalog(name: str) -> None:
    for resource in load_project(name).resources:
        assert CATALOG.get(resource.catalog_ref), f"{name}: {resource.catalog_ref} not in catalog"
