"""check-catalog against a stub `terraform` on PATH: no network, no registry."""

import json
import os
import sys
from pathlib import Path

import pytest

from app.catalog.check import CheckError, check_entry, main, module_interface
from app.catalog.load import load_catalog
from tests.conftest import FIXTURES

MINIMAL = FIXTURES / "catalog-minimal"
VNET = "avm-res-network-virtualnetwork"

VARIABLES = """
variable "location" { type = string }
variable "parent_id" { type = string }
variable "name" {
  type    = string
  default = null
}
variable "address_space" {
  type    = set(string)
  default = null
}
variable "enable_telemetry" {
  type    = bool
  default = true
}
variable "dns_servers" {
  type    = any
  default = null
}
"""
RG_VARIABLES = """
variable "location" { type = string }
variable "name" { type = string }
variable "tags" {
  type    = map(string)
  default = null
}
variable "enable_telemetry" {
  type    = bool
  default = true
}
"""
OUTPUTS = """
output "name" { value = "x" }
output "resource_id" { value = "y" }
"""

# Installs each module in main.tf from TF_STUB_MODULES/<key>, at TF_STUB_VERSION or its pin.
STUB = f"""#!{sys.executable}
import json, os, re, shutil, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["TF_STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if "ARM_CLIENT_SECRET" in os.environ or "TF_VAR_secret" in os.environ:
    sys.exit("stub saw a secret")
workdir = Path(args[0].removeprefix("-chdir="))
command = args[1]
if os.environ.get("TF_STUB_FAIL") == command:
    print(f"Error: stub {{command}} failed", file=sys.stderr)
    sys.exit(1)
if command == "init":
    text = (workdir / "main.tf").read_text()
    records = []
    for key, version in re.findall(r'module "(\\w+)" {{\\n.*\\n  version = "([^"]+)"', text):
        target = workdir / ".terraform" / "modules" / key
        shutil.copytree(Path(os.environ["TF_STUB_MODULES"]) / key, target)
        records.append({{"Key": key, "Version": os.environ.get("TF_STUB_VERSION", version),
                        "Dir": os.environ.get("TF_STUB_DIR", f".terraform/modules/{{key}}")}})
    (workdir / ".terraform" / "modules" / "modules.json").write_text(
        json.dumps({{"Modules": records}}))
"""


@pytest.fixture
def stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    terraform = bin_dir / "terraform"
    terraform.write_text(STUB)
    terraform.chmod(0o755)
    for key, variables in [("vnet1", VARIABLES), ("rg1", RG_VARIABLES)]:
        module = tmp_path / "modules" / key
        module.mkdir(parents=True)
        (module / "variables.tf").write_text(variables)
        (module / "outputs.tf").write_text(OUTPUTS)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("TF_STUB_MODULES", str(tmp_path / "modules"))
    monkeypatch.setenv("TF_STUB_LOG", str(tmp_path / "calls.log"))
    return tmp_path


def _calls(stub: Path) -> list[list[str]]:
    return [json.loads(line) for line in (stub / "calls.log").read_text().splitlines()]


def _check(stub: Path) -> list[str]:
    catalog = load_catalog(MINIMAL)
    workdir = stub / "work"
    workdir.mkdir()
    return check_entry(catalog.entries[VNET], catalog, workdir, str(stub / "bin" / "terraform"))


def test_module_interface_reads_variables_and_outputs(stub: Path) -> None:
    interface = module_interface(stub / "modules" / "vnet1")
    assert interface.variables["location"] is True
    assert interface.variables["name"] is False
    assert interface.outputs == {"name", "resource_id"}


def test_passing_entry_runs_init_then_validate(stub: Path) -> None:
    assert _check(stub) == ["dns_servers"]  # unlisted, so only a warning
    workdir = str(stub / "work")
    assert _calls(stub) == [
        [f"-chdir={workdir}", "init", "-backend=false", "-input=false", "-no-color"],
        [f"-chdir={workdir}", "validate", "-no-color"],
    ]
    assert 'module "vnet1"' in (stub / "work" / "main.tf").read_text()


def test_secrets_are_not_passed_to_terraform(stub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARM_CLIENT_SECRET", "not-for-providers")
    monkeypatch.setenv("TF_VAR_secret", "not-for-providers")
    assert _check(stub) == ["dns_servers"]


def test_init_failure_names_the_step(stub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_STUB_FAIL", "init")
    with pytest.raises(CheckError, match="init: Error: stub init failed"):
        _check(stub)


def test_validate_failure_names_the_step(stub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_STUB_FAIL", "validate")
    with pytest.raises(CheckError, match="validate: Error: stub validate failed"):
        _check(stub)


def test_resolved_version_must_equal_pin(stub: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_STUB_VERSION", "0.22.4")
    with pytest.raises(CheckError, match=r"registry resolved '0\.22\.4', catalog pins '0\.22\.3'"):
        _check(stub)


def test_module_dir_outside_workdir_is_rejected(
    stub: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TF_STUB_DIR", "../modules/vnet1")
    with pytest.raises(CheckError, match="is not under the workdir"):
        _check(stub)


def test_input_missing_from_module_fails(stub: Path) -> None:
    (stub / "modules" / "vnet1" / "variables.tf").write_text(
        VARIABLES.replace("address_space", "spaces")
    )
    with pytest.raises(CheckError, match="inputs not in the module: address_space"):
        _check(stub)


def test_required_input_not_listed_fails(stub: Path) -> None:
    (stub / "modules" / "vnet1" / "variables.tf").write_text(
        VARIABLES + 'variable "sku" { type = string }'
    )
    with pytest.raises(CheckError, match="required module inputs not listed: sku"):
        _check(stub)


def test_output_missing_from_module_fails(stub: Path) -> None:
    (stub / "modules" / "vnet1" / "outputs.tf").write_text('output "name" { value = "x" }')
    with pytest.raises(CheckError, match="outputs not in the module: resource_id"):
        _check(stub)


def test_main_reports_each_entry(stub: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(MINIMAL)]) == 0
    out = capsys.readouterr().out
    assert "ok   avm-res-network-virtualnetwork@0.22.3" in out
    assert "ok   avm-res-resources-resourcegroup@0.4.0" in out
    assert "warning: 1 module inputs not listed: dns_servers" in out


def test_main_fails_on_first_bad_entry(
    stub: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TF_STUB_FAIL", "validate")
    assert main([str(MINIMAL)]) == 1
    assert "FAIL avm-res-network-virtualnetwork@0.22.3: validate:" in capsys.readouterr().err


def test_main_without_terraform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert main([str(MINIMAL)]) == 1


def test_main_rejects_an_invalid_catalog(stub: Path) -> None:
    assert main([str(FIXTURES / "catalog-invalid" / "ref-unknown-entry")]) == 1
