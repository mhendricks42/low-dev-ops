# M3.1 — implementation plan

Spec: [spec.md](spec.md). Checklist: [tasks.md](tasks.md).

## Approach

Each issue is independent, so each is one test-first commit.

- **#10 symlink race (backend).**
  - Rewrite `projects.py` around a small context manager, `_open_project_dir(name, create)`, that yields a directory fd opened with `O_NOFOLLOW` relative to the workspace root fd.
  - `_write_atomic(dir_fd, filename, text)` and the read in `get_project` take that fd.
  - The race test calls the context manager, renames the directory, puts a symlink in its place, then writes through the fd.
- **#9 pins (CI).**
  - Write `test_workflow_pins.py` first, using PyYAML or a regex if YAML isn't a dependency. It should fail on today's workflows.
  - Resolve the SHAs with `git ls-remote`, rewrite the `uses:` lines and add `dependabot.yml`.
- **#11 budget (frontend).**
  - Run `rollup-plugin-visualizer` once via `npx`.
  - `scripts/check-size.mjs` uses `node:zlib` `gzipSync`, with no new dependency.
  - The `npm run size` script builds, then checks.
  - `make test` runs the size check after vitest.
- **#12 status (frontend).**
  - Add a `saving` boolean to the store. `saveStatus` no longer takes "Saving…".
  - `App.tsx` renders `<span aria-hidden="true" className="app-saving">Saving…</span>` while `saving` is true.
  - Unit tests are written first.

## Risks

- The `git ls-remote` route goes through the proxy, which should work. If it fails, the GitHub API is the fallback.
- `make test` gets slower by one `vite build` (about 10 s). That is accepted, because the budget must run in the PR gate.
