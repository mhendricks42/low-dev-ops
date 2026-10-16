# M3 — GUI views (wizard, canvas, HCL editor): spec

## Context

ROADMAP §M3 covers four pieces, all bound to one model store:

- design-system tokens and components
- a schema-driven wizard
- a React Flow canvas with a keyboard list view
- a Monaco HCL editor

This is the first milestone with UI. It builds on M1 (model, generator, parser) and M2 (catalog). PRD rows to respect:

- **Experience:** the wizard and canvas stay in two-way sync with the HCL.
- **Sync rules:** wizard and canvas edits regenerate the HCL right away. HCL is parsed on save. On a parse error the model is unchanged and the error shows inline.
- **Canvas edges:** an edge is a typed ref the catalog allows. Containment is drawn as nesting.
- **Accessibility:** WCAG 2.2 AA, with every canvas action also available from the keyboard or a list view.

Decided with the user (2026-10-16):

- **Persistence:** M3 adds minimal project save/load to a local workspace.
- **Wizard controls:** each control's type is inferred from the catalog input's default, so the catalog format does not change.

## Backend API (`backend/app/api/`, mounted in `app/main.py`)

All routes live under `/api` and the server binds to `127.0.0.1` only. Request bodies are Pydantic models and an invalid body returns 422.

| Route                      | Request → response                                                                                                                                                         |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /api/catalog`         | → every catalog entry, by alias, in a stable order. Loaded once at startup with `load_catalog()`.                                                                          |
| `POST /api/hcl/generate`   | `{project}` → `{hcl}` (M1 `generate`).                                                                                                                                     |
| `POST /api/hcl/parse`      | `{hcl, previous}` → `{project}`, or 422 `{message, line}` from `HclParseError`. `hcl` is at most 1 MB.                                                                     |
| `GET /api/projects`        | → `{names: [...]}` (sorted directory names under the workspace that contain a `project.json`).                                                                             |
| `GET /api/projects/{name}` | → `{project}`, or 404.                                                                                                                                                     |
| `PUT /api/projects/{name}` | `{project}` → `{issues}`. Writes `project.json` and the generated `main.tf`. `issues` are the M2 `check_project` results (warnings and errors are reported, not blocking). |

**Workspace rules** (ARCHITECTURE trust boundaries):

- The workspace directory comes from `LOWDEVOPS_WORKSPACE` and defaults to `~/lowdevops`.
- `{name}` must match `^[a-z][a-z0-9-]{0,62}$` before it becomes a path. The resolved path must also stay inside the workspace, which is checked again after `resolve()`.
- A PUT where `project.meta.name != name` is rejected with 422.
- Each file is written atomically: write a temp file in the same directory, then `os.replace`.
- No subprocesses, and no deletes.

**Request guards** (added after the security review):

- `TrustedHostMiddleware` accepts only the hosts `127.0.0.1` and `localhost`. Anything else gets 400, which stops DNS rebinding.
- POST, PUT, PATCH and DELETE requests carrying an `Origin` header must come from `http://127.0.0.1:5173` or `http://localhost:5173`, or they get 403. Clients that send no `Origin` (curl, tests) are allowed.
- Request bodies are capped at 2 MB (413), whether or not they declare a `Content-Length`.
- A symlinked project directory or `project.json` is refused (422), and an invalid stored `project.json` returns 422, not 500.
- **Accepted risk:** a process running as the same user could swap the project directory for a symlink between the check and the write. The threat model already trusts same-user local processes (single user, one machine), so the directory-fd rewrite needed to close this race is not worth its code in M3.

## Frontend (`frontend/src/`)

**Types.** `npm run types` generates `src/model/project.ts` and `src/model/catalog.ts` with `json-schema-to-typescript`, from `backend/schema/project.schema.json` and `catalog/catalog.schema.json`. The files are committed, and `npm run lint` fails if they drift. No model types are hand-written (frontend/CLAUDE.md).

