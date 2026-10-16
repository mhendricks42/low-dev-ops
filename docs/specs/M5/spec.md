# M5 — Runner + state bootstrap: spec

## Context

ROADMAP §M5 covers:

- `init`, `plan` and `apply` as subprocesses, with streamed logs
- one run per project, and apply only of the saved plan
- typed confirmations
- the shared state-backend bootstrap
- the subscription-confirm step

PRD rows it implements:

- **Lifecycle:** full plan and apply in the app, plus the bootstrap flow.
- **State bootstrap:** one shared backend per subscription. That is a resource group plus a storage account with blob versioning, soft delete, no public blob access and Entra-only auth. It is created with `az` as the signed-in user and recorded in local app settings, and each project gets its own state key.
- **Credentials:** `ARM_USE_CLI=true` with the mounted `~/.azure`. The UI shows the signed-in account and subscription, and the user confirms the subscription before each plan. The app never stores secrets.
- **Apply:** applies only the saved, reviewed `plan.tfplan`, and requires the project name to be typed. Destroys and replacements are highlighted and need a second confirmation. One run per project at a time.
- **Guardrail failures:** shown in the plan output.

M4 left M5 one hard rule: run the guardrails on the plan the backend produces itself (`terraform show -json`), never on a plan from a request, and gate apply on `apply_allowed`.

**Never in this repo's automation:** Claude does not run `terraform apply` or `destroy`, or any `az` command that changes resources (settings.json denies them). All tests use fake `terraform` and `az` binaries. The human runs the sandbox gate.

## Backend

### Azure CLI wrapper and settings

- **`app/azure.py`:**
  - `az(args) -> JSON`. It takes an argument list, adds `--output json --only-show-errors`, uses a timeout, and resolves `az` with `shutil.which`.
  - `account() -> {user, subscriptionId, subscriptionName, tenantId}` comes from `az account show`.
  - Errors become `AzError` with az's message. "Not logged in" maps to a clear 401 telling the user to run `az login` on the host.
- **`app/settings.py`:** local app settings live at `$LOWDEVOPS_WORKSPACE/settings.json`. The name doesn't match the project pattern, so it can't collide with a project. The file is written atomically and holds no secrets:
  ```jsonc
  {
    "backends": {
      "<subscriptionId>": {
        "resourceGroup": "rg-lowdevops-state",
        "storageAccount": "stlowdevops<10 hex>",
        "container": "tfstate",
        "location": "westeurope",
      },
    },
  }
  ```

### Bootstrap (`app/bootstrap/`)

`ensure_backend(subscription_id, location)` is idempotent. Each step first checks with a read-only `show` or `list` and creates only when the resource is missing. Every call passes `--subscription <id>`, except `az ad signed-in-user show`, which reads the signed-in user's object id for the role assignment.

| Step                                                                                                                                               | Check                                                                                                             | Create                                                                                                                                                                                                                                                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Resource group `rg-lowdevops-state`                                                                                                                | `az group show`                                                                                                   | `az group create --location <loc> --tags managedBy=lowdevops`                                                                                                                                                                                                                                                                                                               |
| Storage account `stlowdevops` + the first 10 hex characters of sha256(subscription id) (21 characters, lowercase, CAF `st`, within the 3–24 limit) | `az storage account show`                                                                                         | `az storage account create --kind StorageV2 --sku Standard_ZRS --min-tls-version TLS1_2 --https-only true --allow-blob-public-access false --allow-shared-key-access false --tags managedBy=lowdevops` (public network access stays at its default, Enabled; see below). If an existing account has lost any of these settings, `az storage account update` re-applies them |
| Blob versioning and soft delete                                                                                                                    | `az storage account blob-service-properties show`                                                                 | `… blob-service-properties update --enable-versioning true --enable-delete-retention true --delete-retention-days 30 --enable-container-delete-retention true --container-delete-retention-days 30`                                                                                                                                                                         |
| Data access for the signed-in user (Entra-only, no keys)                                                                                           | `az role assignment list --assignee <user object id> --scope <account id> --role "Storage Blob Data Contributor"` | `az role assignment create --assignee-object-id <user object id> --assignee-principal-type User` with the same role and scope                                                                                                                                                                                                                                               |
| Container `tfstate`                                                                                                                                | `az storage container exists --auth-mode login`                                                                   | `az storage container create --auth-mode login`                                                                                                                                                                                                                                                                                                                             |

