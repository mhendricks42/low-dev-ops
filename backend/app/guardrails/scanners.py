"""Conftest, Checkov and Trivy as subprocesses (M4).

Each tool runs on an argument list (never a shell) with a timeout, in a fresh temp dir that holds
only what it scans. Anything other than parseable output becomes a blocking LDO_SCANNER_FAILED
finding, so a broken scanner can never make a project look clean.
"""

import hashlib
import json
import os
import shutil
import signal
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from app.guardrails.findings import Finding, Severity
from app.model import Project

POLICIES_DIR = Path(__file__).resolve().parents[3] / "policies"
TIMEOUT_SECONDS = 120
_SEVERITIES = {"critical", "high", "medium", "low"}


class ScannerError(Exception):
    pass


def curated_checks(tool: str) -> dict[str, Severity]:
    table = yaml.safe_load((POLICIES_DIR / "scanners.yaml").read_text())
    checks: dict[str, Severity] = {}
    for check_id, severity in table[tool].items():
        if severity not in _SEVERITIES:
            raise ScannerError(
                f"policies/scanners.yaml: {check_id} has unknown severity {severity}"
            )
        checks[str(check_id)] = severity
    return checks


# Settings these tools read from the environment (e.g. TRIVY_IGNOREFILE, CKV_SKIP_CHECK) could
# silence checks, so they never reach a scanner.
_CONFIG_PREFIXES = ("CHECKOV_", "CKV_", "BC_", "PRISMA_", "TRIVY_", "CONFTEST_")


def _env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith(_CONFIG_PREFIXES)}


