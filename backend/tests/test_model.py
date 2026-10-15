import pytest
from pydantic import ValidationError

from app.model import Project
from tests.conftest import FIXTURES, INVALID, VALID, load_project

# Each invalid fixture breaks exactly one rule; the error must name that rule.
EXPECTED_ERRORS = {
    "bad-id": "String should match pattern",
    "bad-input-name": "String should match pattern",
    "bad-ref-output": "String should match pattern",
    "duplicate-id": "duplicate resource id 'rg1'",
    "dangling-ref": "ref to unknown resource 'rg9'",
    "dangling-parent": "unknown parent 'rg9'",
    "self-ref": "references itself",
    "input-and-ref": "set both as input and ref",
    "unpinned-catalog-ref": "String should match pattern",
    "unknown-field": "Extra inputs are not permitted",
    "wrong-schema-version": "Input should be 1",
    "duplicate-custom-id": "duplicate customHcl id 'c'",
}


@pytest.mark.parametrize("name", VALID)
def test_valid_fixture(name: str) -> None:
    project = load_project(name)
    assert project.resources


def test_every_invalid_fixture_has_an_expected_error() -> None:
    assert sorted(EXPECTED_ERRORS) == INVALID


@pytest.mark.parametrize("name", INVALID)
def test_invalid_fixture_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match=EXPECTED_ERRORS[name]):
        Project.model_validate_json((FIXTURES / "invalid" / f"{name}.json").read_text())


def test_json_round_trip_uses_camel_case() -> None:
    project = load_project("rg-vnet")
    dumped = project.model_dump(mode="json", by_alias=True)
    assert {"schemaVersion", "customHcl"} <= dumped.keys()
    assert "catalogRef" in dumped["resources"][0]
    assert Project.model_validate(dumped) == project


def test_refs_are_sorted_by_input() -> None:
    data = load_project("rg-vnet").model_dump(by_alias=True)
    data["resources"][1]["refs"] = [
        {"input": "z_id", "to": "rg1", "output": "resource_id"},
        {"input": "a_id", "to": "rg1", "output": "resource_id"},
    ]
    refs = Project.model_validate(data).resources[1].refs
    assert [r.input for r in refs] == ["a_id", "z_id"]
