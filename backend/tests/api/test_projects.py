import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.hcl.generate import generate
from app.main import app
from tests.conftest import load_project

client = TestClient(app)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "ws"
    monkeypatch.setenv("LOWDEVOPS_WORKSPACE", str(root))
    return root


def body(name: str = "rg-vnet") -> dict[str, object]:
    return {"project": load_project(name).model_dump(mode="json", by_alias=True)}


def test_put_then_get_and_list(workspace: Path) -> None:
    assert client.get("/api/projects").json() == {"names": []}
    response = client.put("/api/projects/webapp-dev", json=body())
    assert response.status_code == 200
    assert response.json() == {"issues": []}
    assert client.get("/api/projects/webapp-dev").json() == body()
    assert client.get("/api/projects").json() == {"names": ["webapp-dev"]}
    written = workspace / "webapp-dev"
    assert json.loads((written / "project.json").read_text()) == body()["project"]
    assert (written / "main.tf").read_text() == generate(load_project("rg-vnet"))
    assert sorted(p.name for p in written.iterdir()) == ["main.tf", "project.json"]  # no temp files


def test_put_reports_catalog_issues_without_blocking(workspace: Path) -> None:
    data = body()
    data["project"]["resources"][0]["catalogRef"] = "avm-res-unknown-thing@1.0.0"  # type: ignore[index]
    response = client.put("/api/projects/webapp-dev", json=data)
    assert response.status_code == 200
    assert response.json()["issues"][0]["severity"] == "error"


def test_get_missing_is_404(workspace: Path) -> None:
    assert client.get("/api/projects/nope").status_code == 404


def test_name_must_match_meta_name(workspace: Path) -> None:
    assert client.put("/api/projects/other", json=body()).status_code == 422
    assert not workspace.exists() or not any(workspace.iterdir())


# "." is not listed: HTTP clients normalize "/api/projects/." to the list route before sending.
@pytest.mark.parametrize("name", ["..", "UPPER", "a_b", "-a", "a" * 64, "%2e%2e", "a%2Fb"])
def test_bad_names_never_touch_the_filesystem(workspace: Path, name: str) -> None:
    assert client.get(f"/api/projects/{name}").status_code in (404, 422)
    assert client.put(f"/api/projects/{name}", json=body()).status_code in (404, 405, 422)
    assert not workspace.exists() or not any(workspace.iterdir())


def test_symlink_out_of_the_workspace_is_refused(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace.mkdir()
    (workspace / "webapp-dev").symlink_to(outside)
    assert client.put("/api/projects/webapp-dev", json=body()).status_code == 422
    assert client.get("/api/projects/webapp-dev").status_code == 422
    assert list(outside.iterdir()) == []


def test_list_ignores_dirs_without_project_or_with_bad_names(workspace: Path) -> None:
    (workspace / "empty").mkdir(parents=True)
    (workspace / "Bad_Name").mkdir()
    (workspace / "Bad_Name" / "project.json").write_text("{}")
    assert client.get("/api/projects").json() == {"names": []}
