"""The Azure CLI, as the signed-in user (M5). Never stores or passes credentials.

az reads the mounted ~/.azure; service-principal variables are stripped so az and terraform can
only ever act as the person who ran `az login` (PRD: credentials).
"""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import proc

TIMEOUT_SECONDS = 300
# Credentials and settings the app must never use, even if they are in its environment: it acts
# only as the person who ran `az login` (PRD). TF_VAR_* could smuggle values into a plan.
CREDENTIAL_PREFIXES = (
    "AZURE_CLIENT_", "AZURE_FEDERATED_", "AZURE_USERNAME", "AZURE_PASSWORD", "AZURE_STORAGE_",
    "ARM_CLIENT_", "ARM_OIDC_", "ARM_USE_MSI", "ARM_USE_OIDC", "ARM_MSI_", "ARM_ACCESS_KEY",
    "ARM_SAS_TOKEN", "ARM_USE_AKS_WORKLOAD_IDENTITY", "ARM_USE_CLI", "ACTIONS_ID_TOKEN_REQUEST_",
    "TF_VAR_",
)  # fmt: skip
_workdir: Path | None = None


class AzError(Exception):
    pass


class NotLoggedIn(AzError):
    pass


class NotFound(AzError):
    pass


@dataclass(frozen=True)
class Account:
    user: str
    subscription_id: str
    subscription_name: str
    tenant_id: str


def credential_free_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment for az and terraform: no stored credentials, Azure CLI auth only."""
    return proc.inherited_env(
        drop_prefixes=CREDENTIAL_PREFIXES, extra={"ARM_USE_CLI": "true", **(extra or {})}
    )


def private_workdir() -> Path:
    # A 0700 directory of our own: az is Python, and Python puts its cwd on the import path.
    global _workdir  # one directory per process
    if _workdir is None or not _workdir.is_dir():
        _workdir = Path(tempfile.mkdtemp(prefix="lowdevops-az-"))
    return _workdir


def az(args: list[str]) -> Any:
    """Run `az <args>` and return its JSON output (None when it prints nothing)."""
    try:
        done = proc.run(
            ["az", *args, "--output", "json", "--only-show-errors"],
            cwd=private_workdir(),
            timeout=TIMEOUT_SECONDS,
            env=credential_free_env(),
        )
    except proc.ProcError as e:
        raise AzError(str(e)) from e
    if done.returncode != 0:
        message = (done.stderr or done.stdout).strip().splitlines()[-1:] or [
            f"az failed ({done.returncode})"
        ]
        text = message[0].removeprefix("ERROR: ")[:500]
        if "az login" in text:
            raise NotLoggedIn("Azure CLI is not signed in: run `az login` on the host, then retry.")
        if (
            "could not be found" in text
            or "not found" in text.lower()
            or "ResourceNotFound" in text
        ):
            raise NotFound(text)
        raise AzError(text)
    return json.loads(done.stdout) if done.stdout.strip() else None


def account() -> Account:
    data = az(["account", "show"])
    return Account(
        user=str(data["user"]["name"]),
        subscription_id=str(data["id"]),
        subscription_name=str(data["name"]),
        tenant_id=str(data["tenantId"]),
    )