**Store (`src/model/store.tsx`).** One React context with a pure `useReducer`, which holds the only copy of the `Project`. Actions:

- `addResource`
- `setInput`
- `setRef`: setting `parent_id` also sets `parent` to the ref's target, which is how VNet-in-RG nesting arises
- `removeRef`
- `removeResource`
- `moveNode` (writes `layout`)
- `replaceProject` (used by HCL save and load)

Every change triggers a debounced `PUT` (save) and a `POST /api/hcl/generate`. A visible `role="status"` region reports "Saved" or the error.

**Project.** The project comes from `?project=<name>`, defaulting to `default`. The app loads it, or creates an empty project (location `westeurope`, naming defaults) when it isn't found.

**Design system (`src/design-system/`).**

- `tokens.css`: colours that meet AA contrast (4.5:1 for text, 3:1 for UI parts), spacing, type scale, and a visible 2 px focus ring.
- Components: `Button`, `TextField`, `NumberField`, `Checkbox`, `Select`, `JsonField` (a textarea that validates JSON and shows its error), `Tabs` (ARIA tablist with arrow keys), `Dialog` (native `<dialog>`), `Status`, `Alert`.
- Every control has a visible `<label>`, and every error is linked to its field with `aria-describedby`.

**Layout.** A header holds the project name and save status. Main navigation is a `Tabs` with three panels: **Wizard**, **Canvas** and **HCL**. Each panel is a "page" for the axe check.

**Wizard (`src/wizard/`).**

- **Add resource:**
  - choose a type from the catalog, grouped by category
  - id, pre-filled with the next free one, e.g. `rg1`
  - then a form for the type
- **Edit resource:** pick an existing resource from a list. Its form shows the current values, which is how an HCL edit shows up.
- **Form controls:**
  - Basic inputs are shown. Advanced inputs sit behind a "More options" disclosure. Hidden inputs are never shown and keep their default.
  - The control is chosen from the default: string → `TextField`, bool → `Checkbox`, number → `NumberField`, anything else → `JsonField`.
  - Fill inputs:
    - `fill: name` is a text field pre-filled from `naming.pattern`, with `{type}` replaced by the CAF abbreviation. Real naming rules are M4.
    - `fill: location` takes `subscription.location`, and `fill: tenant_id` takes `subscription.tenantId`. Both stay editable.
  - A ref input renders as a `Select` of the existing resources whose catalog entry is the ref's `from`, and sets a ref rather than a literal.
- **Custom HCL** entries are listed read-only.

**Canvas (`src/canvas/`).**

- **Nodes:** React Flow (`@xyflow/react`). Each resource is a node at its `layout`, or on a simple grid when `layout` is null. A resource with a `parent` is drawn nested inside its parent's group node. Custom HCL blocks get their own node, labelled "Custom HCL".
- **Edges:** every ref except `parent_id` is an edge.
- **Connecting:** dragging a connection is allowed only when the source's catalog entry has a ref from the target's module. Several matching inputs → a `Dialog` asks which one.
- **Moving:** dragging a node writes its `layout`.

**Keyboard list view.** It sits next to the canvas and offers the same actions without a mouse. It is a table of resources, and each row has:

- **Add reference:** a `Dialog` with a select of allowed (input, target) pairs
- **Remove reference**
- **Remove**

**HCL editor (`src/editor/`).**

- **Monaco setup:** Monaco is bundled locally (`monaco-editor` with `loader.config({ monaco })`; no CDN, since the app works offline) and uses HCL syntax highlighting.
- **Display:** it shows the generated HCL. While the user has unsaved edits, regenerating does not overwrite them, and a status says so.
- **Save:** "Save HCL", or Ctrl/Cmd+S in the editor, calls `/api/hcl/parse` with the current model as `previous`. On success it dispatches `replaceProject`.
- **Errors:** on a 422, an `Alert` shows the message and line, a Monaco marker is added, and the model is unchanged.

## Files touched