- **Public network access stays Enabled.** The sandbox has no private network, so access is protected by Entra-only auth with shared keys disabled. A private endpoint is a later option.
- **Settings:** the result is recorded in `settings.json`.
- **Role propagation:** a fresh role assignment can take a minute to apply. Container creation is retried on 403 for up to 2 minutes.

### Runner (`app/runner/`)

**Run directory.** The runner works in the project directory (`<workspace>/<name>/`, already guarded by the M3.1 dir-fd checks). It holds:

- `main.tf`, generated as before.
- `runtime.tf`: generated by the runner and never edited. It contains `terraform { backend "azurerm" {} }`, plus `provider "azurerm" { features {} storage_use_azuread = true }` because AVM modules require `features`. Keeping these out of `main.tf` leaves the M1 snapshots and the HCL editor unchanged.
- `.terraform/`, `plan.tfplan` and `run.log`, which are all gitignored.

**Environment.** Terraform runs with:

- `ARM_USE_CLI=true`, `ARM_SUBSCRIPTION_ID=<confirmed id>`, `TF_IN_AUTOMATION=1` and `TF_INPUT=0`
- `-no-color` on every command
- no `ARM_CLIENT_SECRET`, `ARM_CLIENT_CERTIFICATE*`, `ARM_OIDC_*` or `TF_VAR_*` passed through, so the app never uses stored credentials or variables
- an argument list in its own process group, resolved with `shutil.which`
- timeouts of 10 minutes for `init`, 30 for `plan` and 60 for `apply`; a timeout kills the whole group

**One run per project.**

- A per-project lock in the API process. A second run, plan or apply, while one is active gets **409** with the running run's id.
- Terraform's own state lock is the second line of defence.
- A run keeps `{id, kind, status: running|succeeded|failed, exitCode, startedAt, finishedAt}` and its log lines in memory. Log lines are also appended to `run.log`.

**Plan:** `POST /api/projects/{name}/runs/plan`, body `{ "subscriptionId": "<typed or confirmed id>" }`.

1. It returns 422 unless `subscriptionId == project.subscription.id`, and 409 unless `az account show` has access to that subscription. This is the subscription-confirm step.
2. It returns 409 "Bootstrap the state backend first" if `settings.json` has no backend for that subscription.
3. Start the run (202 `{runId}`), then in a worker thread:
   1. Regenerate `main.tf` from `project.json`, the only source of truth, and write `runtime.tf`.
   2. `terraform init -input=false -no-color -reconfigure`, with `-backend-config` for `resource_group_name`, `storage_account_name`, `container_name`, `key=<name>.tfstate`, `use_azuread_auth=true` and `subscription_id`.
   3. `terraform plan -input=false -no-color -out=plan.tfplan`.
   4. `terraform show -json plan.tfplan`. This is parsed in memory and not kept on disk.
   5. Run the M4 guardrails `check(project, catalog, plan_json)`.
   6. Store a **plan record** in memory (after an API restart, plan again):
      - `{planSha256, modelSha256, createdAt}`
      - a summary: each change with its address and action (create, update, delete or replace), the addresses that are destroyed or replaced, and a one-line text
      - the guardrail report
4. Plan output shows drift: resources whose `change.actions` include `update` or `delete` while the model did not change them are listed as reported by Terraform. No drift UI beyond that (PRD out of scope).

**Apply:** `POST /api/projects/{name}/runs/apply`, body `{ "planSha256", "confirmName", "confirmDestroy": bool }`.

The request is rejected unless all of these hold:

