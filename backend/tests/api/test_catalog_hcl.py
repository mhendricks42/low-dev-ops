from fastapi.testclient import TestClient

from app.hcl.generate import generate
from app.main import app
from tests.conftest import FIXTURES, load_project

client = TestClient(app, base_url="http://127.0.0.1:8000")


def project_json(name: str) -> dict[str, object]:
    return load_project(name).model_dump(mode="json", by_alias=True)


def test_catalog_lists_every_entry_by_alias() -> None:
    entries = client.get("/api/catalog").json()["entries"]
    modules = [e["module"] for e in entries]
    assert modules == sorted(modules)
    assert "avm-res-resources-resourcegroup" in modules
    vnet = next(e for e in entries if e["module"] == "avm-res-network-virtualnetwork")
    assert vnet["cafAbbreviation"] == "vnet"
    assert vnet["refs"][0]["from"] == "avm-res-resources-resourcegroup"
    # Only what the YAML sets: an input without a default must not arrive as default: null.
    assert "default" not in vnet["inputs"]["parent_id"]
    assert vnet["inputs"]["enable_telemetry"]["default"] is False


def test_generate_matches_the_generator() -> None:
    response = client.post("/api/hcl/generate", json={"project": project_json("rg-vnet")})
    assert response.status_code == 200
    assert response.json() == {"hcl": generate(load_project("rg-vnet"))}


def test_parse_round_trips() -> None:
    text = (FIXTURES / "valid" / "rg-vnet" / "main.tf").read_text()
    body = {"hcl": text, "previous": project_json("rg-vnet")}
    response = client.post("/api/hcl/parse", json=body)
    assert response.status_code == 200
    assert response.json() == {"project": project_json("rg-vnet")}


def test_parse_error_is_422_with_line_and_message() -> None:
    body = {"hcl": 'module "a" {\n  x = \n}\n', "previous": project_json("rg")}
    response = client.post("/api/hcl/parse", json=body)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["line"] == 2
    assert detail["message"]


def test_invalid_project_body_is_422() -> None:
    assert client.post("/api/hcl/generate", json={"project": {"bad": 1}}).status_code == 422


def test_parse_rejects_oversized_hcl() -> None:
    body = {"hcl": "#" * 1_000_001, "previous": project_json("rg")}
    assert client.post("/api/hcl/parse", json=body).status_code == 422
