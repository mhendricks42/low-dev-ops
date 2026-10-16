# Policies

Guardrail policies (M4, [spec](../docs/specs/M4/spec.md)). High and critical findings block apply; medium and low can be waived with a reason that is stored in `project.json`.

| Path                        | What                                                                                                                                                               |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `conftest/*.rego`           | Rules on the project model (`input.resources[].{id, module, inputs}`). `deny` is high, `warn` is medium. Each result is an object with `id`, `resource` and `msg`. |
| `conftest/policy_test.rego` | Their unit tests: `conftest verify --policy policies/conftest` (run by `backend/tests/guardrails/test_real_scanners.py`).                                          |
| `scanners.yaml`             | The Checkov and Trivy checks LowDevOps adopts, and the severity it gives each. Checks not listed are not run (Checkov) or dropped (Trivy).                         |

## Add a rule

1. Write it in `conftest/<area>.rego`. Give it a stable id (`LDO_<AREA>_<WHAT>`); if one resource can fail it more than once, add a suffix (`LDO_NSG_ADMIN_OPEN:<rule>`) so one waiver covers one problem.
2. Add a passing and a failing case to `policy_test.rego`, then run `conftest verify --policy policies/conftest`.

## Adopt a scanner check

Add `CHECK_ID: severity  # what it checks` under `checkov:` or `trivy:` in `scanners.yaml`. If it changes what a guardrail fixture reports, re-record that fixture's scanner output (see `backend/tests/bin/_stub.py`) and update `test_real_scanners.py`.
