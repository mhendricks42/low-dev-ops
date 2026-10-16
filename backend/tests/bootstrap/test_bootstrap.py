"""EC5: bootstrap issues the expected create commands, and a second run creates nothing."""

import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import bootstrap, settings
from app.main import app
from app.runner.runs import REGISTRY
from tests.conftest import az_calls

client = TestClient(app, base_url="http://127.0.0.1:8000")
SUB = "00000000-0000-0000-0000-000000000000"
ACCOUNT = bootstrap.storage_account_name(SUB)
WRITES = ("create", "update", "delete", "set", "add", "remove")


@pytest.fixture(autouse=True)
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LOWDEVOPS_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setattr(bootstrap, "RETRY_DELAY_SECONDS", 0)
    return tmp_path / "ws"


def writes(state: Path) -> list[list[str]]:
    return [c for c in az_calls(state) if any(w in c[:4] for w in WRITES)]


def test_names_follow_caf_and_storage_limits() -> None:
    assert ACCOUNT.startswith("st") and ACCOUNT.isalnum() and ACCOUNT.islower()
    assert 3 <= len(ACCOUNT) <= 24
    assert bootstrap.storage_account_name(SUB) == ACCOUNT  # stable per subscription
    assert bootstrap.storage_account_name("ffffffff-0000-0000-0000-000000000000") != ACCOUNT


def test_first_run_creates_a_hardened_backend(fake_az: Path) -> None:
    backend = bootstrap.ensure_backend(SUB, "westeurope", say=lambda _: None)
    assert backend == settings.Backend(
        resource_group="rg-lowdevops-state",
        storage_account=ACCOUNT,
        container="tfstate",
        location="westeurope",
    )
    sub = ["--subscription", SUB]
    rg = ["--resource-group", "rg-lowdevops-state"]
    scope = (
        f"/subscriptions/{SUB}/resourceGroups/rg-lowdevops-state"
        f"/providers/Microsoft.Storage/storageAccounts/{ACCOUNT}"
    )
    tail = ["--output", "json", "--only-show-errors"]
    assert writes(fake_az) == [
        [
            "group",
            "create",
            "--name",
            "rg-lowdevops-state",
            "--location",
            "westeurope",
            "--tags",
            "managedBy=lowdevops",
            *sub,
            *tail,
        ],
        [
            "storage",
            "account",
            "create",
            "--name",
            ACCOUNT,
            *rg,
            "--location",
            "westeurope",
            "--kind",
            "StorageV2",
            "--sku",
            "Standard_ZRS",
            "--min-tls-version",
            "TLS1_2",
            "--https-only",
            "true",
            "--allow-blob-public-access",
            "false",
            "--allow-shared-key-access",
            "false",
            "--tags",
            "managedBy=lowdevops",
            *sub,
            *tail,
        ],
        [
            "storage",
            "account",
            "blob-service-properties",
            "update",
            "--account-name",
            ACCOUNT,
            *rg,
            "--enable-versioning",
            "true",
            "--enable-delete-retention",
            "true",
            "--delete-retention-days",
            "30",
            "--enable-container-delete-retention",
            "true",
            "--container-delete-retention-days",
            "30",
            *sub,
            *tail,
        ],
        [
            "role",
            "assignment",
            "create",
            "--assignee-object-id",
            "11111111-2222-3333-4444-555555555555",
            "--assignee-principal-type",
            "User",
            "--role",
            "Storage Blob Data Contributor",
            "--scope",
            scope,
            *sub,
            *tail,
        ],
        [
            "storage",
            "container",
            "create",
            "--name",
            "tfstate",
            "--account-name",
            ACCOUNT,
            "--auth-mode",
            "login",
            *sub,
            *tail,
        ],
    ]
    assert all(
        "--subscription" in c for c in az_calls(fake_az) if c[:2] != ["ad", "signed-in-user"]
    )


def test_second_run_only_reads(fake_az: Path) -> None:
    bootstrap.ensure_backend(SUB, "westeurope", say=lambda _: None)
    (fake_az / "calls.log").unlink()
    bootstrap.ensure_backend(SUB, "westeurope", say=lambda _: None)
    assert writes(fake_az) == []
    assert {tuple(c[:3]) for c in az_calls(fake_az)} >= {
        ("group", "show", "--name"),
        ("storage", "account", "show"),
    }


