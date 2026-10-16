"""app/azure.py (the az wrapper) and app/settings.py, against the fake az."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import azure, settings
from app.main import app
from tests.conftest import az_calls

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_account_comes_from_az_account_show(fake_az: Path) -> None:
    account = azure.account()
    assert account == azure.Account(
        user="sam@example.com",
        subscription_id="00000000-0000-0000-0000-000000000000",
        subscription_name="Sandbox",
        tenant_id="tenant-1",
    )
    # JSON output, no warnings mixed in, and only ever read-only here.
    assert az_calls(fake_az) == [["account", "show", "--output", "json", "--only-show-errors"]]


def test_not_logged_in_is_its_own_error(fake_az: Path) -> None:
    (fake_az / "logged_out").touch()
    with pytest.raises(azure.NotLoggedIn, match="az login"):
        azure.account()


def test_not_found_is_its_own_error(fake_az: Path) -> None:
    with pytest.raises(azure.NotFound):
        azure.az(["group", "show", "--name", "rg-missing"])


def test_az_never_sees_service_principal_credentials(
    fake_az: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The app runs as the signed-in user only (PRD): no client secrets reach az.
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "s3cret")
    monkeypatch.setenv("ARM_CLIENT_SECRET", "s3cret")
    assert "AZURE_CLIENT_SECRET" not in azure.az_env()
    assert "ARM_CLIENT_SECRET" not in azure.az_env()


def test_account_api(fake_az: Path) -> None:
    assert client.get("/api/azure/account").json() == {
        "user": "sam@example.com",
        "subscriptionId": "00000000-0000-0000-0000-000000000000",
        "subscriptionName": "Sandbox",
        "tenantId": "tenant-1",
    }
    (fake_az / "logged_out").touch()
    response = client.get("/api/azure/account")
    assert response.status_code == 401
    assert "az login" in response.json()["detail"]["message"]


def test_settings_round_trip_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOWDEVOPS_WORKSPACE", str(tmp_path))
    assert settings.load() == settings.Settings()
    backend = settings.Backend(
        resource_group="rg-lowdevops-state",
        storage_account="stlowdevops0123456789",
        container="tfstate",
        location="westeurope",
    )
    settings.save(settings.Settings(backends={"sub-1": backend}))
    assert settings.load().backends["sub-1"] == backend
    assert '"storageAccount": "stlowdevops0123456789"' in (tmp_path / "settings.json").read_text()
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]  # no temp files left
