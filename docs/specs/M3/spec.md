# M3 — GUI views: wizard, canvas, HCL editor: spec

## Context

ROADMAP §M3: design-system tokens and components, a schema-driven wizard, a React Flow canvas with a keyboard list view, and a Monaco editor, all bound to one model store. ARCHITECTURE's sync rules apply as written: `project.json` is the only source of truth, wizard and canvas edits regenerate HCL right away, HCL edits are parsed on save, and a parse error leaves the model unchanged with the error shown inline.

M3 is the first milestone with API routes and real UI. It uses the M1 generator and parser and the M2 catalog as they are; it does not change their output.

## Backend: workspace and API (`backend/app/api/`, `backend/app/workspace.py`)

**Workspace.** Projects live in `$LOWDEVOPS_WORKSPACE` (default `~/lowdevops-workspace`), one folder per project: `<workspace>/<name>/project.json` and the derived `<workspace>/<name>/main.tf`. A project name must match `^[a-z][a-z0-9-]{1,38}[a-z0-9]$` before it reaches a path; the resolved path must also sit inside the workspace. Writes go to a temp file in the same folder and are renamed into place, `project.json` first. `main.tf` is always rebuilt from the model, never read.

**Routes** (all under `/api`, JSON, still bound to `127.0.0.1`):

| Route | Does |
| --- | --- |
| `GET /api/catalog` | Every catalog entry (the M2 `CatalogEntry` dumped by alias) |
| `GET /api/projects` | Project names in the workspace |
| `POST /api/projects` | Create from `{name, location, workload, env, region}`; 409 if it exists |
| `GET /api/projects/{name}` | `{project, hcl, issues}` |
| `PUT /api/projects/{name}` | Body is a full `Project`. Validates it, runs `check_project`; any error-level issue → 422 with nothing written. Otherwise saves and returns `{project, hcl, issues}` |
| `PUT /api/projects/{name}/hcl` | Body `{hcl}`. `parse(hcl, current)`, then the same checks as above. `HclParseError` → 422 `{message, line}` and nothing written. Otherwise saves the parsed model and returns `{project, hcl}` with the canonical (reformatted) HCL |

`issues` are the M2 `CatalogIssue`s (warnings only, since errors are rejected). The create route fills `subscription.location` from the form and leaves `subscription.id` and `tenantId` empty; the subscription-confirm step that fills them is M5.

## Frontend (`frontend/src/`)

