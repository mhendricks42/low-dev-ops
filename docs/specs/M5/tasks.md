# M5 — tasks

One Conventional Commit per task. Exit criteria (EC) come from [ROADMAP](../../ROADMAP.md#m5--runner--state-bootstrap-week-3):

- **EC1:** apply only takes the saved plan
- **EC2:** a concurrent run gets 409
- **EC3:** the log stream ends with the exit code
- **EC4:** Playwright typed confirmations
- **EC5:** bootstrap creates the expected resources and is idempotent
- **EC6:** human sandbox gate

## PR A — `feat/m5-bootstrap`

- [x] A1 `refactor(backend)`: extract the subprocess helper into `app/proc.py`: which() resolution, own process group, killpg on timeout, env filter, line callback. The M4 scanner tests stay green.
- [x] A2 `feat(backend)`: run framework, `RunRegistry` with one run per key and logs, plus an SSE log endpoint (**EC2**, **EC3**).
- [x] A3 `feat(backend)`: `app/azure.py` (`az` wrapper, account) and `app/settings.py` (atomic `settings.json`), with the fake `az` binary.
- [ ] A4 `feat(backend)`: `ensure_backend` bootstrap with check-then-create steps and a retry on 403, plus the account and bootstrap API (**EC5**).
- [ ] A5 `docs`: ARCHITECTURE and backend CLAUDE.md for azure, settings, bootstrap and runs.

## PR B — `feat/m5-runner`

- [ ] B1 `feat(backend)`: `runtime.tf`, the terraform env, and plan steps (init, plan, show -json, guardrails) with the plan record, using the fake `terraform` binary.
- [ ] B2 `feat(backend)`: apply gates (saved plan sha, unchanged model, confirmName, confirmDestroy, guardrails) and single-use plans (**EC1**).
- [ ] B3 `feat(frontend)`: Run tab with account, backend and bootstrap, plan with live log and summary, guardrails, and apply with typed confirmations.
- [ ] B4 `test(frontend)`: `e2e/m5.spec.ts` covering typed confirmations and the destroy second confirm, with axe on each state (**EC4**).
- [ ] B5 `feat(scripts)`: `scripts/e2e-sandbox.sh`, the human gate (**EC6**). Claude never runs it.
- [ ] B6 `docs`: CLAUDE.md, ARCHITECTURE, and tasks ticked.
