import pytest

from app.catalog.example import example_project, subject_id
from app.catalog.load import CATALOG_DIR, load_catalog
from app.hcl.generate import generate
from app.hcl.parse import parse
from tests.conftest import FIXTURES

CATALOG = load_catalog(CATALOG_DIR)
MODULES = sorted(CATALOG.entries)


@pytest.mark.parametrize("module", MODULES)
def test_example_sets_every_basic_input(module: str) -> None:
    entry = CATALOG.entries[module]
    project = example_project(entry, CATALOG)
    subject = next(r for r in project.resources if r.id == subject_id(entry))
    assert subject.catalog_ref == entry.catalog_ref
    set_names = set(subject.inputs) | {r.input for r in subject.refs}
    basic = {n for n, s in entry.inputs.items() if s.tier == "basic"}
    assert basic <= set_names


@pytest.mark.parametrize("module", MODULES)
def test_example_exercises_every_allowed_ref(module: str) -> None:
    entry = CATALOG.entries[module]
    project = example_project(entry, CATALOG)
    by_id = {r.id: r for r in project.resources}
    subject = by_id[subject_id(entry)]
    used = {(r.input, by_id[r.to].catalog_ref.partition("@")[0], r.output) for r in subject.refs}
    for ref in entry.refs:
        assert (ref.input, ref.from_, ref.output) in used


@pytest.mark.parametrize("module", MODULES)
def test_example_round_trips_through_hcl(module: str) -> None:
    project = example_project(CATALOG.entries[module], CATALOG)
    text = generate(project)
    assert parse(text, project) == project
    assert generate(example_project(CATALOG.entries[module], CATALOG)) == text


def test_example_puts_ref_targets_first() -> None:
    entry = CATALOG.entries["avm-res-app-containerapp"]
    ids = [r.id for r in example_project(entry, CATALOG).resources]
    assert ids == ["rg1", "cae1", "ca1"]


def test_example_overrides_and_fills() -> None:
    minimal = load_catalog(FIXTURES / "catalog-minimal")
    project = example_project(minimal.entries["avm-res-network-virtualnetwork"], minimal)
    rg, vnet = project.resources
    assert rg.inputs == {
        "enable_telemetry": False,
        "location": "westeurope",
        "name": "rg-lowdevops-ex",
    }
    assert vnet.inputs["address_space"] == ["10.0.0.0/16"]
    assert [(r.input, r.to, r.output) for r in vnet.refs] == [("parent_id", "rg1", "resource_id")]


def test_example_fills_tenant_id() -> None:
    project = example_project(CATALOG.entries["avm-res-keyvault-vault"], CATALOG)
    kv = project.resources[-1]
    assert kv.inputs["tenant_id"] == project.subscription.tenant_id
    assert kv.inputs["name"] == "kv-lowdevops-ex"