- **`model/`**: TypeScript types generated from `backend/schema/project.schema.json` and `catalog/catalog.schema.json` with `json-schema-to-typescript`, written by `make schema`, with a drift test. The **model store** (`model/store.ts`) holds the one in-memory `Project`, its HCL, the catalog and a save state. Views read it with a hook and change it only through store actions (`addResource`, `updateResource`, `removeResource`, `addRef`, `removeRef`, `moveResource`, `saveHcl`). Each action PUTs the whole project and replaces the store's copy with the response, so the HCL view always shows generator output. A rejected PUT leaves the store unchanged and sets an error.
- **`design-system/`**: CSS custom-property tokens (color, spacing, type scale, radius, focus ring) with light and dark values that meet AA contrast, and components built on native elements: `Button`, `TextField`, `Select`, `Checkbox`, `Field` (label, hint, error wired with `aria-describedby`), `Tabs` (WAI-ARIA tabs pattern), `Disclosure` and `StatusMessage` (`role="status"` / `role="alert"`).
- **Pages.** `/` lists projects and has a create form. `/projects/<name>` has the wizard on the left and a tab set on the right: **Canvas**, **List**, **HCL**. Routing is a small `pathname` switch, no router dependency.
- **`wizard/`**: "Add resource" picks a catalog entry by title, then renders a form from the entry: an id field (suggested as `<cafAbbreviation><n>`), every `basic` input, `advanced` inputs inside a "More options" disclosure, and `hidden` inputs never. The control follows the default's JSON type: text, number, checkbox, or a JSON text area for lists and objects, which shows an inline error when it does not parse. Each allowed ref is a select of existing resources from the `from` entry. Inputs with `fill: location` / `tenant_id` are prefilled from `subscription`; `fill: name` is prefilled from `naming.pattern` by plain substitution of `{type}` (the CAF abbreviation), `{workload}`, `{env}` and `{region}`, with no length or character rules (those are M4). Selecting an existing resource opens the same form in edit mode with its current values. `customHcl` entries are listed read-only.
- **Containment.** When a resource's ref targets a resource-group entry, the wizard sets `parent` to that resource group. The canvas draws `parent` as nesting, and that ref is not also drawn as an edge.
- **`canvas/`**: `@xyflow/react`. Resource groups are group nodes with their children inside; other resources and each `customHcl` entry (read-only, labelled "Custom HCL") are plain nodes. Every other ref is an edge labelled with its input. Connecting two nodes offers only the inputs the catalog allows (`isValidConnection`); picking one calls `addRef`. Dragging a node calls `moveResource`, which only changes `layout`, so the HCL does not change. New resources get a default position from their index.
- **List view (`canvas/ListView.tsx`)**: the keyboard equivalent of the canvas. A table of resources (id, type, parent, refs), each row with Edit, Remove and **Add reference** actions. Add reference is a small form: input (from the entry's allowed refs) and target (resources of the allowed type). Removing a resource that others reference shows the API's error.
- **`editor/`**: `@monaco-editor/react` with Monaco bundled locally (`loader.config({ monaco })`, so nothing loads from a CDN) and its built-in `hcl` language. The buffer shows the store's HCL until the user types. **Save** (also Ctrl/Cmd+S) calls `saveHcl`; on 422 it shows the message inline in `role="alert"` with the line number and a Monaco marker on that line, and the store is unchanged. **Discard** reloads the store's HCL. If the model changes while the buffer has unsaved edits, the buffer is kept and a status says that saving will replace the other change.

## Files touched

- `backend/app/{workspace.py,api/__init__.py,api/projects.py,api/catalog.py}`, `backend/app/main.py` (mount routers)
- `backend/tests/api/test_{catalog,projects,hcl,workspace}.py`
- `frontend/src/{model,design-system,wizard,canvas,editor,pages}/**` with `*.test.tsx` beside them, `frontend/src/App.tsx`
- `frontend/e2e/m3.spec.ts`, `frontend/e2e/a11y.spec.ts`; `frontend/playwright.config.ts` (a fresh temp `LOWDEVOPS_WORKSPACE` per run); the M0 hello test updated for the new home page
- `frontend/package.json` and lock: `@xyflow/react`, `@monaco-editor/react`, `monaco-editor`; dev: `@axe-core/playwright`, `json-schema-to-typescript`
- `Makefile` (`schema` also writes the TS types), `frontend/CLAUDE.md`, `backend/CLAUDE.md`, CI e2e artifact path for the M3 screenshots

## Exit criteria → proof (Playwright, `make e2e`)

| Criterion | Proof |
| --- | --- |
| RG + VNet added in the wizard appear on the canvas (VNet nested in RG) and in the HCL | `m3.spec.ts`: adds both, checks the VNet node is inside the RG group node, then opens HCL and finds `module "rg1"`, `module "vnet1"` and `parent_id = module.rg1.resource_id` |
| Changing a value in HCL and saving shows the new value in the wizard | `m3.spec.ts`: edits `address_space`, saves, opens `vnet1` in the wizard and checks the field |
| Saving invalid HCL shows an inline error and leaves the model unchanged | `m3.spec.ts`: saves broken HCL, expects the alert, then reloads the page and checks `GET /api/projects/<name>` still matches the earlier model |
| Keyboard-only: create a resource and add a reference | `m3.spec.ts`: drives the wizard and the List view with `page.keyboard` only (no `click`, `fill`, `hover` or mouse calls), then checks the ref in the HCL |
| axe-core reports 0 WCAG 2.2 AA violations on every page | `a11y.spec.ts`: `@axe-core/playwright` with tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` on the home page and on the project page with each tab open, the wizard form open and the HCL error shown |

Backend unit tests cover every route, including path traversal and bad names (`..`, `/`, uppercase, too long), 409 on create, 422 on a catalog error, and "nothing written" on every 422. Vitest covers the store (a failed PUT leaves state unchanged), the form builder (tiers, control types, fills), containment, and the list view's ref form.

## Decisions (defaults picked; change them before the build starts)

1. **Autosave.** Each wizard or canvas action saves immediately. There is no separate "Save project" step, which keeps the disk and the store identical.
2. **`fill: name` is prefilled by plain pattern substitution.** CAF length and character rules, and `func` for Function Apps, stay in M4.
3. **Unsaved HCL edits are never discarded silently.** The other views stay usable, and the editor warns that a save will overwrite their change.

## Out of scope

- Plan and apply buttons, the subscription-confirm step, `az account show` (M5)
- CAF naming rules, tags from `project.tags`, guardrails and waivers UI (M4)
- Editing `customHcl` outside the HCL editor, undo/redo, auto-layout, deleting or renaming projects
- Subnets as their own nodes, landing-zone patterns (M6), onboarding (M6)
- Any change to generator or parser output

## Risks

- **Monaco and axe.** Monaco renders its own DOM; if axe flags it, the fix is Monaco options (`ariaLabel`, accessibility support on) or a scoped, documented exclusion of Monaco's internal widgets only, never of the page.
- **React Flow and keyboard users.** React Flow's own keyboard support is partial, which is why the List view is the required path and is what the keyboard test drives.
- **Typing into Monaco in Playwright** fights auto-closing brackets, so tests use `keyboard.insertText` after selecting all.
- **Bundle size.** Monaco is large; it is loaded lazily on the HCL tab.

## Verification

1. `make check` (pytest, vitest, ruff, mypy, eslint, tsc).
2. `make schema && git diff --exit-code`.
3. `make e2e`, with screenshots of the canvas, list and HCL error saved to `docs/specs/M3/` and attached to the PR.
4. spec-reviewer, security-reviewer (new routes, file paths) and a11y-reviewer (`frontend/src`), then a PR titled `feat: M3 GUI views`.
