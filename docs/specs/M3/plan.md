# M3 — implementation plan

Spec: [spec.md](spec.md). Checklist: [tasks.md](tasks.md).

## Approach

**Backend first.** It is small and fully testable without a browser.

- `app/api/catalog.py`, `hcl.py` and `projects.py` are each an `APIRouter`, included in `app/main.py`.
- The catalog is loaded once, at import, with `load_catalog()`.
- `projects.py` resolves the workspace directory from `LOWDEVOPS_WORKSPACE` on every request, so tests can point it at `tmp_path` with `monkeypatch.setenv`.
- **Path rule:** check the name pattern, then `(root / name).resolve()` must sit directly inside `root.resolve()`.
- **Writes:** `tempfile.NamedTemporaryFile(dir=..., delete=False)`, then `os.replace`.

**Types.** `json-schema-to-typescript` writes `src/model/project.ts` and `src/model/catalog.ts`. A `types:check` script regenerates into a temp dir and diffs the result, and `npm run lint` runs it.

**Store.**

- `src/model/reducer.ts` is pure and unit-tested on its own.
- `src/model/store.tsx` adds the context and two debounced effects (save, and regenerate HCL).
- `src/api.ts` holds thin `fetch` wrappers that throw an `ApiError` carrying `{status, message, line}`.

**Pure helpers (`src/model/catalog.ts`), unit-tested:**

- `controlFor(spec)`: string, bool, number or json
- `allowedRefs(project, catalog, resourceId)`: the `(input, targetId, output)` triples
- `nextId(project, abbreviation)`
- `newResource(entry, project)`: defaults, fills and name pre-fill

**Views.** Wizard, Canvas plus the list view, and HCL. All of them read `useProject()` and dispatch actions; none keeps its own copy of the model.

- **Canvas:** React Flow, using a group node for containment (`parentId` plus `extent: "parent"`).
- **HCL editor:** `@monaco-editor/react` with `loader.config({ monaco })`. The editor worker comes from `monaco-editor/esm/vs/editor/editor.worker?worker`.

**E2E.** `playwright.config.ts` gives the backend a fresh temp workspace, and one spec file covers each exit criterion. axe runs through `@axe-core/playwright`.

## Risks

See [spec.md](spec.md#risks). Ordering also matters: the backend and the pure helpers land first, so the UI tasks build on tested code.
