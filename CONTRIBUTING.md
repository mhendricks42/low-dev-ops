# Contributing to LowDevOps

Thanks for helping. This page covers how to get a working setup and how changes get merged.

## Setup

1. Open the repo in VS Code, then run **Dev Containers: Reopen in Container**. The container ships pinned versions of Python, Node, Terraform, Azure CLI, tflint, Checkov, Trivy and Conftest, and runs `make install` for you.
2. Run `az login` on your host. The container mounts `~/.azure`, and LowDevOps never stores credentials.
3. Run `make dev`, then open http://127.0.0.1:5173.

To work without the container, install uv and Node 22, then run `make install`.

## Before you open a PR

| Command | What it does |
| --- | --- |
| `make check` | Lint, typecheck and unit tests. CI requires it to pass. |
| `make e2e` | Playwright end-to-end tests. Run it for UI changes. |
| `make fmt` | Auto-format Python and TypeScript. |

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before changing behavior. Milestone work follows [docs/ROADMAP.md](docs/ROADMAP.md), with a spec in `docs/specs/M<n>/`.

## Git workflow

- Branch from an up-to-date `main`. Name the branch `feat/`, `fix/`, `docs/`, `chore/` or `ci/` plus a short kebab-case description, e.g. `fix/vnet-cidr-validation`.
- Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `test:`, `refactor:`. Keep commits small and logical.
- Don't skip hooks (`--no-verify`) or force-push a shared branch.
- Open a PR against `main` with a Conventional Commit title (a CI check enforces this) and fill in the template.
- A maintainer squash-merges, so the PR title becomes the commit on `main`.

## Code rules

- Every behavior change comes with a test.
- Never commit `*.tfstate`, `*.tfplan`, `*.tfvars` or any credential.
- UI must meet WCAG 2.2 AA.
- Backend and frontend specifics: [backend/CLAUDE.md](backend/CLAUDE.md), [frontend/CLAUDE.md](frontend/CLAUDE.md).

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
