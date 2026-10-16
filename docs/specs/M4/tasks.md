# M4 — tasks

One Conventional Commit per task. Exit criteria (EC) come from [ROADMAP](../../ROADMAP.md#m4--guardrails-week-3): EC1 high blocks, EC2 waived medium allowed, EC3 clean has zero findings, EC4 naming limits; plus the UI criteria from the spec (keyboard waive, axe).

- [x] T1 `feat(backend)`: `Project.required_tags`, `CatalogEntry.name_rules`, and `nameRules` in every catalog entry. Regenerate the schemas and frontend types.
- [x] T2 `feat`: CAF naming (`caf_name`, `func` for function apps) in the backend and frontend, with shared vectors (**EC4**).
- [x] T3 `feat(backend)`: merge project tags into resource tags in the generator and parser, and update the snapshots.
- [x] T4 `feat(backend)`: findings, naming and tag checks, and the waiver/report logic (`run.py`).
- [x] T5 `feat(backend)`: scanner adapters (Conftest, Checkov, Trivy), fail-closed handling, stub binaries, starter Rego policies and `severity.yaml`.
- [x] T6 `feat(backend)`: `POST /api/guardrails/check` and the fixtures `high`, `waived-medium` and `clean` (**EC1–EC3**).
- [x] T7 `test(backend)`: real-scanner and `conftest verify` tests; set `LOWDEVOPS_REQUIRE_SCANNERS` in the dev container.
- [x] T8 `feat(frontend)`: waiver actions, the API client and the Checks tab, with unit tests.
- [x] T9 `test(frontend)`: `e2e/m4.spec.ts` covering the keyboard waive flow and axe on every state, with screenshots.
- [x] T10 `docs`: the `caf-naming` skill, `policies/README.md`, CLAUDE.md commands and ARCHITECTURE notes.