def test_container_create_retries_while_the_role_propagates(fake_az: Path) -> None:
    (fake_az / "container_403").touch()
    lines: list[str] = []
    bootstrap.ensure_backend(SUB, "westeurope", say=lines.append)
    creates = [c for c in az_calls(fake_az) if c[:3] == ["storage", "container", "create"]]
    assert len(creates) == 2
    assert any("waiting for the role assignment" in line for line in lines)


def test_api_bootstraps_streams_and_records_the_backend(fake_az: Path, workspace: Path) -> None:
    assert client.get(f"/api/backends/{SUB}").status_code == 404
    response = client.post(
        f"/api/backends/{SUB}/bootstrap",
        json={"location": "westeurope", "confirmSubscriptionId": SUB},
    )
    assert response.status_code == 202
    run = REGISTRY.get(response.json()["runId"])
    assert run is not None and run.wait(20) and run.status == "succeeded", (
        run.lines if run else None
    )
    assert client.get(f"/api/backends/{SUB}").json()["storageAccount"] == ACCOUNT
    assert settings.load().backends[SUB].container == "tfstate"


@pytest.mark.parametrize(
    ("sub", "body", "status"),
    [
        (
            SUB,
            {
                "location": "westeurope",
                "confirmSubscriptionId": "ffffffff-0000-0000-0000-000000000000",
            },
            422,
        ),
        ("not-a-guid", {"location": "westeurope", "confirmSubscriptionId": "not-a-guid"}, 422),
        (SUB, {"location": "West Europe; rm -rf", "confirmSubscriptionId": SUB}, 422),
    ],
)
def test_api_refuses_unconfirmed_or_malformed_requests(
    fake_az: Path, sub: str, body: dict[str, str], status: int
) -> None:
    assert client.post(f"/api/backends/{sub}/bootstrap", json=body).status_code == status
    assert writes(fake_az) == []


def test_a_second_bootstrap_while_one_runs_is_409(
    fake_az: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()
    monkeypatch.setattr(bootstrap, "ensure_backend", lambda *a, **k: release.wait(20))
    body = {"location": "westeurope", "confirmSubscriptionId": SUB}
    first = client.post(f"/api/backends/{SUB}/bootstrap", json=body)
    second = client.post(f"/api/backends/{SUB}/bootstrap", json=body)
    release.set()
    # Wait for the run, so its thread never outlives the fake (and never reaches a real az).
    run = REGISTRY.get(first.json()["runId"])
    assert run is not None and run.wait(20)
    assert (first.status_code, second.status_code) == (202, 409)
    assert second.json()["detail"]["runId"] == first.json()["runId"]


def test_a_weakened_existing_account_is_hardened_again(fake_az: Path) -> None:
    bootstrap.ensure_backend(SUB, "westeurope", say=lambda _: None)
    weak = {"allowSharedKeyAccess": True, "allowBlobPublicAccess": True,
            "minimumTlsVersion": "TLS1_0", "enableHttpsTrafficOnly": False}  # fmt: skip
    (fake_az / f"st_{ACCOUNT}").write_text(json.dumps(weak))
    (fake_az / "calls.log").unlink()
    lines: list[str] = []
    bootstrap.ensure_backend(SUB, "westeurope", say=lines.append)
    updates = [c for c in az_calls(fake_az) if c[:3] == ["storage", "account", "update"]]
    assert len(updates) == 1
    for flag in ("--allow-shared-key-access", "--allow-blob-public-access"):
        assert updates[0][updates[0].index(flag) + 1] == "false"
    assert updates[0][updates[0].index("--min-tls-version") + 1] == "TLS1_2"
    assert any("re-applying" in line for line in lines)


def test_a_taken_account_name_is_explained(fake_az: Path) -> None:
    (fake_az / "name_taken").touch()
    with pytest.raises(bootstrap.BootstrapError, match="already taken in another subscription"):
        bootstrap.ensure_backend(SUB, "westeurope", say=lambda _: None)


def test_subscription_ids_are_case_insensitive(fake_az: Path) -> None:
    # One subscription, one backend, whatever the casing it was typed in.
    upper = SUB.replace("0", "0").upper().replace("0000", "ABCD", 1)
    lower = upper.lower()
    body = {"location": "westeurope", "confirmSubscriptionId": upper}
    response = client.post(f"/api/backends/{upper}/bootstrap", json=body)
    run = REGISTRY.get(response.json()["runId"])
    assert run is not None and run.wait(20) and run.status == "succeeded", (
        run.lines if run else None
    )
    assert list(settings.load().backends) == [lower]
    assert settings.load().backends[lower].storage_account == bootstrap.storage_account_name(lower)
    assert client.get(f"/api/backends/{upper}").status_code == 200
