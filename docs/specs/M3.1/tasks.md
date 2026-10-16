# M3.1 — tasks

One Conventional Commit per task. The exit criteria come from [ROADMAP](../../ROADMAP.md#m31--m3-follow-ups).

- [x] T1 `fix(backend)`: project files are opened through directory fds with `O_NOFOLLOW`. A race test swaps the dir for a symlink after opening it (#10). The M3 spec's accepted-risk note is updated.
- [ ] T2 `ci`: every action is pinned by SHA, `dependabot.yml` is added, and `test_workflow_pins.py` enforces the pins (#9).
- [ ] T3 `chore(frontend)`: measure Monaco, cut any unused import, and add `npm run size` with gzip budgets wired into `make test` (#11).
- [ ] T4 `fix(frontend)`: the live save status says only saved or not saved, with a visual-only "Saving…" indicator and `aria-busy` kept (#12).
- [ ] T5 `test`: `make check` and `make e2e` (3 runs) pass, and the reviewers return PASS.
