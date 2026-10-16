"""The real Conftest, Checkov and Trivy agree with the recordings the stubs replay.

These run wherever the scanners are installed (the dev container pins them). Elsewhere they are
skipped with a reason, except when LOWDEVOPS_REQUIRE_SCANNERS=1 (set in the dev container image),
where a missing scanner fails instead.
"""

import os
import shutil
import subprocess

import pytest

from app.catalog.load import CATALOG_DIR, load_catalog
from app.guardrails import scanners
from app.guardrails.run import check
from tests.conftest import load_guardrail_fixture

CATALOG = load_catalog(CATALOG_DIR)
TOOLS = ("conftest", "checkov", "trivy")


def require(*tools: str) -> None:
    missing = [t for t in tools if shutil.which(t) is None]
    if not missing:
        return
    message = f"real scanners not installed: {', '.join(missing)}"
    if os.environ.get("LOWDEVOPS_REQUIRE_SCANNERS") == "1":
        pytest.fail(message + " (LOWDEVOPS_REQUIRE_SCANNERS=1)")
    pytest.skip(message + "; the dev container runs these")


def test_rego_policy_unit_tests_pass() -> None:
    require("conftest")
    done = subprocess.run(  # noqa: S603
        ["conftest", "verify", "--no-color", "--policy", str(scanners.POLICIES_DIR / "conftest")],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr


EXPECTED = {
    "clean": set(),
    "high": {"LDO_ST_TLS", "CKV_AZURE_44", "AZU-0011", "AZU-0059"},
    "waived-medium": set(),
}


@pytest.mark.parametrize("fixture", sorted(EXPECTED))
def test_real_scanners_match_the_recorded_fixture(fixture: str) -> None:
    require(*TOOLS)
    project, plan = load_guardrail_fixture(fixture)
    report = check(project, CATALOG, plan)
    assert {f.id for f in report.findings} == EXPECTED[fixture]
    assert not any(f.id.startswith("LDO_SCANNER_FAILED") for f in report.findings)
    if fixture == "waived-medium":
        assert {f.id for f, _ in report.waived} == {"LDO_ST_PUBLIC", "CKV_AZURE_59"}
