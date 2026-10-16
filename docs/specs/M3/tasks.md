# M3 — tasks

One Conventional Commit per task. Exit criteria (EC) come from [ROADMAP](../../ROADMAP.md#m3--gui-views-wizard-canvas-hcl-editor-week-23).

- [ ] T1 `feat(backend)`: `/api/catalog`, `/api/hcl/generate` and `/api/hcl/parse` (422 with the line number), with tests.
- [ ] T2 `feat(backend)`: `/api/projects` list/get/put, workspace safety (name pattern, staying inside the workspace, atomic writes, `meta.name` must match). Tests include path-escape attempts.
- [ ] T3 `chore(frontend)`: add the dependencies, generated model types, and a `types:check` drift check in lint.
- [ ] T4 `feat(frontend)`: reducer, store, API client and pure catalog helpers, with unit tests (`parent_id` sets `parent`, control inference, allowed refs).
- [ ] T5 `feat(frontend)`: design-system tokens and accessible components, with unit tests for labels and errors.
- [ ] T6 `feat(frontend)`: app shell (tabs, status) and the wizard (add and edit, More options, ref selects, custom HCL read-only).
- [ ] T7 `feat(frontend)`: Monaco HCL editor with save, inline error, unsaved-edits guard and discard.
- [ ] T8 `feat(frontend)`: React Flow canvas (nesting, edges, allowed connections, layout) and the keyboard list view.
- [ ] T9 `test(frontend)`: Playwright for **EC1** wizard→canvas+HCL, **EC2** HCL→wizard, **EC3** invalid HCL, **EC4** keyboard only and **EC5** axe on every panel. Screenshots go in `docs/specs/M3/`.
- [ ] T10 `docs`: frontend/CLAUDE.md and backend/CLAUDE.md commands, with tasks ticked.
