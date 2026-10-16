"""Severity tiers and waivers: high/critical block apply; only medium/low can be waived."""

from app.catalog.load import CATALOG_DIR, Catalog, load_catalog
from app.guardrails.findings import Finding
from app.guardrails.naming import check_names
from app.guardrails.run import apply_waivers
from app.guardrails.tags import check_tags
from app.model import Waiver
from tests.conftest import load_project

CATALOG = load_catalog(CATALOG_DIR)


def finding(severity: str, fid: str = "X1", resource: str = "rg1") -> Finding:
    return Finding(id=fid, resource=resource, severity=severity, source="conftest", message="m")  # type: ignore[arg-type]


def waiver(fid: str = "X1", resource: str = "rg1") -> Waiver:
    return Waiver(
        finding_id=fid,
        resource=resource,
        reason="accepted for the sandbox",
        by="me",
        at="2026-10-16",
    )


def test_high_finding_blocks_and_cannot_be_waived() -> None:
    report = apply_waivers([finding("high")], [waiver()])
    assert report.blocked
    assert report.findings == [finding("high")]
    assert report.ignored_waivers == [(waiver(), "high findings cannot be waived")]
    assert report.waived == []


def test_critical_blocks_too() -> None:
    assert apply_waivers([finding("critical")], []).blocked


def test_waived_medium_is_moved_out_and_allows_apply() -> None:
    report = apply_waivers([finding("medium"), finding("low", "X2")], [waiver()])
    assert not report.blocked
    assert report.waived == [(finding("medium"), waiver())]
    assert report.findings == [finding("low", "X2")]  # unwaived low is shown, not blocking


def test_waiver_must_match_resource_too_and_unused_ones_are_listed() -> None:
    report = apply_waivers([finding("medium", resource="st1")], [waiver(resource="rg1")])
    assert report.findings == [finding("medium", resource="st1")]
    assert report.unused_waivers == [waiver(resource="rg1")]


def test_findings_sort_by_severity_then_resource() -> None:
    found = [
        finding("low", "A"),
        finding("high", "B", "z"),
        finding("medium", "C"),
        finding("high", "D", "a"),
    ]
    assert [f.id for f in apply_waivers(found, []).findings] == ["D", "B", "C", "A"]


def test_names_that_break_type_limits_are_high() -> None:
    project = load_project("rg")
    rg = project.resources[0]
    bad = rg.model_copy(update={"inputs": {**rg.inputs, "name": "rg-" + "x" * 100}})
    found = check_names(project.model_copy(update={"resources": [bad]}), CATALOG)
    assert [(f.id, f.severity) for f in found] == [("LDO_NAME_LENGTH", "high")]
    odd = rg.model_copy(update={"inputs": {**rg.inputs, "name": "rg webapp!"}})
    found = check_names(project.model_copy(update={"resources": [odd]}), CATALOG)
    assert ("LDO_NAME_CHARS", "high") in [(f.id, f.severity) for f in found]


def test_names_off_the_pattern_are_low_and_on_pattern_are_clean() -> None:
    project = load_project("rg")
    assert check_names(project, CATALOG) == []
    rg = project.resources[0]
    other = rg.model_copy(update={"inputs": {**rg.inputs, "name": "rg-legacy"}})
    found = check_names(project.model_copy(update={"resources": [other]}), CATALOG)
    assert [(f.id, f.severity, f.resource) for f in found] == [("LDO_NAME_PATTERN", "low", "rg1")]


def test_missing_required_tags_are_medium_per_resource() -> None:
    project = load_project("rg").model_copy(
        update={"tags": {"env": "dev"}, "required_tags": ["env", "owner"]}
    )
    found = check_tags(project, CATALOG)
    assert [(f.id, f.severity, f.resource) for f in found] == [
        ("LDO_TAG_MISSING:owner", "medium", "rg1")
    ]
    assert "owner" in found[0].message
    rg = project.resources[0]
    own = rg.model_copy(update={"inputs": {**rg.inputs, "tags": {"owner": "me"}}})
    assert check_tags(project.model_copy(update={"resources": [own]}), CATALOG) == []


def test_each_missing_tag_is_its_own_waivable_finding() -> None:
    # A waiver matches (finding id, resource), so one waiver must cover exactly one problem.
    project = load_project("rg").model_copy(update={"tags": {}, "required_tags": ["env", "owner"]})
    found = check_tags(project, CATALOG)
    assert [f.id for f in found] == ["LDO_TAG_MISSING:env", "LDO_TAG_MISSING:owner"]
    report = apply_waivers(found, [waiver("LDO_TAG_MISSING:owner")])
    assert [f.id for f in report.findings] == ["LDO_TAG_MISSING:env"]


def test_repeated_scanner_hits_on_one_resource_collapse_to_the_most_severe() -> None:
    # e.g. Checkov failing the same check on two NSG rules inside module.nsg1
    found = [finding("medium", "CKV_X"), finding("high", "CKV_X"), finding("low", "CKV_Y")]
    report = apply_waivers(found, [])
    assert [(f.id, f.severity) for f in report.findings] == [("CKV_X", "high"), ("CKV_Y", "low")]


def test_apply_also_needs_a_scanned_plan() -> None:
    report = apply_waivers([], [])
    assert not report.blocked and not report.apply_allowed  # nothing found, but no plan read
    report.plan_scanned = True
    assert report.apply_allowed


def test_tags_are_only_required_where_the_module_takes_them() -> None:
    # A resource whose catalog entry has no `tags` input (or an unknown module) cannot be fixed.
    project = load_project("rg").model_copy(update={"tags": {}, "required_tags": ["env"]})
    rg = CATALOG.entries["avm-res-resources-resourcegroup"]
    untaggable = rg.model_copy(
        update={"inputs": {k: v for k, v in rg.inputs.items() if k != "tags"}}
    )
    catalog = Catalog({**CATALOG.entries, rg.module: untaggable})
    assert check_tags(project, catalog) == []
    unknown = project.resources[0].model_copy(update={"catalog_ref": "avm-res-unknown-thing@1.0.0"})
    assert check_tags(project.model_copy(update={"resources": [unknown]}), CATALOG) == []
