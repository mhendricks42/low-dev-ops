"""Build each catalog entry's example: a small Project that check-catalog renders and validates."""

from pydantic import JsonValue

from app.catalog.load import Catalog
from app.catalog.model import CatalogEntry
from app.model import Meta, Naming, Project, Ref, Resource, Subscription

LOCATION = "westeurope"
TENANT_ID = "00000000-0000-0000-0000-000000000000"


def subject_id(entry: CatalogEntry) -> str:
    return f"{entry.caf_abbreviation}1"


def _inputs(entry: CatalogEntry, ref_inputs: set[str]) -> dict[str, JsonValue]:
    fills: dict[str, JsonValue] = {
        "name": entry.example.get("name", f"{entry.caf_abbreviation}-lowdevops-ex"),
        "location": LOCATION,
        "tenant_id": TENANT_ID,
    }
    inputs: dict[str, JsonValue] = {}
    for name, spec in entry.inputs.items():
        if name in ref_inputs:
            continue
        if name in entry.example:
            inputs[name] = entry.example[name]
        elif spec.fill is not None:
            inputs[name] = fills[spec.fill]
        elif spec.tier != "advanced" and "default" in spec.model_fields_set:
            inputs[name] = spec.default
    return inputs


def _add(entry: CatalogEntry, catalog: Catalog, out: dict[str, Resource]) -> str:
    rid = subject_id(entry)
    if rid in out:
        return rid
    refs: list[Ref] = []
    for ref in entry.refs:
        if any(r.input == ref.input for r in refs):
            continue  # the first allowed ref for an input is the example's
        target = catalog.entries[ref.from_]
        if target.module == entry.module:
            continue
        refs.append(Ref(input=ref.input, to=_add(target, catalog, out), output=ref.output))
    out[rid] = Resource(
        id=rid,
        catalog_ref=entry.catalog_ref,
        inputs=_inputs(entry, {r.input for r in refs}),
        refs=refs,
    )
    return rid


def example_project(entry: CatalogEntry, catalog: Catalog) -> Project:
    """The entry's own resource with every basic and hidden input set, after one resource per
    ref target (recursively), so each allowed ref is exercised. Ids are `<abbreviation>1`."""
    resources: dict[str, Resource] = {}
    _add(entry, catalog, resources)
    return Project(
        schema_version=1,
        meta=Meta(name="catalog-example", created="2026-01-01T00:00:00Z", lowdevops_version="0"),
        subscription=Subscription(id=TENANT_ID, tenant_id=TENANT_ID, location=LOCATION),
        naming=Naming(workload="lowdevops", env="ex", region="weu", pattern="{type}-{workload}"),
        resources=list(resources.values()),
    )
