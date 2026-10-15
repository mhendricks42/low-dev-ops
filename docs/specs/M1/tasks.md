# M1 — tasks

One Conventional Commit per task. Exit criteria from [ROADMAP](../../ROADMAP.md#m1--internal-model--hcl-engine-week-12) are mapped in bold.

- [x] T1 `chore(backend)`: add python-hcl2. Spike test pins down how it represents literals versus `module.x.y` versus `var.x`.
- [x] T2 `feat(backend)`: Pydantic model, with valid and invalid fixtures. Proves **exit criterion 1: schema**.
- [x] T3 `feat(backend)`: JSON Schema generation, `make schema`, committed schema, and the drift test.
- [ ] T4 `feat(backend)`: HCL value renderer and generator, with snapshot tests for all valid fixtures. Proves **exit criterion 2: snapshots**.
- [ ] T5 `feat(backend)`: top-level block splitter. Tests cover heredocs, comments and strings containing braces, plus error lines.
- [ ] T6 `feat(backend)`: parser mapping AVM modules and refs, inheriting fields from `previous`, with syntax errors raised and no partial model. Proves **exit criterion 3: round-trip** and **exit criterion 4: custom HCL survives**.
- [ ] T7 `ci`: the `terraform-validate` job (`fmt -check` + `init` + `validate` per fixture). Proves **exit criterion 5**.
- [ ] T8 `docs`: backend/CLAUDE.md commands, with tasks.md ticked off.