- `plan.tfplan` exists and its sha256 equals both the stored plan record and `planSha256`. Otherwise 409, "Plan again: there is no reviewed plan".
- The model is unchanged since the plan (`modelSha256` of `project.json`). Otherwise 409.
- `confirmName == name`. Otherwise 422.
- The summary has no deletes or replaces, or `confirmDestroy` is true. Otherwise 422.
- The guardrail report says `apply_allowed`. Waivers are re-applied from the current `project.json`, which is allowed, because waivers cannot change `blocked` for high or critical findings. Otherwise 409 with the blocking findings.

Then it runs `terraform apply -input=false -no-color plan.tfplan`, only ever with the saved plan file and never `-auto-approve` on a config. Afterwards it deletes `plan.tfplan` and the plan record, so each plan is applied at most once.

**Read endpoints:**

- `GET /api/projects/{name}/runs/current` returns the current run and the plan record if there is one.
- `GET /api/runs/{runId}` returns a run's status, and `GET /api/runs/{runId}/log` is its **Server-Sent Events** stream (run ids are random, and bootstrap runs use the same routes):
  - It sends the lines so far, then new lines as they arrive (`event: line`).
  - It ends with `event: exit`, `data: {"exitCode": n, "status": "..."}`, then closes. This is the exit criterion: "the log stream ends with the exit code".
  - SSE is a plain GET, so it still goes through the Host guard.

**Other endpoints:**

- `GET /api/azure/account`
- `GET /api/backends/{subscriptionId}`, which returns the recorded backend or 404
- `POST /api/backends/{subscriptionId}/bootstrap`, body `{ "location", "confirmSubscriptionId" }`. It runs in the same run framework, under the key `bootstrap:<sub>`, and streams its log the same way.

All write routes keep the M3 Origin and body guards.

## Frontend: Run tab (`frontend/src/run/`)

A fifth tab, **Run**, in four parts:

1. **Account:** "Signed in as \<user\>", plus the subscription name and id from `az account show`. The project's subscription id is shown next to it, and a mismatch is an Alert.
2. **State backend:** the recorded backend, or a **Bootstrap state backend** button. It needs a checkbox, "Create the state backend in subscription \<name\> (\<id\>)". The log streams below it.
3. **Plan:**
   - A required checkbox, "I confirm subscription \<name\> (\<id\>) for this plan". Then a **Plan** button.
   - **Live log.** A scrollable, focusable `region` with `aria-live="off"`, so it doesn't chatter. It is `aria-busy` while a run is going. Start and finish are announced by one `role="status"` line in the tab (never `aria-busy`, and not repeated through the store's announcer, so nothing is read twice), which says "Planning…", "Plan ready: 2 to add, 0 to change, 1 to destroy" or "Plan failed (exit 1)".
   - **Plan summary.** A table of the changes. Deletes and replaces are highlighted with text ("Destroy", "Replace"), not colour alone.
   - **Guardrails.** The report from the backend's own plan, reusing the M4 status line and findings list.
4. **Apply:** visible once a plan is ready.
   - A text field, "Type the project name to apply".
   - When the plan destroys or replaces anything, a second checkbox: "I understand this destroys or replaces N resources".
   - The **Apply** button stays `aria-disabled` until the name matches, the destroy box is ticked if needed, and the guardrails allow apply. The reason shows as text next to it.
   - The apply log streams like the plan log.
   - **Focus.** When a run's controls disappear on success, focus moves on instead of dropping to the page: after bootstrap to the plan confirmation, after apply to the run log.

## Files touched

- **Backend:**
  - `backend/app/{azure,settings}.py`
  - `backend/app/bootstrap/`
  - `backend/app/runner/`
  - `backend/app/api/{runs,azure}.py`
  - `backend/app/main.py`
- **Backend tests:**
  - `backend/tests/bin/{terraform,az}`, fake scripts that record argv and env and replay scenarios chosen by `LOWDEVOPS_FAKE_*`. They never touch Azure.
  - `backend/tests/{runner,bootstrap}/`
- **Frontend:**
  - `frontend/src/run/*`
  - `frontend/src/App.tsx`
  - `frontend/src/api.ts`
  - `frontend/e2e/m5.spec.ts`
