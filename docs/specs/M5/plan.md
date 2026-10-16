# M5 — implementation plan

Spec: [spec.md](spec.md). Checklist: [tasks.md](tasks.md).

## Two PRs (decided with the user)

| PR  | Branch                        | Contents                                                                                                                                                                | Exit criteria it proves                                                                                                           |
| --- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| A   | `feat/m5-bootstrap`           | `app/azure.py`, `app/settings.py`, `app/bootstrap/`, the run framework (`app/runner/runs.py`: one run per key, logs, SSE), bootstrap and account API, and the fake `az` | Bootstrap issues the expected creates and is idempotent; a second concurrent run gets 409; the log stream ends with the exit code |
| B   | `feat/m5-runner` (based on A) | Terraform plan and apply (`app/runner/terraform.py`), the plan record and apply gates, the fake `terraform`, the Run tab, `e2e/m5.spec.ts` and `scripts/e2e-sandbox.sh` | Apply only takes the saved plan; Playwright typed confirmations; the human sandbox gate                                           |

## Approach

**Run framework (A).**

- `RunRegistry` keeps a dict of key → `Run` and a lock.
- `start(key, kind, steps)` raises `RunBusy` when a run for the key is active. The API maps that to 409.
- A run executes its steps in a daemon thread. Each step is a subprocess: argument list, own process group, timeout, environment, and output appended line by line to `Run.lines` and to an optional log file.
- `Run` has a `threading.Condition`, so log readers wait for new lines.
- SSE is a Starlette `StreamingResponse` over a generator. The generator yields the lines from an index, waits on the condition and ends with `event: exit`.
- The subprocess helper is shared with the M4 scanners: it is extracted from `guardrails/scanners.py` into `app/proc.py`, which handles which() resolution, the process group, killpg on timeout and the env filter.

**Bootstrap (A).**

- `ensure_backend` is a list of (check, create) pairs over `az`.
- The fake `az` in `tests/bin/az` records argv to a log. It answers from a scenario directory (`LOWDEVOPS_FAKE_AZ_STATE`): resources are files there, so a create makes a later show succeed, which is how idempotency is tested.
- The role-assignment retry loop is tested by making the first container create return 403.

**Terraform (B).**

- `plan` and `apply` are steps in the same framework.
- The fake `terraform` in `tests/bin/terraform` replays scenarios: no changes, create, a plan with a destroy, a failure, and blocking on a fifo to test concurrency. For `show -json` it prints a fixture plan.
- The apply gates are checked in the API before any subprocess runs.

## Risks

- **Threads and SSE in TestClient.** Starlette's TestClient streams fine. Tests wait on run completion with a timeout, never with sleeps.
- **The real `az` and `terraform` output** differs from the fakes. The sandbox gate in B is the real check.
