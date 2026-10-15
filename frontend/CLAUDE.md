# Frontend (React + TypeScript + Vite)

Node 22. Run commands from `frontend/`, or use the root `make` targets. The dev server proxies `/api` to `127.0.0.1:8000`.

## Commands

| What | Command |
| --- | --- |
| Install | `npm ci` |
| Lint | `npm run lint` (eslint + prettier --check) |
| Format | `npm run format` |
| Typecheck | `npm run typecheck` |
| Unit tests | `npm test` (vitest, jsdom) |
| One test | `npx vitest run src/App.test.tsx` |
| E2E | `npm run e2e` (Playwright; starts API and UI; writes `docs/specs/M0/hello.png`) |
| Run | `npm run dev` |

## Rules

- TypeScript is strict: no `any`, no non-null `!`. Model types are generated from the backend JSON Schema, never hand-written.
- Wizard, canvas and editor all read and write one model store. A view never holds its own copy of the model.
- Accessibility (WCAG 2.2 AA): native elements first, every control labelled, status changes in `role="status"`, and every canvas action reachable from the keyboard list view.
- Query tests by role and name (`getByRole`), not by CSS class or test id.
- Unit tests sit next to the code (`*.test.tsx`), and Playwright specs go in `e2e/`.
