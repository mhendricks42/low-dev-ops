import pytest

from app.catalog.check_project import CatalogIssue, check_project
from app.catalog.load import CATALOG_DIR, load_catalog
from app.model import Project, Ref
from tests.conftest import VALID, load_project

CATALOG = load_catalog(CATALOG_DIR)


def _vnet_project() -> Project:
    return load_project("rg-vnet")


@pytest.mark.parametrize("name", VALID)
def test_valid_fixtures_have_no_issues(name: str) -> None:
    assert check_project(load_project(name), CATALOG) == []


def test_unknown_module_is_an_error() -> None:
    p = load_project("rg")
    p.resources[0].catalog_ref = "avm-res-missing-thing@1.0.0"
    assert check_project(p, CATALOG) == [
        CatalogIssue("rg1", "error", "'avm-res-missing-thing' is not in the catalog"),
    ]


def test_other_version_is_an_error() -> None:
    p = _vnet_project()
    p.resources[0].catalog_ref = "avm-res-resources-resourcegroup@0.3.0"
    assert check_project(p, CATALOG) == [
        CatalogIssue(
            "rg1",
            "error",
            "pins avm-res-resources-resourcegroup@0.3.0, but the catalog pins 0.4.0",
        ),
    ]


def test_unlisted_input_is_a_warning() -> None:
    p = _vnet_project()
    p.resources[0].inputs["managed_by"] = "someone"
    assert check_project(p, CATALOG) == [
        CatalogIssue("rg1", "warning", "input 'managed_by' is not listed in the catalog entry"),
    ]


def test_ref_the_catalog_does_not_allow_is_an_error() -> None:
    p = _vnet_project()
    p.resources[1].refs = [Ref(input="parent_id", to="rg1", output="name")]
    assert check_project(p, CATALOG) == [
        CatalogIssue(
            "vnet1",
            "error",
            "ref parent_id <- avm-res-resources-resourcegroup.name is not allowed",
        ),
    ]


def test_ref_to_unknown_module_is_not_allowed() -> None:
    p = _vnet_project()
    p.resources[0].catalog_ref = "avm-res-missing-thing@1.0.0"
    issues = check_project(p, CATALOG)
    assert [i.resource for i in issues] == ["rg1", "vnet1"]
    assert issues[1].message == "ref parent_id <- avm-res-missing-thing.resource_id is not allowed"
