# Run `make help` for the list. `make check` is the gate for every PR.
BE := cd backend &&
FE := cd frontend &&

.PHONY: help install lint typecheck test check e2e dev fmt

help: ## Show targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	$(BE) uv sync --locked
	$(FE) npm ci

lint: ## ruff + eslint + prettier --check
	$(BE) uv run ruff check . && uv run ruff format --check .
	$(FE) npm run lint

typecheck: ## mypy --strict + tsc
	$(BE) uv run mypy .
	$(FE) npm run typecheck

test: ## pytest + vitest
	$(BE) uv run pytest -q
	$(FE) npm test

check: lint typecheck test ## lint, typecheck and unit tests

e2e: ## Playwright (starts API and UI itself)
	$(FE) npm run e2e

dev: ## API on :8000 and UI on :5173, both bound to 127.0.0.1
	trap 'kill 0' EXIT; $(BE) uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload & \
	$(FE) npm run dev

fmt: ## Auto-fix formatting and lint
	$(BE) uv run ruff format . && uv run ruff check --fix .
	$(FE) npm run format
