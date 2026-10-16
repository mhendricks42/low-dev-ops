# M2 — tasks

One Conventional Commit per task. Exit criteria from [ROADMAP](../../ROADMAP.md#m2--catalog-week-2) are mapped in bold.

- [x] T1 `chore(backend)`: add pyyaml and types-pyyaml.
- [x] T2 `feat(backend)`: catalog model and loader, with bad-entry fixtures, plus the committed catalog JSON Schema and its drift test. Proves **exit criterion 1: every YAML passes the catalog schema**.
- [x] T3 `feat(catalog)`: the foundation entries (RG, VNet, NSG, Key Vault, Storage), with `test_entries.py` checking basic-input defaults and allowed refs. Proves **exit criterion 4: basic inputs have CAF defaults and allowed refs point at real outputs** for these entries.
- [x] T4 `feat(catalog)`: the compute entries (App Service plan, web/site, Container Apps environment, container app, AKS), covered by the same parametrized tests.
- [ ] T5 `feat(backend)`: `example_project` and `check_project`, with every M1 valid fixture passing `check_project`.
- [ ] T6 `feat(backend)`: `check-catalog` (init, pin check, interface check, validate) with a stub `terraform` in tests, plus `scripts/check-catalog` and `make catalog`.
- [ ] T7 `ci`: the `check-catalog` job. Proves **exit criteria 2 and 3: pins exist and examples validate**.
- [ ] T8 `docs`: the avm-catalog skill, catalog/README.md and backend/CLAUDE.md, with tasks.md ticked off.
