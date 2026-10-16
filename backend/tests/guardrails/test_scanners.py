"""Scanner adapters against stubs that replay real Conftest/Checkov/Trivy output."""

import json
import os
import time
from pathlib import Path

import pytest

from app.catalog.load import CATALOG_DIR, load_catalog
from app.guardrails import scanners
from app.guardrails.run import check
from tests.conftest import GUARDRAILS, load_guardrail_fixture

CATALOG = load_catalog(CATALOG_DIR)

pytestmark = pytest.mark.usefixtures("stub_scanners")


def ids(fixture: str, monkeypatch: pytest.MonkeyPatch) -> set[tuple[str, str, str]]:
    monkeypatch.setenv("LOWDEVOPS_STUB_DIR", str(GUARDRAILS / fixture))
    project, plan = load_guardrail_fixture(fixture)
    report = check(project, CATALOG, plan)
    return {(f.source, f.id, f.resource) for f in report.findings}


def test_each_scanner_maps_findings_back_to_the_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    assert ids("high", monkeypatch) == {
        ("conftest", "LDO_ST_TLS", "st1"),
        ("checkov", "CKV_AZURE_44", "st1"),
        ("trivy", "AZU-0011", "st1"),  # Trivy names it by md5("module.st1")
        ("trivy", "AZU-0059", "st1"),
    }


def test_curated_severity_wins_over_the_scanners_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOWDEVOPS_STUB_DIR", str(GUARDRAILS / "high"))
    project, plan = load_guardrail_fixture("high")
    severities = {f.id: f.severity for f in check(project, CATALOG, plan).findings}
    assert severities["CKV_AZURE_44"] == "high"  # free Checkov reports no severity at all
    assert severities["AZU-0011"] == "critical"


def test_scanners_run_on_argument_lists_in_a_temp_dir_that_is_removed(stub_scanners: Path) -> None:
    project, plan = load_guardrail_fixture("clean")
    check(project, CATALOG, plan)
    calls = [json.loads(line) for line in stub_scanners.read_text().splitlines()]
    assert [c[0] for c in calls] == ["conftest", "checkov", "trivy"]
    conftest, checkov, _ = calls
    assert conftest[-3] == "input.json" and str(scanners.POLICIES_DIR / "conftest") in conftest
    assert checkov[checkov.index("--check") + 1] == ",".join(
        sorted(scanners.curated_checks("checkov"))
    )
    for call in calls:
        assert call[-2] == "env:"  # scanner config variables are stripped
        cwd = Path(call[-1])
        assert cwd.name.startswith(f"lowdevops-{call[0]}-")
        assert not cwd.exists()


def test_without_a_plan_only_conftest_runs(stub_scanners: Path) -> None:
    project, _ = load_guardrail_fixture("clean")
    report = check(project, CATALOG)
    assert report.scanners == ["naming", "tags", "conftest"]
    assert [json.loads(line)[0] for line in stub_scanners.read_text().splitlines()] == ["conftest"]


@pytest.mark.parametrize("mode", ["garbage", "crash", "wrong-shape"])
def test_a_broken_scanner_blocks_apply(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setenv("LOWDEVOPS_STUB_MODE", mode)
    project, plan = load_guardrail_fixture("clean")
    report = check(project, CATALOG, plan)
    assert report.blocked
    assert {(f.id, f.severity) for f in report.findings} == {
        (f"LDO_SCANNER_FAILED:{tool}", "high") for tool in ("conftest", "checkov", "trivy")
    }


def test_a_missing_scanner_blocks_apply(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # no scanners at all
    project, plan = load_guardrail_fixture("clean")
    report = check(project, CATALOG, plan)
    assert report.blocked
    assert {f.message.split(" ")[0] for f in report.findings} == {"conftest", "checkov", "trivy"}
    assert all("is not installed" in f.message for f in report.findings)


def test_a_waiver_on_a_scanner_failure_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOWDEVOPS_STUB_MODE", "crash")
    project, _ = load_guardrail_fixture("clean")
    waiver = {
        "findingId": "LDO_SCANNER_FAILED:conftest",
        "resource": "project",
        "reason": "x" * 20,
        "by": "me",
        "at": "now",
    }
    project = project.model_validate({**project.model_dump(by_alias=True), "waivers": [waiver]})
    report = check(project, CATALOG)
    assert report.blocked and report.ignored_waivers


def test_scanner_config_variables_never_reach_a_scanner(
    stub_scanners: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # e.g. TRIVY_IGNOREFILE or CKV_SKIP_CHECK in the API's environment could silence checks.
    monkeypatch.setenv("TRIVY_IGNOREFILE", "ignore-everything.yaml")
    monkeypatch.setenv("CKV_SKIP_CHECK", "CKV_AZURE_44")
    project, plan = load_guardrail_fixture("clean")
    check(project, CATALOG, plan)
    assert all(json.loads(line)[-2] == "env:" for line in stub_scanners.read_text().splitlines())


def test_a_plan_with_no_resources_is_not_clean() -> None:
    project, _ = load_guardrail_fixture("clean")
    report = check(project, CATALOG, {})
    assert report.blocked
    assert [f.id for f in report.findings] == ["LDO_SCANNER_FAILED:plan"]


def test_a_timeout_kills_the_scanner_and_its_workers(
    stub_scanners: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOWDEVOPS_STUB_MODE", "hang")
    monkeypatch.setattr(scanners, "TIMEOUT_SECONDS", 2)
    project, _ = load_guardrail_fixture("clean")
    report = check(project, CATALOG)
    assert [f.id for f in report.findings] == ["LDO_SCANNER_FAILED:conftest"]
    assert "took longer than 2 s" in report.findings[0].message
    child = int(Path(f"{stub_scanners}.child").read_text())
    for _ in range(50):  # the group is killed; give the kernel a moment to reap
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    pytest.fail(f"worker {child} survived the timeout")


def test_checkov_cannot_read_a_home_config(stub_scanners: Path) -> None:
    # A ~/.checkov.yaml with skip-check could silence a curated check, so Checkov's HOME is its
    # own empty temp workdir. The other scanners keep the real HOME.
    project, plan = load_guardrail_fixture("clean")
    check(project, CATALOG, plan)
    calls = {
        json.loads(line)[0]: json.loads(line)[-1] for line in stub_scanners.read_text().splitlines()
    }
    assert Path(f"{stub_scanners}.home.checkov").read_text() == calls["checkov"]
    assert Path(f"{stub_scanners}.home.trivy").read_text() == os.environ["HOME"]
