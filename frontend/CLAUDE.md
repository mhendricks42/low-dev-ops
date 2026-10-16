# Frontend (React + TypeScript + Vite)

Node 22. Run commands from `frontend/`, or use the root `make` targets. The dev server proxies `/api` to `127.0.0.1:8000`.

## Commands

| What        | Command                                                                                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Install     | `npm ci`                                                                                                                                                |
| Lint        | `npm run lint` (eslint + prettier --check)                                                                                                              |
| Format      | `npm run format`                                                                                                                                        |
| Typecheck   | `npm run typecheck`                                                                                                                                     |
| Unit tests  | `npm test` (vitest, jsdom)                                                                                                                              |
| One test    | `npx vitest run src/App.test.tsx`                                                                                                                       |
| E2E         | `npm run e2e` (Playwright; starts API and UI in a temp workspace, with stub guardrail scanners; writes `docs/specs/M3/*.png` and `docs/specs/M4/*.png`) |
| Run         | `npm run dev`, then open `/?project=<name>`                                                                                                             |
| Bundle size | `npm run size` (builds, then fails if a chunk passes its gzipped budget in `scripts/check-size.mjs`; part of `make test`)                               |
| Model types | `npm run types` (from the JSON Schemas; `npm run lint` fails if they drift)                                                                             |

## Rules

- TypeScript is strict: no `any`, no non-null `!`. Model types are generated from the backend JSON Schema, never hand-written.
- Wizard, canvas and editor all read and write one model store (`src/model/store.tsx`, actions in `reducer.ts`). A view never holds its own copy of the model.
- `src/model/project.ts` and `catalog-entry.ts` are generated: never edit them. UI builds on `src/design-system/` components, not raw styled elements.
- Monaco is bundled locally (`src/editor/monaco.ts`); never load it from a CDN. Every new page or dialog gets an axe check in `e2e/m3.spec.ts` style (M4: `e2e/m4.spec.ts`).
- Accessibility (WCAG 2.2 AA): native elements first, every control labelled, status changes in `role="status"`, and every canvas action reachable from the keyboard list view.
- Query tests by role and name (`getByRole`), not by CSS class or test id.
- Unit tests sit next to the code (`*.test.tsx`), and Playwright specs go in `e2e/`.
