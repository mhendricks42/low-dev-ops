import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.projects as projects_api
from app.api.guard import MAX_BODY_BYTES
from app.main import app
from tests.conftest import load_project

client = TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "ws"
    monkeypatch.setenv("LOWDEVOPS_WORKSPACE", str(root))
    return root


def body() -> dict[str, object]:
    return {"project": load_project("rg-vnet").model_dump(mode="json", by_alias=True)}


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:8000", "127.0.0.1:5173"])
def test_local_hosts_are_served(host: str) -> None:
    assert client.get("/api/health", headers={"host": host}).status_code == 200


def test_rebinding_host_is_refused() -> None:
    # A DNS-rebinding page reaches 127.0.0.1 under its own host name.
    assert client.get("/api/health", headers={"host": "attacker.example:8000"}).status_code == 400


@pytest.mark.parametrize("origin", ["http://attacker.example", "null", "http://127.0.0.1:9999"])
def test_writes_from_foreign_origins_are_refused(workspace: Path, origin: str) -> None:
    response = client.put("/api/projects/webapp-dev", json=body(), headers={"origin": origin})
    assert response.status_code == 403
    assert not workspace.exists()


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "http://localhost:5173", None])
def test_writes_from_the_app_are_allowed(workspace: Path, origin: str | None) -> None:
    headers = {"origin": origin} if origin else {}
    assert client.put("/api/projects/webapp-dev", json=body(), headers=headers).status_code == 200


def test_oversized_body_is_413() -> None:
    big = b'{"hcl": "' + b"#" * 2_100_000 + b'"}'
    response = client.post(
        "/api/hcl/parse", content=big, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


def test_oversized_chunked_body_is_413() -> None:
    def chunks() -> Iterator[bytes]:  # no Content-Length header
        yield b'{"hcl": "'
        for _ in range(30):
            yield b"#" * 100_000
        yield b'"}'

    response = client.post(
        "/api/hcl/parse", content=chunks(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


def test_symlinked_project_dir_inside_the_workspace_is_refused(workspace: Path) -> None:
    (workspace / "other").mkdir(parents=True)
    (workspace / "webapp-dev").symlink_to(workspace / "other")
    assert client.put("/api/projects/webapp-dev", json=body()).status_code == 422
    assert list((workspace / "other").iterdir()) == []


def test_symlinked_project_file_is_not_read(workspace: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret.json"
    secret.write_text("{}")
    (workspace / "webapp-dev").mkdir(parents=True)
    (workspace / "webapp-dev" / "project.json").symlink_to(secret)
    assert client.get("/api/projects/webapp-dev").status_code == 422


def test_corrupt_project_file_is_422_not_500(workspace: Path) -> None:
    (workspace / "webapp-dev").mkdir(parents=True)
    (workspace / "webapp-dev" / "project.json").write_text('{"not": "a project"}')
    assert client.get("/api/projects/webapp-dev").status_code == 422


def test_failed_generate_writes_nothing(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_: object) -> str:
        raise RuntimeError("generator failed")

    monkeypatch.setattr(projects_api, "generate", boom)
    with pytest.raises(RuntimeError):
        client.put("/api/projects/webapp-dev", json=body())
    assert not (workspace / "webapp-dev" / "project.json").exists()


def test_failed_replace_leaves_no_temp_file(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_replace(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(OSError):
        client.put("/api/projects/webapp-dev", json=body())
    assert list((workspace / "webapp-dev").glob("*.tmp")) == []


def test_swap_to_symlink_after_open_stays_in_workspace(workspace: Path, tmp_path: Path) -> None:
    # The race from M3's accepted risk: the directory is checked, then swapped for a symlink
    # before the write. Writes go through the fd opened at check time, so they cannot follow it.
    outside = tmp_path / "outside"
    outside.mkdir()
    with projects_api._open_project_dir("webapp-dev", create=True) as dir_fd:
        (workspace / "webapp-dev").rename(workspace / "moved")
        (workspace / "webapp-dev").symlink_to(outside)
        projects_api._write_atomic(dir_fd, "project.json", "{}\n")
    assert list(outside.iterdir()) == []
    assert (workspace / "moved" / "project.json").read_text() == "{}\n"


def test_symlinked_project_dir_is_not_read(workspace: Path) -> None:
    (workspace / "other").mkdir(parents=True)
    (workspace / "webapp-dev").symlink_to(workspace / "other")
    assert client.get("/api/projects/webapp-dev").status_code == 422


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("fifo", "project.json is not a regular file"),
        ("directory", "project.json is not a regular file"),
        ("oversized", "project.json is too large"),
    ],
)
def test_project_file_that_is_not_a_small_regular_file_is_422(
    workspace: Path, kind: str, message: str
) -> None:
    # A FIFO would block the worker forever and a huge file would exhaust memory.
    path = workspace / "webapp-dev" / "project.json"
    path.parent.mkdir(parents=True)
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    else:  # valid JSON, so only the size cap can refuse it
        path.write_text(json.dumps(body()["project"]) + " " * MAX_BODY_BYTES)
    response = client.get("/api/projects/webapp-dev")
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == message


def test_file_in_place_of_the_project_dir_is_422(workspace: Path) -> None:
    workspace.mkdir()
    (workspace / "webapp-dev").write_text("")
    response = client.put("/api/projects/webapp-dev", json=body())
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "project path is not a directory"


# Non-ASCII digits (e.g. "\u00b9") cannot be sent over HTTP/1.1; isascii() guards them anyway.
@pytest.mark.parametrize("length", ["-1", "+5", "abc"])
def test_malformed_content_length_is_413(length: str) -> None:
    response = client.post(
        "/api/hcl/generate",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": length},
    )
    assert response.status_code == 413
