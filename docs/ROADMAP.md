# LowDevOps MVP roadmap

There are seven milestones, each one PR. Each exit criterion is a command or test that passes or fails, and a milestone is done when all of its criteria pass in CI (M5's sandbox gate is run by a human). Specs for each milestone go in `docs/specs/M<n>/`.

**Cut order if time slips:** drop AKS and Functions from the catalog first, then move landing-zone patterns (M6) to v0.2. Guardrails are never cut.

## M0 — Foundations (week 1)

- **Scope:** monorepo layout, dev container, CLAUDE.md files, `.claude/` settings/agents/skills, CI, LICENSE (MIT), CONTRIBUTING, SECURITY, templates.
- **Out of scope:** any product feature.
- **Exit criteria:**
  - `make check` (lint, typecheck, unit tests) exits 0 locally and inside the dev container.
  - CI runs `make check` on every PR and is required before merging to `main`.
  - Playwright test: `GET /api/health` returns 200 and the UI hello page renders (screenshot attached to the PR).

## M1 — Internal model + HCL engine (week 1–2)

- **Scope:** Pydantic model and generated JSON Schema, the deterministic generator, and the parser with opaque `customHcl`. Fixtures use RG, VNet and NSG.
- **Out of scope:** UI, catalog breadth, running terraform plan.
- **Exit criteria:**
  - Schema test: every fixture `project.json` validates, and invalid fixtures are rejected.
  - Snapshot tests: generator output for each fixture matches the committed `.tf`, byte for byte.
  - Round-trip test: `parse(generate(m)) == m` for every fixture.
  - Custom HCL test: unmappable blocks survive parse → generate unchanged.
  - `terraform validate` passes on every fixture's generated output (CI job).

## M2 — Catalog (week 2)

- **Scope:** catalog YAML format, plus entries for the foundation set (RG, VNet, NSG, Key Vault, Storage) and compute (App Service, Container Apps, Functions, AKS).
- **Out of scope:** landing-zone patterns (M6).
- **Exit criteria:**
  - `scripts/check-catalog` exits 0: every YAML file passes the catalog schema, every AVM pin exists in the registry, and every entry's example passes `terraform validate`.
  - A unit test covers each entry's basic inputs (they have CAF defaults) and its allowed refs (they point at real outputs).

## M3 — GUI views: wizard, canvas, HCL editor (week 2–3)

- **Scope:** design-system tokens and components, a schema-driven wizard, a React Flow canvas with a keyboard list view, and a Monaco editor, all bound to one model store.
- **Out of scope:** plan/apply buttons (M5).
- **Exit criteria (Playwright):**
  - Adding RG + VNet in the wizard → both appear on the canvas (VNet nested in RG) and in the HCL.
  - Changing a value in HCL and saving → the wizard shows the new value.
  - Saving invalid HCL → an inline error appears and the model is unchanged.
  - Keyboard-only test: create a resource and add a reference with no mouse events.
  - axe-core reports 0 WCAG 2.2 AA violations on every page.

## M4 — Guardrails (week 3)

- **Scope:** CAF naming and tag rules, Conftest policies, Checkov/Trivy on HCL and plan JSON, severity tiers, waivers stored in `project.json`.
- **Out of scope:** custom policy authoring UI.
- **Exit criteria:**
  - Fixture with a high finding → the API reports `apply_allowed: false`.
  - Fixture with a waived medium finding → `apply_allowed: true`, and the waiver is listed in the response.
  - Clean fixture → zero findings.
  - Naming tests: generated names match the CAF pattern and each resource type's length/character limits.

## M5 — Runner + state bootstrap (week 3)

- **Scope:** init/plan/apply as subprocesses, streamed logs, one run per project, apply only the saved plan, typed confirmations, the shared state-backend bootstrap, and the subscription-confirm step.
- **Out of scope:** destroy-all, import, scheduled runs.
- **Exit criteria:**
  - Backend tests against a fake `terraform` binary on `PATH`: apply only accepts an existing `plan.tfplan`, a second concurrent run gets 409, and the log stream ends with the exit code.
  - Playwright: apply stays disabled until the project name is typed, and a plan with destroys needs a second confirmation.
  - Bootstrap test with a fake `az`: it issues the expected create commands (versioning, soft delete, no public access) and is idempotent on a second run.
  - **Human gate:** `scripts/e2e-sandbox.sh` exits 0 against the sandbox subscription (bootstrap → plan → apply → destroy).

## M6 — Landing-zone patterns, docs, v0.1.0 (week 4)

- **Scope:** AVM pattern entries (hub-spoke), `examples/` (hub-spoke, web app), `docs/user-guide/`, first-run onboarding, README.
- **Out of scope:** everything in the PRD's Out of scope section.
- **Exit criteria:**
  - `scripts/check-catalog` passes with the pattern entries included.
  - Each `examples/*/project.json` generates HCL that passes `terraform validate`.
  - Playwright onboarding test: from a fresh workspace, a user reaches a valid plan-ready project through the wizard alone.
  - A link check over `docs/` and `README.md` passes, and the `v0.1.0` tag is created.
