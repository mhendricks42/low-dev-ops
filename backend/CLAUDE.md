# Backend (FastAPI)

Python 3.13, managed with `uv`. Run commands from `backend/`, or use the root `make` targets.

## Commands

| What                                   | Command                                                                            |
| -------------------------------------- | ---------------------------------------------------------------------------------- |
| Install                                | `uv sync --locked`                                                                 |
| Lint                                   | `uv run ruff check . && uv run ruff format --check .`                              |
| Format                                 | `uv run ruff format . && uv run ruff check --fix .`                                |
| Typecheck                              | `uv run mypy .` (strict, configured in pyproject.toml)                             |
| Test                                   | `uv run pytest -q`                                                                 |
| One test                               | `uv run pytest -q tests/test_health.py::test_health`                               |
| Run                                    | `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`                |
| Regenerate JSON Schema                 | `make schema` (from the repo root; a test fails if it drifts)                      |
| Check the catalog against the registry | `make catalog` from the repo root (needs terraform and network; CI runs it)        |
| Update HCL snapshots                   | `UPDATE_SNAPSHOTS=1 uv run pytest -q tests/test_generate.py`, then review the diff |

## Rules

- Put routes under `/api` and give every function full type hints. mypy runs `--strict`, and `# type: ignore` needs a reason.
- Pydantic models are the source of the `project.json` JSON Schema ([ADR-0002](../docs/adr/0002-single-internal-model.md)). Change the model, not the schema.
- Add dependencies with `uv add` (or `uv add --dev`) and commit `uv.lock`.
- Call `subprocess` only with an argument list, never `shell=True`, and use explicit timeouts. Tests fake `terraform` and `az` with stub binaries on `PATH`. They never call Azure.
- `app/model.py` is the model; `app/hcl/` generates and parses HCL ([M1 spec](../docs/specs/M1/spec.md)); `app/catalog/` loads and checks `catalog/*.yaml` ([M2 spec](../docs/specs/M2/spec.md)). Never hand-edit `schema/project.schema.json`, `catalog/catalog.schema.json` or fixture `main.tf` snapshots.
- `app/api/` holds the routes ([M3 spec](../docs/specs/M3/spec.md)). Projects live in `$LOWDEVOPS_WORKSPACE` (default `~/lowdevops`); a name must match the pattern and resolve inside the workspace before any file access.
- `app/guardrails/` checks naming, tags and policies, and runs Conftest/Checkov/Trivy as subprocesses ([M4 spec](../docs/specs/M4/spec.md)). Tests use the replaying stubs in `tests/bin/` (fixture `stub_scanners`); `tests/guardrails/test_real_scanners.py` runs the real tools where installed and must pass in the dev container. Policies live in `../policies/`.
- Start subprocesses only through `app/proc.py` (absolute binary, own process group, explicit env, timeout). `app/azure.py` wraps `az`; `app/bootstrap/` creates the state backend (read first, create only what is missing); `app/runner/runs.py` holds runs and their logs ([M5 spec](../docs/specs/M5/spec.md)). Tests use the fake `az` in `tests/bin/` (fixture `fake_az`, calls logged to `calls.log`); never call real Azure.
- Layout: `app/{api,catalog,hcl,runner,guardrails,bootstrap}`, as in [ARCHITECTURE.md](../docs/ARCHITECTURE.md). Tests mirror it under `tests/`.
