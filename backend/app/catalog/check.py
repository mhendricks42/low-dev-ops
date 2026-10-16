"""check-catalog: prove every entry's pin exists, its interface matches the module, and its
example passes `terraform validate`. Needs terraform and registry access, so it runs in CI.

Usage: python -m app.catalog.check [catalog-dir]
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import hcl2

from app.catalog.example import example_project, subject_id
from app.catalog.load import CATALOG_DIR, Catalog, CatalogError, load_catalog
from app.catalog.model import CatalogEntry
from app.hcl.generate import generate

INIT_TIMEOUT = 900  # downloads the module and its providers
VALIDATE_TIMEOUT = 300


class CheckError(Exception):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"{step}: {message}")
        self.step = step


@dataclass(frozen=True)
class ModuleInterface:
    variables: dict[str, bool]  # name -> required (has no default)
    outputs: frozenset[str]


def module_interface(module_dir: Path) -> ModuleInterface:
    variables: dict[str, bool] = {}
    outputs: set[str] = set()
    for path in sorted(module_dir.glob("*.tf")):
        doc = hcl2.loads(path.read_text())
        for block in doc.get("variable", []):
            for name, body in block.items():
                variables[name.strip('"')] = "default" not in body
        for block in doc.get("output", []):
            outputs.update(name.strip('"') for name in block)
    return ModuleInterface(variables, frozenset(outputs))


def check_interface(entry: CatalogEntry, interface: ModuleInterface) -> list[str]:
    """Raise on a mismatch with the module; return the module variables the entry leaves out."""
    unknown = sorted(set(entry.inputs) - interface.variables.keys())
    if unknown:
        raise CheckError("interface", f"inputs not in the module: {', '.join(unknown)}")
    missing = sorted(n for n, req in interface.variables.items() if req and n not in entry.inputs)
    if missing:
        raise CheckError("interface", f"required module inputs not listed: {', '.join(missing)}")
    bad_outputs = sorted(set(entry.outputs) - interface.outputs)
    if bad_outputs:
        raise CheckError("interface", f"outputs not in the module: {', '.join(bad_outputs)}")
    return sorted(set(interface.variables) - set(entry.inputs))


def _terraform(terraform: str, workdir: Path, step: str, *args: str, timeout: int) -> None:
    env = {**os.environ, "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1"}
    try:
        result = subprocess.run(  # noqa: S603 - argument list, fixed subcommands, no shell
            [terraform, f"-chdir={workdir}", *args, "-no-color"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise CheckError(step, f"timed out after {timeout}s") from e
    if result.returncode != 0:
        raise CheckError(step, (result.stderr or result.stdout).strip()[-2000:])


def _module_dir(entry: CatalogEntry, workdir: Path) -> Path:
    manifest = workdir / ".terraform" / "modules" / "modules.json"
    try:
        modules = json.loads(manifest.read_text())["Modules"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise CheckError("pin", f"cannot read {manifest.name}: {e}") from e
    key = subject_id(entry)
    record = next((m for m in modules if isinstance(m, dict) and m.get("Key") == key), None)
    if record is None:
        raise CheckError("pin", f"module '{key}' was not installed")
    if record.get("Version") != entry.version:
        raise CheckError(
            "pin", f"registry resolved {record.get('Version')!r}, catalog pins {entry.version!r}"
        )
    module_dir = (workdir / str(record.get("Dir", ""))).resolve()
    if not module_dir.is_relative_to(workdir.resolve()) or not module_dir.is_dir():
        raise CheckError("pin", f"module directory {record.get('Dir')!r} is not under the workdir")
    return module_dir


def check_entry(entry: CatalogEntry, catalog: Catalog, workdir: Path, terraform: str) -> list[str]:
    (workdir / "main.tf").write_text(generate(example_project(entry, catalog)))
    # init resolving the exact `version` is the proof the pin exists in the registry.
    _terraform(
        terraform, workdir, "init", "init", "-backend=false", "-input=false", timeout=INIT_TIMEOUT
    )
    unlisted = check_interface(entry, module_interface(_module_dir(entry, workdir)))
    _terraform(terraform, workdir, "validate", "validate", timeout=VALIDATE_TIMEOUT)
    return unlisted


def main(argv: list[str]) -> int:
    directory = Path(argv[0]) if argv else CATALOG_DIR
    terraform = shutil.which("terraform")
    if terraform is None:
        print("check-catalog: terraform is not on PATH", file=sys.stderr)
        return 1
    try:
        catalog = load_catalog(directory)
    except CatalogError as e:
        print(f"check-catalog: {e}", file=sys.stderr)
        return 1
    for _, entry in sorted(catalog.entries.items()):
        with tempfile.TemporaryDirectory(prefix="check-catalog-") as tmp:
            try:
                unlisted = check_entry(entry, catalog, Path(tmp), terraform)
            except CheckError as e:
                print(f"FAIL {entry.catalog_ref}: {e}", file=sys.stderr)
                return 1
        print(f"ok   {entry.catalog_ref}")
        if unlisted:
            # Unlisted inputs stay hidden at the module's default (M2 spec, Decision).
            print(f"     warning: {len(unlisted)} module inputs not listed: {', '.join(unlisted)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