- **Scripts:** `scripts/e2e-sandbox.sh`, the human gate.
- **Docs:** `docs/ARCHITECTURE.md` (flow and trust boundaries), `backend/CLAUDE.md` and `frontend/CLAUDE.md`.

## Exit criteria → proof

| Criterion                                                                       | Proof                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Apply only accepts an existing `plan.tfplan`                                    | `tests/runner/test_apply.py`. Apply with no plan, a changed plan file, a changed model or a wrong sha256 each gets 409. A good apply runs `terraform apply -input=false -no-color plan.tfplan`, which the fake records, then deletes the plan                                                                                                                                                                                                                  |
| A second concurrent run gets 409                                                | PR A: `tests/runner/test_runs.py::test_one_run_per_key_and_a_second_start_is_busy` and `tests/bootstrap/test_bootstrap.py::test_a_second_bootstrap_while_one_runs_is_409`. PR B: `tests/runner/test_terraform.py::test_a_second_run_while_one_plans_is_409_with_its_id`, where the fake `terraform plan` blocks until a switch file is removed, and a second plan gets 409 with the running id                                                                 |
| The log stream ends with the exit code                                          | `tests/runner/test_runs.py::test_the_log_stream_ends_with_the_exit_code`. SSE events arrive in order and the last is `exit` with the fake's exit code, 0 and non-zero                                                                                                                                                                                                                                                                                          |
| Apply is disabled until the project name is typed                               | `e2e/m5.spec.ts` (fake terraform and az on the e2e API's PATH). Apply is `aria-disabled` until the name is typed, then enabled. axe runs on every state                                                                                                                                                                                                                                                                                                        |
| A plan with destroys needs a second confirmation                                | the same spec, with the fake plan scenario that has a delete. Typing the name is not enough until the destroy checkbox is ticked                                                                                                                                                                                                                                                                                                                               |
| Bootstrap issues the expected create commands, and a second run creates nothing | `tests/bootstrap/test_bootstrap.py`. The fake `az` replays "missing" and then "exists". The test asserts the exact create argument lists (versioning, soft delete, `--allow-blob-public-access false`, `--allow-shared-key-access false`, TLS 1.2), and that the second run issues only `show`/`list`/`exists` calls                                                                                                                                           |
| **Human gate:** `scripts/e2e-sandbox.sh` exits 0 against the sandbox            | The script starts the API on a temporary workspace, creates a project with one resource group, and drives bootstrap → plan → apply through the API with `curl`, parsing JSON with `python3` (the dev container has no `jq`). It then runs `terraform destroy` itself in the project directory as cleanup, outside the app, because destroy-all is out of scope. It prints each step and exits non-zero on the first failure. **You run it.** Claude never does |

## Out of scope

- Destroy-all from the app, import, and scheduled or auto runs (per the ROADMAP).
- Service principals or stored credentials.
- Private endpoints for the state account.
- Run history beyond the current run and `run.log`.
- Cancelling a running apply. Plan cancel is a follow-up.

## Risks

- **Fakes differ from the real tools.** The fakes replay recorded output shapes: `terraform show -json` uses the M4 plan fixture format, and `az` uses documented JSON. The human sandbox gate is the real check.
- **Role propagation delay** can make the first container create fail. It is retried, and the log says why.
- **Secrets in plan files.** `plan.tfplan` and the plan JSON may contain secrets. The plan JSON stays in memory, `plan.tfplan` is deleted after apply, and both are gitignored. The workspace is outside the repo.
- **One process.** The run lock lives in memory. A second API process could race, and Terraform's state lock still protects state. The API is single-user on localhost (PRD).
- **Size.** This is the largest milestone so far: runner, bootstrap, SSE and a UI tab. Its two halves, bootstrap and the runner, could be split into separate PRs if review gets heavy.

## Verification

- `make check` passes, using fakes only.
- `make e2e` passes the M3 and M4 suites plus `m5.spec.ts`, three runs in a row.
- spec-reviewer, security-reviewer (subprocesses, credentials and API surface) and a11y-reviewer (`frontend/src`) all return PASS.
- The human runs `scripts/e2e-sandbox.sh` against the sandbox subscription before merging.
