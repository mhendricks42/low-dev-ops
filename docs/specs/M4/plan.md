# M4 — implementation plan

Spec: [spec.md](spec.md). Checklist: [tasks.md](tasks.md).

## Approach

**Backend first, pure checks before scanners.**

- **Naming and tags.** These are plain Python over the model and the catalog, so they are fast and fully unit-tested.
  - `naming.py` exposes `caf_name()` and `check_names()`.
  - The shared vectors live in `backend/tests/fixtures/naming-cases.json`, generated once from `caf_name` and then reviewed by hand against Microsoft's limits.
  - `frontend/src/model/naming.ts` ports the same algorithm, and its vitest reads the same JSON file.
- **Findings and the report.**
  - `findings.py` holds the `Finding` dataclass and the severity order.
  - `run.py` collects findings from each check, maps `module.<id>` addresses to resource ids, applies waivers and computes `apply_allowed`.
- **Scanners.**
  - Each adapter (`conftest.py`, `checkov.py`, `trivy.py`) builds an argument list, runs `subprocess.run(args, capture_output=True, timeout=120, check=False, cwd=tmp)`, and parses the JSON.
  - A shared `_run_tool()` helper turns `FileNotFoundError`, a timeout or bad JSON into `LDO_SCANNER_FAILED`.
  - Scanners only ever see a temp dir holding the generated `main.tf` and an optional `plan.json`.
- **Stub scanners.**
  - `backend/tests/bin/{checkov,trivy,conftest}` are small Python scripts. Each prints the recorded JSON stored next to the fixture (`<fixture>/<tool>.json`), found through a `.fixture` marker file that the test writes into the scan dir. With no marker they print a clean result.
  - A fixture in `conftest.py` puts `tests/bin` first on `PATH`.
- **Real scanners.** `test_real_scanners.py` runs the real binaries, plus `conftest verify` for the Rego unit tests. Each test is skipped when its binary is missing, unless `LOWDEVOPS_REQUIRE_SCANNERS=1` is set (which the dev container image sets), in which case it fails.
- **Tags in the generator.** `generate.py` merges project tags under resource tags for entries that have a `tags` input. `parse.py` drops tag keys whose value equals the project's, so a round trip stays equal. Snapshots are regenerated with `UPDATE_SNAPSHOTS=1` and the diff is reviewed.

**Frontend:**

- `api.ts` gains `check(project)`.
- The reducer gains `addWaiver` and `removeWaiver`.
- `src/checks/Checks.tsx` is built from design-system components (Button, Status, Alert, dialog).
- `App.tsx` adds a fourth tab.

## Risks

- **Real scanner output formats.** Only the dev container has the real scanners, so the stub output is recorded from the documented formats and confirmed by the real-scanner tests in the dev-container CI job.
- **Snapshot churn from the tag merge.** It is limited to fixtures that have project tags.
- **Name limits.** These come from Microsoft's docs. A wrong limit is caught only by a real deploy, so each one cites its source in the YAML comment.
