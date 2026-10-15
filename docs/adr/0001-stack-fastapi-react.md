# 0001. Python FastAPI backend + React TypeScript frontend

- **Status:** Accepted (2026-10-15)

## Context

LowDevOps runs Terraform, the Azure CLI and Python-based scanners (Checkov) locally, and needs a rich interactive UI: forms, a diagram canvas and a code editor. It must be easy to contribute to as an open-source project.

## Decision

- Backend: Python + FastAPI, managed with `uv`, checked with `ruff`, `mypy --strict` and `pytest`. Pydantic models define the internal model and generate its JSON Schema.
- Frontend: React + TypeScript + Vite, with React Flow (canvas), Monaco (HCL editor), `eslint`, `vitest` and Playwright with axe-core.
- Everything ships in one dev container with Terraform, `az`, tflint, Checkov, Trivy and Conftest pinned.

## Consequences

- Checkov runs in the same Python environment, and HCL parsing can use `python-hcl2`.
- Pydantic → JSON Schema → TypeScript types gives one model definition across both languages.
- Two toolchains (uv + npm) to maintain. The dev container hides this from users.
