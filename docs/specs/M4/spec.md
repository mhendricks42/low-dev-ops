# M4 — Guardrails: spec

## Context

ROADMAP §M4 covers CAF naming and tag rules, Conftest policies, Checkov/Trivy on HCL and plan JSON, severity tiers, and waivers stored in `project.json`. The PRD rows it implements:

- **Guardrails:** CAF naming and tagging, policy checks before apply, SecOps scanning.
- **Standards:** CAF naming and tag defaults, fully configurable.
- **Guardrail failures:** high and critical findings block apply. A medium or low finding can be waived with a written reason that is stored in `project.json` and shown in the plan output.

M4 builds on M1 (generator), M2 (catalog, `fill: name`, `cafAbbreviation`) and M3 (API, store, UI). `Project.waivers` and the `Waiver` model already exist from M1.

Decided with the user (2026-10-16):

- **UI:** M4 includes a **Checks** tab that lists findings and lets you add and remove waivers.
- **Scan target:** M4 scans the project model and the generated HCL, and accepts an optional plan JSON. Tests feed it recorded plan fixtures, and M5 passes in its real `terraform show -json`. Checkov and Trivy see little inside AVM module calls that haven't been initialised, so most scanner findings will come from the plan JSON once M5 lands.

## Findings and severity

```python
Severity = Literal["critical", "high", "medium", "low"]

@dataclass(frozen=True, order=True)
class Finding:
    id: str           # e.g. LDO_NAME_LENGTH, CKV_AZURE_35, AVD-AZU-0012
    resource: str     # resource id (module.<id> mapped back), or "project"
    severity: Severity
    source: Literal["naming", "tags", "conftest", "checkov", "trivy", "guardrails"]
    message: str
```

- `waivable` is `severity in {"medium", "low"}`.
- **Waiver match:** a waiver matches a finding when `finding_id` and `resource` are equal.
- **Waiver on a high or critical finding:** it has no effect and is returned under `ignored_waivers` with the reason.
- **Unmatched waiver:** a waiver that matches no finding is returned under `unused_waivers`. Nothing is deleted automatically.
- **Apply rule:** `apply_allowed` is true exactly when no high or critical finding remains. Waivers can only cover medium and low, so they never change this. An unwaived medium or low finding does not block; it is shown.
- **Fail closed:** a scanner that is missing, times out or returns output that can't be parsed produces a `high` finding `LDO_SCANNER_FAILED` with source `guardrails`, so apply is blocked rather than silently clean.

## Checks (`backend/app/guardrails/`)

