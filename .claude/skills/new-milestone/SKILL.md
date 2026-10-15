---
name: new-milestone
description: Implement a roadmap milestone end to end, from spec through plan, tests, build and review to a PR. Use for "/new-milestone M<n>" or "implement milestone M<n>".
---

# /new-milestone M<n>

Follow these steps in order. Do not skip one.

1. **Branch.** `git switch main && git pull`, then `git switch -c feat/m<n>-<short-name>`.
2. **Read the spec.** Read the milestone in `docs/ROADMAP.md` and `docs/specs/M<n>/spec.md`. If spec.md is missing, write it first (1–3 pages: interfaces, files touched, out of scope, end-to-end verification) and stop for the user to confirm it.
3. **Plan.** Write `docs/specs/M<n>/plan.md` (approach, files, risks) and `docs/specs/M<n>/tasks.md`. In tasks.md, list one checkbox per small, testable task and map every exit criterion to a task. Commit with `docs: plan M<n>`.
4. **Build test-first.** For each task, write the failing test, make it pass, tick the box in tasks.md, and make a Conventional Commit. Stay inside the spec's scope.
5. **Gate.** Run `make check`, plus `make e2e` if the UI changed. Repeat until both are green. Never skip, weaken or delete a test to get there.
6. **Review.** Run the `spec-reviewer` subagent with the milestone id. Also run `security-reviewer` if the runner, bootstrap, subprocesses, paths or CI changed, and `a11y-reviewer` if `frontend/src` changed.
7. **Fix gaps.** Fix only the gaps the reviewers report, then repeat steps 5–6 until every verdict is PASS.
8. **PR.** `git push -u origin <branch>`, then `gh pr create`. Use a Conventional Commits title (`feat: M<n> <name>`) and fill in `.github/pull_request_template.md`: summary, `Milestone: M<n>`, and test evidence (the commands run, plus screenshots for UI). Stop there, because the user merges.
