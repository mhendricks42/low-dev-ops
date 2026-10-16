"""Conftest, Checkov and Trivy as subprocesses (M4).

Each tool runs on an argument list (never a shell) with a timeout, in a fresh temp dir that holds
only what it scans. Anything other than parseable output becomes a blocking LDO_SCANNER_FAILED
finding, so a broken scanner can never make a project look clean.
"""

import hashlib
import json
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


def _run(args: list[str], cwd: Path, ok_codes: set[int]) -> Any:
    try:
        done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            args, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=False
        )
    except FileNotFoundError as e:
        raise ScannerError(f"{args[0]} is not installed") from e
    except subprocess.TimeoutExpired as e:
        raise ScannerError(f"{args[0]} took longer than {TIMEOUT_SECONDS} s") from e
    if done.returncode not in ok_codes:
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
        raise ScannerError(f"{args[0]} exited with {done.returncode}: {tail[0][:200]}")
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError as e:
        raise ScannerError(f"{args[0]} printed output that is not JSON") from e


def failed(tool: str, error: ScannerError) -> Finding:
    return Finding(
        id="LDO_SCANNER_FAILED",
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
    ids = {r.id for r in project.resources}
    found: list[Finding] = []
    for result in data if isinstance(data, list) else []:
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


def checkov(project: Project, workdir: Path) -> list[Finding]:
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
    ids = {r.id for r in project.resources}
    # Trivy names plan resources "<type>.<name>_<md5 of the module address>".
    root = (plan.get("planned_values") or {}).get("root_module") or {}
    by_hash = {
        hashlib.md5(address.encode(), usedforsecurity=False).hexdigest(): _resource_of(address, ids)
        for address in _module_addresses(root)
    }
    found: list[Finding] = []
    for result in (data.get("Results") if isinstance(data, dict) else None) or []:
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