| Module | Checks | Severity |
| --- | --- | --- |
| `naming.py` | **High** if a `fill: name` input breaks its type's limits: `LDO_NAME_LENGTH`, `LDO_NAME_CHARS`. **Low** if it doesn't match the name the project pattern gives: `LDO_NAME_PATTERN` | high / low |
| `tags.py` | Every resource whose entry has a `tags` input must end up with each key in `project.required_tags` (project tags merged with the resource's own): `LDO_TAG_MISSING` | medium |
| `conftest.py` | Runs `conftest test --output json -p policies/conftest -` on the project JSON enriched with each resource's catalog module. `deny` rules are high and `warn` rules are medium. Each rule's id comes from its message prefix, e.g. `LDO_ST_TLS: …` | high / medium |
| `checkov.py` | `checkov -d <tmp> --framework terraform -o json --quiet`, plus `-f plan.json --framework terraform_plan` when a plan is given. Severity comes from `policies/severity.yaml` (check id → severity); unmapped checks default to medium | from map |
| `trivy.py` | `trivy config --format json <tmp>`, which also reads `plan.json` when it is in the temp dir. Trivy's own severity is used, `UNKNOWN` maps to medium | from Trivy |
| `run.py` | `check(project, catalog, plan_json=None) -> Report` runs everything and applies waivers | — |

- **Subprocess rules:** scanners run on argument lists (never `shell=True`) with a 120 s timeout each. They run in a fresh temp dir that holds only the generated `main.tf` and, if given, `plan.json`. The temp dir is deleted afterwards and nothing touches the workspace. A module address `module.<id>` in scanner output is mapped back to the resource id.
- **Starter policies** in `policies/conftest/*.rego`, each with Conftest unit tests (`conftest verify`):
  - storage `min_tls_version` must be `TLS1_2` (deny)
  - storage public network access must not be `Enabled` (warn)
  - Key Vault purge protection must be on (deny)
  - an NSG rule must not allow `*` inbound on 22 or 3389 (deny)

## CAF naming (`backend/app/guardrails/naming.py`, mirrored in `frontend/src/model/naming.ts`)

**Name rules in the catalog.** Each catalog entry gains `nameRules: { min, max, chars, lowercase, hyphens }`:

- `chars` is a regex character class, for example `a-z0-9-`.
- `hyphens: false` means separators are removed from the name (storage accounts).
- `catalog.schema.json` is regenerated and the M2 drift test is updated.

The values come from Microsoft's "Naming rules and restrictions for Azure resources" page. They are pinned in the YAML, and `make catalog` does not refetch them.

**`caf_name(entry, project, kind=None)`:**

1. Fill the project pattern (`{type}`, `{workload}`, `{env}`, `{region}`). `{type}` is the CAF abbreviation, and `func` replaces `app` when `kind == "functionapp"`, as the M2 spec deferred.
2. Lowercase the name if the type requires it, then drop every character not in `chars`. When `hyphens` is false, separators are dropped too.
3. If the name is longer than `max`, trim it, taking characters from `{workload}` first, then strip any leading or trailing separator.
4. If the result is still shorter than `min`, it is an error. The UI shows it as the high finding `LDO_NAME_LENGTH`.

**One algorithm, two languages.** `frontend/src/model/catalog.ts` `suggestedName` calls `cafName` with the same algorithm. Both test suites read the shared vectors in `backend/tests/fixtures/naming-cases.json`, one per catalog entry plus long-workload and odd-character cases, so the two implementations cannot drift apart.

## Tags

- **Required tags:** `Project` gains `required_tags: list[str] = ["env", "owner"]` (`requiredTags` in JSON). This is the CAF minimum, and you can change it per project. `schemaVersion` stays 1, because the default keeps old files valid.
- **Generator:** a resource whose entry has a `tags` input gets project `tags` merged under its own (the resource's keys win) and emitted as the module's `tags`. This changes generated HCL, so the M1 snapshots are updated in the same PR (CLAUDE.md rule). The parser maps the merged value back, so round-trips stay equal: it drops keys equal to the project value.

## API

`POST /api/guardrails/check`, body `{ "project": Project, "plan": <plan JSON object> | null }` (the 2 MB body cap applies). Response:

```jsonc
{
  "findings": [ { "id", "resource", "severity", "source", "message", "waivable" } ],  // unwaived, sorted by severity then resource
  "waived":   [ { "finding": {…}, "waiver": {…} } ],
  "ignored_waivers": [ { "waiver": {…}, "reason": "high findings cannot be waived" } ],
  "unused_waivers":  [ {…} ],
  "apply_allowed": true
}
```

`PUT /api/projects/{name}` is unchanged: its catalog `issues` stay as they are, and guardrails run only on request, because the scanners take seconds.

## Frontend: Checks tab (`frontend/src/checks/`)

- **The tab.** A fourth tab, **Checks**. **Run checks** calls the API with the current model. While it runs the button is disabled and the result region is `aria-busy`.
- **Status line** (`role="status"`): "Apply allowed" or "Apply blocked: N high or critical findings".
- **Findings table** (caption, `scope` headers): grouped by severity, with columns for id, resource, source and message. Each waivable row has a **Waive** button.
- **Waive dialog.** It reuses the M3 `<dialog>` component and asks for **Reason** (required, at least 10 characters) and **Your name** (required); `at` is set to the current ISO time. It dispatches `addWaiver`, so the waiver is saved like any other model change, then re-runs the checks and returns focus to the row.
- **Waived list.** Each entry shows its reason, author and date, plus a **Remove waiver** button (dispatches `removeWaiver`, then re-runs). Ignored and unused waivers are listed with their reasons.
- **Stale results.** When the model has changed since the last run, the panel says "Results are out of date. Run checks again." Apply itself arrives in M5.

## Files touched

- **Backend:**
  - `backend/app/guardrails/{__init__,findings,naming,tags,conftest,checkov,trivy,run}.py`
  - `backend/app/api/guardrails.py`
  - `backend/app/main.py`
  - `backend/app/model.py` (`required_tags`)
  - `backend/app/catalog/model.py` (`NameRules`)
  - `backend/app/hcl/{generate,parse}.py` (tag merge)
  - `catalog/*.yaml` (`nameRules`, plus the `func` rule for web-site)
  - the schemas
- **Policies:** `policies/conftest/*.rego` with `*_test.rego`, `policies/severity.yaml`, `policies/README.md`
- **Backend tests:**
  - `backend/tests/guardrails/` and `backend/tests/api/test_guardrails.py`
  - fixtures under `backend/tests/fixtures/guardrails/{high,waived-medium,clean}/` (`project.json`, `plan.json`)
  - `backend/tests/fixtures/naming-cases.json`
  - updated `main.tf` snapshots
  - stub `checkov`, `trivy` and `conftest` binaries under `backend/tests/bin/`
- **Frontend:**
  - `frontend/src/checks/*`
  - `frontend/src/model/{naming,catalog,reducer}.ts` (`addWaiver`, `removeWaiver`)
  - `frontend/src/App.tsx`
  - the regenerated model types
- **Frontend tests:** `frontend/e2e/m4.spec.ts`
- **Other:** `Makefile` (`policy-test` target in `check`), `docs/ARCHITECTURE.md` if the flow changes, and `.claude/skills/caf-naming/SKILL.md` (the PRD lists it; it records the naming rules)

## Exit criteria → proof

| Criterion | Proof |
| --- | --- |
| A fixture with a high finding gives `apply_allowed: false` | `test_guardrails.py::test_high_finding_blocks_apply`, using fixture `high` (storage account with TLS 1.0, a Conftest `deny`). It also checks that a waiver on that finding lands in `ignored_waivers` |
| A fixture with a waived medium finding gives `apply_allowed: true` and lists the waiver | `test_waived_medium_allows_apply`, using fixture `waived-medium` (a missing `owner` tag with a waiver) |
| A clean fixture gives zero findings | `test_clean_fixture_has_no_findings`, using fixture `clean` (project and plan) |
| Generated names match the CAF pattern and each type's length and character limits | `tests/guardrails/test_naming.py` checks every catalog entry against `naming-cases.json`, plus property-style cases (long workload, uppercase, symbols); `frontend/src/model/naming.test.ts` runs the same vectors |
| UI: keyboard-only waive flow, and axe-core reports 0 violations | `e2e/m4.spec.ts`: run checks, waive a medium finding by keyboard, check that the status line and the waived list update, and run axe on the empty, findings, dialog and waived states |

**Unit tests and stub scanners.** API and unit tests run against the stub scanners on `PATH`. Each stub replays recorded JSON chosen by a fixture marker, so `make check` needs no network and no real scanners.

**Real-scanner tests.** `tests/guardrails/test_real_scanners.py` runs the real Checkov, Trivy and Conftest on the three fixtures. It runs whenever the binaries are on `PATH`, which is the case in the dev container, so the dev-container CI job runs them. Where a binary is missing it is skipped with an explicit reason. `LOWDEVOPS_REQUIRE_SCANNERS=1`, set in the dev container image, turns that skip into a failure there.

## Out of scope

- A custom policy authoring UI (per the ROADMAP).
- Running `terraform plan` or `terraform init`, and the plan and apply buttons (M5).
- Showing waivers in plan output (M5, which will reuse `waived`).
- Globally unique name suffixes for storage accounts and Key Vaults.
- Organisation-wide policy bundles.

## Risks

- **Hand-written plan fixtures may not match real `terraform show -json` output.** The real-scanner tests check them with real Checkov and Trivy in the dev container, and M5 replaces them with recorded plans.
- **The scanners are slow** (Checkov takes 5–15 s), so checks run on request, never on every keystroke.
- **Free Checkov reports no severity**, so `policies/severity.yaml` must map the checks that matter. Unmapped checks default to medium, which keeps them visible without blocking.
- **The tag merge changes generated HCL.** The snapshot and round-trip tests are updated in the same PR, and the parser change keeps round-trips exact.
- **Scanner version drift between the dev container and CI.** Versions are already pinned in `.devcontainer/Dockerfile` (Checkov 3.3.29, Trivy 0.76.0, Conftest 0.71.1).

## Verification

- `make check` passes, including the stub-scanner API tests, `conftest verify` and the naming vectors on both sides.
- The dev-container CI job runs the real-scanner tests on the three fixtures.
- `make e2e` passes the M3 suite plus `m4.spec.ts` three runs in a row.
- spec-reviewer, security-reviewer (subprocesses and temp dirs) and a11y-reviewer (`frontend/src`) all return PASS.
