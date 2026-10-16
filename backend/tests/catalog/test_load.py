from pathlib import Path

import pytest

from app.catalog.load import CatalogError, load_catalog
from tests.conftest import FIXTURES

MINIMAL = FIXTURES / "catalog-minimal"
INVALID_DIR = FIXTURES / "catalog-invalid"
INVALID = sorted(p.name for p in INVALID_DIR.iterdir())

# Each invalid catalog breaks exactly one rule; the error must name that rule.
EXPECTED_ERRORS = {
    "bad-input-name": "String should match pattern",
    "basic-without-default": "basic input 'address_space' needs a default",
    "default-and-fill": "input 'name' has both a default and a fill",
    "duplicate-output": "duplicate output 'name'",
    "example-unknown-input": "example sets unlisted input 'colour'",
    "file-name-mismatch": "does not match module 'avm-res-network-virtualnetwork'",
    "hidden-without-default": "hidden input 'enable_telemetry' needs a default",
    "non-finite-default": "must be a finite number",
    "not-a-mapping": "must be a YAML mapping",
    "python-tag": "could not determine a constructor",
    "ranged-version": "String should match pattern",
    "ref-input-unlisted": "ref input 'parent_id' is not listed under inputs",
    "ref-unknown-entry": "ref to unknown catalog entry 'avm-res-missing'",
    "ref-unknown-output": "has no output 'id'",
    "reserved-input": "reserved module argument 'count'",
    "unknown-field": "Extra inputs are not permitted",
    "unknown-fill": "Input should be 'name', 'location' or 'tenant_id'",
    "unknown-tier": "Input should be 'basic', 'advanced' or 'hidden'",
    "yaml-syntax": "YAML",
}


def test_minimal_catalog_loads() -> None:
    catalog = load_catalog(MINIMAL)
    assert sorted(catalog.entries) == [
        "avm-res-network-virtualnetwork",
        "avm-res-resources-resourcegroup",
    ]
    vnet = catalog.entries["avm-res-network-virtualnetwork"]
    assert vnet.inputs["address_space"].default == ["10.0.0.0/16"]
    assert vnet.refs[0].from_ == "avm-res-resources-resourcegroup"


def test_get_matches_exact_pin_only() -> None:
    catalog = load_catalog(MINIMAL)
    assert catalog.get("avm-res-resources-resourcegroup@0.4.0") is not None
    assert catalog.get("avm-res-resources-resourcegroup@0.4.1") is None
    assert catalog.get("avm-res-missing@1.0.0") is None
    assert catalog.get("not-a-ref") is None


def test_every_invalid_catalog_has_an_expected_error() -> None:
    assert sorted(EXPECTED_ERRORS) == INVALID


@pytest.mark.parametrize("name", INVALID)
def test_invalid_catalog_rejected(name: str) -> None:
    with pytest.raises(CatalogError) as err:
        load_catalog(INVALID_DIR / name)
    assert EXPECTED_ERRORS[name] in str(err.value)


def test_error_names_the_file() -> None:
    with pytest.raises(CatalogError) as err:
        load_catalog(INVALID_DIR / "hidden-without-default")
    assert "avm-res-resources-resourcegroup.yaml" in str(err.value)


def test_empty_directory_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="no catalog entries"):
        load_catalog(tmp_path)
