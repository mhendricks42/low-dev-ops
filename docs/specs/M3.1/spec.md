# M3.1 — M3 follow-ups: spec

## Context

M3 (PR #8) merged with four follow-ups filed as issues. M3.1 closes them in one PR and adds no features.

| Issue | Problem | Outcome |
| --- | --- | --- |
| #9 | CI actions are referenced by mutable tag | every `uses:` pinned to a commit SHA, enforced by a test |
| #10 | Same-user race between the symlink check and the write | file access through directory fds, so nothing is re-resolved |
| #11 | The Monaco chunk is 2.7 MB minified (692 KB gzipped) | measured, trimmed where possible, and guarded by a size budget |
| #12 | The save status is announced after every typing pause | the live text changes only when the saved or failed state changes |

## 1. Pin CI actions by SHA (#9)

- **Files:** `.github/workflows/ci.yml` and `.github/workflows/pr-title.yml`. There are 11 tag-pinned references across 6 actions: checkout, setup-uv, setup-node, upload-artifact, devcontainers/ci and action-semantic-pull-request.
- **Pinning:** each becomes `owner/action@<40-hex sha> # <tag>`. The SHA comes from `git ls-remote https://github.com/<owner>/<action> refs/tags/<tag>`, using the peeled `^{}` commit for annotated tags.
- **Updates:** a new `.github/dependabot.yml` (ecosystem `github-actions`, weekly) keeps the pins current.
- **Guard:** `backend/tests/test_workflow_pins.py` parses every `.github/workflows/*.yml` and fails on any remote `uses:` not pinned to a 40-hex SHA. Local `./` and `docker://` references are exempt. It runs in `make check`.

## 2. Close the symlink race (#10)

Today `_project_dir()` in `backend/app/api/projects.py` checks paths with `is_symlink()` and `resolve()`, and the write later opens those same paths again. A process running as the same user can swap the directory for a symlink in between.

New flow, built only on directory file descriptors:

1. `root_fd = os.open(workspace.resolve(), O_RDONLY | O_DIRECTORY)`. The workspace root is the user's own configuration, so it is trusted.
2. `os.mkdir(name, dir_fd=root_fd)` for a save, tolerating `FileExistsError`. Then `dir_fd = os.open(name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW, dir_fd=root_fd)`. An `ELOOP` or `ENOTDIR` error becomes the existing 422 `project directory is a symlink`.
3. `_write_atomic(dir_fd, filename, text)` does the whole write relative to `dir_fd`:
   - opens the temp file with `O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW` and mode `0o600`
   - writes and fsyncs it
   - renames it into place with `os.replace(tmp, filename, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)`
   - fsyncs `dir_fd`
   - on failure, unlinks the temp file with `dir_fd`
4. `get_project` opens `project.json` with `O_RDONLY | O_NOFOLLOW` relative to `dir_fd`. A symlinked file gives the existing 422.
5. Every fd is closed in a `finally`.

The `NAME_PATTERN` check stays as the first line of defence. The response shapes and status codes do not change.

**Docs:** the "Accepted risk" bullet in `docs/specs/M3/spec.md` is changed to say M3.1 closed it.

## 3. Monaco chunk budget (#11)

**Finding:** `src/editor/monaco.ts` already imports `monaco-editor/editor`, which is the API-only entry with no feature contributions and no languages except HCL. Nearly all of the 2.7 MB is Monaco's standalone core, which cannot be split further without forking Monaco.

**Work:**

- **Measure:** build once with `rollup-plugin-visualizer`, run through `npx` and not committed. Remove any import that turns out to be reachable but unused.
- **Budget:** `frontend/scripts/check-size.mjs` reads `dist/assets/`, gzips each `.js` file and fails if the Monaco chunk exceeds **750 KB gzipped** or the main `index-*.js` chunk exceeds **80 KB gzipped** (measured: 692 KB and 73 KB). Both limits sit about 10 % above the current measurements.
- **Wiring:** `npm run size` runs `vite build` and then the script. `make check` calls it through the `test` target.

#11 closes as "budgeted, core is irreducible" unless measuring finds a real saving.

## 4. Quieter save status (#12)

Today the header `<Status busy={pending}>{saveStatus}</Status>` (`role="status"`) switches between "Saving…" and "All changes saved" on every debounced save, so a screen reader announces it twice after each pause in typing.

**Change** (`frontend/src/model/store.tsx`, `frontend/src/App.tsx`):

- The live text has two values: "All changes saved" and "Not saved". "Loaded" stays as the text before the first save.
- While a save is in flight, an `aria-hidden` "Saving…" indicator appears next to the status, for sighted users only.
- `aria-busy={pending}` stays on the live status, so assistive tech knows an update is pending. The e2e `saved()` helper keeps working unchanged.
- The save-failure `Alert` and the screen-reader announcements for add, remove and reference changes do not change.

This meets WCAG 4.1.3: the result of a save (saved or failed) is still announced, only the in-progress chatter goes. A check with real NVDA and VoiceOver is left to the user, because this environment cannot run them.

## Files touched

- `.github/workflows/ci.yml`, `.github/workflows/pr-title.yml`, `.github/dependabot.yml` (new)
- `backend/app/api/projects.py`
- `backend/tests/api/test_projects.py`, `backend/tests/test_workflow_pins.py` (new)
- `frontend/src/model/store.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css` (styles for the "Saving…" indicator)
- `frontend/src/model/store.test.tsx`
- `frontend/scripts/check-size.mjs` (new), `frontend/package.json` (the `size` script), `Makefile`
- `docs/ROADMAP.md`, `docs/specs/M3/spec.md`, and `docs/specs/M3.1/{spec,plan,tasks}.md`

## Exit criteria → proof

| Criterion | Proof (fails before the change) |
| --- | --- |
| Every action pinned to a SHA | `test_workflow_pins.py` fails on today's workflows and passes after |
| Race closed | `test_projects.py::test_swap_to_symlink_after_open_stays_in_workspace` opens the dir fd, renames the dir and puts a symlink to an outside dir in its place, then writes. The files land in the renamed original and the outside dir stays empty |
| Monaco budget | `npm run size` passes at the current size. Lowering the budget by 10 % makes it fail; checked once and noted in the PR |
| Quiet status | `store.test.tsx`: two edits with saves between them leave the live text at "All changes saved" and never "Saving…", and `aria-busy` goes true then false. A failing PUT gives "Not saved" and the next success restores the text |
| No regressions | `make e2e`: the M3 suite passes 8/8, three runs in a row, with axe-core and 320 px reflow included |

## Out of scope

- Replacing Monaco, or serving it from anywhere but the local bundle.
- A multi-user or shared-workspace threat model.
- Pinning the dev container base image by digest.
- New UI features.

## Risks

- **`O_NOFOLLOW` and `dir_fd` are POSIX-only.** The app runs in the Linux dev container (PRD), so that is acceptable. `os.supports_dir_fd` is asserted at import so a missing feature fails loudly, not silently.
- **SHA pins go stale.** Dependabot handles that, and the `# <tag>` comment keeps the version readable.
- **The size budget may flake if the build output changes between Vite versions.** The budget has about 10 % headroom, and raising it is a reviewed one-line change.

## Verification

- `make check` exits 0. It now includes the pin test and the size budget.
- `make e2e` passes 8/8, three times in a row.
- spec-reviewer, security-reviewer (paths and CI) and a11y-reviewer (`frontend/src`) all return PASS.
- After the push, every PR check is green, with the workflows running on the SHA-pinned actions.