def _run(args: list[str], cwd: Path, ok_codes: set[int]) -> Any:
    tool = args[0]
    binary = shutil.which(tool)  # an absolute path, resolved on the API's PATH
    if binary is None:
        raise ScannerError(f"{tool} is not installed")
    # Own process group, so a timeout kills the scanner and everything it started.
    with (
        subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
            [binary, *args[1:]],
            cwd=cwd,
            env=_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        ) as process
    ):
        try:
            stdout, stderr = process.communicate(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as e:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise ScannerError(f"{tool} took longer than {TIMEOUT_SECONDS} s") from e
    if process.returncode not in ok_codes:
        tail = (stderr or stdout).strip().splitlines()[-1:] or ["no output"]
        raise ScannerError(f"{tool} exited with {process.returncode}: {tail[0][:200]}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise ScannerError(f"{tool} printed output that is not JSON") from e


def plan_resource_count(plan: dict[str, Any]) -> int:
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        return 0
    return sum(1 for c in changes if isinstance(c, dict) and c.get("mode") == "managed")


def failed(tool: str, error: ScannerError) -> Finding:
    return Finding(
        id=f"LDO_SCANNER_FAILED:{tool}",
        resource="project",
        severity="high",
        source="guardrails",
        message=f"{tool} could not check this project, so apply stays blocked: {error}",
    )


# --- Conftest: policies/conftest/*.rego on the project model ---------------------------------


def conftest_input(project: Project) -> dict[str, Any]:
    return {
        "resources": [
            {"id": r.id, "module": r.catalog_ref.partition("@")[0], "inputs": r.inputs}
            for r in project.resources
        ]
    }


def conftest(project: Project, workdir: Path) -> list[Finding]:
    (workdir / "input.json").write_text(json.dumps(conftest_input(project)))
    args = [
        "conftest",
        "test",
        "--no-color",
        "--output",
        "json",
        "--parser",
        "json",
        "--policy",
        str(POLICIES_DIR / "conftest"),
        "input.json",
    ]
    data = _run(args, workdir, ok_codes={0, 1})  # 1 means "a policy failed"
    # One input file, so exactly one result: anything else means nothing was evaluated.
    if not (isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict)):
        raise ScannerError("conftest output has an unexpected shape")
    ids = {r.id for r in project.resources}
    found: list[Finding] = []
    for result in data:
        for key, severity in (("failures", "high"), ("warnings", "medium")):
            for item in result.get(key) or []:
                meta = item.get("metadata") or {}
                resource = meta.get("resource")
                found.append(
                    Finding(
                        id=str(meta.get("id", "LDO_POLICY")),
                        resource=resource if resource in ids else "project",
                        severity=severity,  # type: ignore[arg-type]  # one of the two literals
                        source="conftest",
                        message=str(item.get("msg", "")),
                    )
                )
    return found


# --- Checkov and Trivy: the plan JSON (`terraform show -json`) --------------------------------


def _module_addresses(module: dict[str, Any]) -> Iterator[str]:
    for child in module.get("child_modules") or []:
        if isinstance(child.get("address"), str):
            yield child["address"]
        yield from _module_addresses(child)


def _resource_of(address: str, ids: set[str]) -> str:
    # module.st1.azurerm_storage_account.this -> st1 (nested AVM submodules map to their root).
    parts = address.split(".")
    if len(parts) > 1 and parts[0] == "module" and parts[1].split("[")[0] in ids:
        return parts[1].split("[")[0]
    return "project"


def checkov(project: Project, plan: dict[str, Any], workdir: Path) -> list[Finding]:
    checks = curated_checks("checkov")
    args = [
        "checkov",
        "--file",
        "plan.json",
        "--framework",
        "terraform_plan",
        "--output",
        "json",
        "--quiet",
        "--compact",
        "--skip-download",
        "--check",
        ",".join(sorted(checks)),
    ]
    data = _run(args, workdir, ok_codes={0, 1})  # 1 means "a check failed"
    reports = data if isinstance(data, list) else [data]
    # A plan Checkov could not read prints a bare summary and exits 0: that is not "clean".
    scanned = [r for r in reports if isinstance(r, dict) and isinstance(r.get("results"), dict)]
    summary = scanned[0].get("summary", {}) if scanned else {}
    if not scanned or summary.get("parsing_errors") or not summary.get("resource_count"):
        raise ScannerError("checkov did not scan any resource in the plan")
    ids = {r.id for r in project.resources}
    found: list[Finding] = []
    for report in reports:
        for check in (report.get("results") or {}).get("failed_checks") or []:
            check_id = check.get("check_id")
            if check_id not in checks:
                continue
            found.append(
                Finding(
                    id=check_id,
                    resource=_resource_of(str(check.get("resource", "")), ids),
                    severity=checks[check_id],
                    source="checkov",
                    message=str(check.get("check_name", check_id)),
                )
            )
    return found


def trivy(project: Project, plan: dict[str, Any], workdir: Path) -> list[Finding]:
    checks = curated_checks("trivy")
    args = [
        "trivy",
        "config",
        "--format",
        "json",
        "--quiet",
        "--skip-check-update",
        "--disable-telemetry",
        ".",
    ]
    data = _run(args, workdir, ok_codes={0})
    results = data.get("Results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not any(
        isinstance(r, dict) and r.get("Type") == "terraformplan" for r in results
    ):
        raise ScannerError("trivy did not read the plan")
    ids = {r.id for r in project.resources}
    # Trivy names plan resources "<type>.<name>_<md5 of the module address>".
    root = (plan.get("planned_values") or {}).get("root_module") or {}
    by_hash = {
        hashlib.md5(address.encode(), usedforsecurity=False).hexdigest(): _resource_of(address, ids)
        for address in _module_addresses(root)
    }
    found: list[Finding] = []
    for result in results:
        for item in result.get("Misconfigurations") or []:
            check_id = item.get("ID")
            if check_id not in checks or item.get("Status", "FAIL") != "FAIL":
                continue
            name = str((item.get("CauseMetadata") or {}).get("Resource", ""))
            found.append(
                Finding(
                    id=check_id,
                    resource=by_hash.get(name.rpartition("_")[2], "project"),
                    severity=checks[check_id],
                    source="trivy",
                    message=str(item.get("Title", check_id)),
                )
            )
    return found