- **Backend:**
  - `backend/app/api/{__init__,catalog,hcl,projects}.py`, wired in `backend/app/main.py`
  - `backend/tests/api/test_{catalog,hcl,projects}.py`, including path-escape and name-pattern tests
- **Frontend, app code:**
  - `frontend/src/{model,design-system,wizard,canvas,editor}/**`, replacing the M0 `App.tsx` hello page (the health check moves to the status bar)
  - unit tests next to the code
- **Frontend, e2e:**
  - `frontend/e2e/m3.spec.ts`
  - `frontend/playwright.config.ts`, where `LOWDEVOPS_WORKSPACE` is set to a temp dir
  - the M0 hello spec is updated to the new page
- **Frontend, packages:** `frontend/package.json` adds:
  - `@xyflow/react`
  - `monaco-editor` and `@monaco-editor/react`
  - dev: `@axe-core/playwright` and `json-schema-to-typescript`
- **Root:**
  - `Makefile`: `make schema` also runs `npm run types`
  - `docs/specs/M3/` and `frontend/CLAUDE.md` (new commands)

## Exit criteria → proof (Playwright, `frontend/e2e/m3.spec.ts`)

| Criterion                                                                        | Test                                                                                                                                                                                                           |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| RG + VNet added in the wizard → on the canvas (VNet nested in RG) and in the HCL | Add `rg1`, then `vnet1` with resource group `rg1`. The canvas shows a `vnet1` node inside the `rg1` group node. The HCL panel contains `module "vnet1"` and `parent_id = module.rg1.resource_id`.              |
| HCL value change + save → the wizard shows it                                    | Edit the `name` of `rg1` in Monaco, then save. The `rg1` form in the Wizard shows the new name.                                                                                                                |
| Invalid HCL save → inline error, model unchanged                                 | Type a syntax error, then save. An `alert` names the line. Wizard values and the saved `project.json` (via `GET`) are unchanged.                                                                               |
| Keyboard-only: create a resource and add a reference                             | Only `page.keyboard`, with no `click` or mouse calls. Add a NSG and a VNet in the wizard, then use the list view's "Add reference" to point the VNet's `parent_id` at the RG, and check the result in the HCL. |
| axe-core: 0 WCAG 2.2 AA violations on every page                                 | `AxeBuilder` with tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` and `wcag22aa`, on each of the three panels with a populated project, plus the open Add-reference dialog.                                    |

Covered by unit tests as well:

- the reducer actions, including `parent_id` → `parent`
- input-control inference
- allowed-ref computation
- the API routes and workspace path rules

## Out of scope

- Plan and apply buttons, and anything that runs terraform (M5)
- Naming and tag rules beyond the simple pattern pre-fill, and guardrail findings (M4)
- Deleting or renaming projects, and a project picker beyond `?project=`
- Undo/redo, auto-layout beyond a grid, and multi-file HCL
- Editing custom HCL from the wizard or canvas (it stays view-only, per the PRD)

## Risks

- **Monaco in Vite:** it needs its editor worker set up through `?worker` imports. It is a large bundle, which is acceptable for a localhost app.
- **axe vs third-party DOM:** Monaco and React Flow internals may trip axe rules. Fix them through their accessibility options (Monaco's `ariaLabel` and accessibility support, React Flow's `ariaLabel` props). Never exclude whole regions from the scan; any narrow exclusion needs a written reason in the test.
- **Two-way sync races:** a model change landing while HCL edits are unsaved. Decided above: unsaved edits win until saved or discarded. A "Discard edits" button resets the editor.
- **Path traversal** in `{name}` is the new trust boundary. It is covered by the pattern, the post-`resolve()` check and tests.

## Verification

1. `make check`, with the new pytest and vitest suites.
2. `make e2e`, with all five exit-criterion tests.
3. Screenshots of each panel attached to the PR.
4. The spec-reviewer, a11y-reviewer and security-reviewer (new file-writing API) subagents.
5. A PR titled `feat: M3 GUI views`.
