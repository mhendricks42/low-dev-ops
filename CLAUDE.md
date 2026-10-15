# LowDevOps

A local web app for designing, validating, planning and applying Azure infrastructure from a GUI, with optional HCL editing. The FastAPI backend lives in `backend/` and the React + TypeScript + Vite frontend in `frontend/`. Everything runs in the dev container.

## Docs (read before changing behavior)

- [docs/PRD.md](docs/PRD.md): product decisions and out of scope
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, sync rules, trust boundaries
- [docs/ROADMAP.md](docs/ROADMAP.md): milestones M0–M6 and their exit criteria
- [docs/adr/](docs/adr/): why the main decisions were made
- `docs/specs/M<n>/`: spec.md, plan.md and tasks.md for each milestone
- [backend/CLAUDE.md](backend/CLAUDE.md), [frontend/CLAUDE.md](frontend/CLAUDE.md): per-package rules

## Commands (run from the repo root)

| What | Command |
| --- | --- |
| Install deps | `make install` |
| Lint (ruff, eslint, prettier) | `make lint` |
| Typecheck (mypy --strict, tsc) | `make typecheck` |
| Unit tests (pytest, vitest) | `make test` |
| **PR gate** (lint + typecheck + test) | `make check` |
| E2E (Playwright; starts API and UI) | `make e2e` |
| Run the app (API :8000, UI :5173) | `make dev` |
| Auto-format | `make fmt` |
| Regenerate project.json schema | `make schema` |

`make check` must exit 0 before you stop. The Stop hook enforces this.

## Hard rules

- `project.json` is the only source of truth. Generated `.tf` is derived: never hand-edit it, and never read it as input.
- The HCL generator is deterministic. Any change to its output updates the snapshot tests in the same PR.
- The API binds to `127.0.0.1` only and has no auth. Never listen on `0.0.0.0`.
- Subprocesses take an argument list, never `shell=True`. Validate project names and ids against a strict pattern before they reach a path or a command.
- Never store credentials. Terraform uses `ARM_USE_CLI=true` with the mounted `~/.azure`.
- Never run `terraform apply`/`destroy` or `az` commands that change resources (settings.json denies them). The human runs sandbox applies.
- Never commit `*.tfstate`, `*.tfplan` or `*.tfvars`.
- Catalog entries pin exact AVM versions ([ADR-0003](docs/adr/0003-avm-first-catalog.md)).
- New logic needs a test that would fail without it. Never skip or weaken a test to go green.
- UI must meet WCAG 2.2 AA: keyboard-only flows work and axe-core reports 0 violations.
- Stay in the milestone's scope. Anything else goes in a follow-up issue.

## Workflow

- Use `/new-milestone M<n>` (`.claude/skills/new-milestone/`): spec → plan → test-first build → `make check` → spec-reviewer → PR.
- Subagents: `spec-reviewer` before every PR, `security-reviewer` for runner, bootstrap, subprocess or CI changes, and `a11y-reviewer` for `frontend/src` changes.

## Git workflow

- Start with `git switch main && git pull`, then branch `feat/|fix/|docs/|chore/|ci/<short-kebab>`. Never commit to main (a hook blocks it).
- Use Conventional Commits (`feat: fix: docs: chore: ci: test: refactor:`) in small, logical commits. Never `--no-verify` or force-push.
- Push the branch, then `gh pr create` with a conventional title, filling in `.github/pull_request_template.md` (summary, milestone, test evidence).
- PRs are squash-merged by the maintainer. Never merge yourself (`gh pr merge` is denied).
