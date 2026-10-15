# LowDevOps: Claude Code Kickoff Playbook

Oct 15, 2026 · @matt

## Product vision and decisions

LowDevOps is an open-source, local-first web app that lets citizen developers, novices and experts design, validate, plan and apply Azure infrastructure entirely from a GUI, with full HCL available for anyone who wants it. Claude Code builds it in phase-gated milestones over a 2–4 week MVP.

| Area | Decision from survey |
| --- | --- |
| Users | Citizen devs, novices and experts. 100% of outcomes achievable in the GUI; advanced HCL editing available |
| Experience | Guided wizard for details + visual canvas for the big picture, kept in two-way sync with generated HCL |
| Lifecycle | Full `plan` / `apply` in-app, plus a bootstrap flow that creates the Azure state backend for greenfield deployments |
| Module strategy | Azure Verified Modules (resource + pattern) first; raw `azurerm` / `azapi` resources only where AVM has gaps |
| State and credentials | App-managed Azure Storage backend, running as the signed-in user's own Azure credentials (`az login` / Entra) |
| Guardrails | CAF naming and tagging, policy checks before apply, SecOps scanning (e.g. Checkov / Trivy) |
| MVP catalog | Foundation (RG, VNet, NSG, Key Vault, Storage), Compute/apps (App Service, Container Apps, Functions, AKS), landing-zone patterns |
| Packaging | Local web UI served from a dev container with Terraform, Azure CLI and scanners baked in |
| Stack | Python (FastAPI) backend + React (TypeScript) frontend |
| In-app AI | Not in v1. Natural-language entry point is a stretch goal |
| Repo | Public, open source |
| Polish for v1 | Design system + accessible UI; docs + onboarding |
| Standards | Microsoft Cloud Adoption Framework naming and tag defaults, fully configurable |
| Build style | Phase-gated: Claude builds a milestone, you review the PR, then the next phase starts |
| License | MIT |

## Detailed decisions

Settled in the spec interview (Oct 15, 2026). [ARCHITECTURE.md](ARCHITECTURE.md) and the [ADRs](adr/) give the reasoning.

| Topic | Decision |
| --- | --- |
| Project scope | One project = one Azure subscription and one environment. For dev/prod, clone the project |
| Model store | `project.json` per project in a local workspace folder, validated by a JSON Schema generated from the backend's Pydantic models. Generated `.tf` files sit beside it. No database |
| HCL that can't be mapped back | Kept verbatim as an opaque "custom HCL" node: shown on the canvas, view-only in the wizard, never rewritten by the generator |
| HCL to model sync | Wizard and canvas edits regenerate HCL instantly. HCL edits are parsed on save (or after a debounce). On a parse error the model stays unchanged and the error shows inline. Generator output is canonical, so saving reformats the file |
| Canvas edges | Typed references the catalog declares (e.g. app → Key Vault). Drawing one sets the input, which renders as `module.<id>.<output>`. Containment (RG > VNet > subnet) is drawn as nesting, not as edges |
| Catalog format | `catalog/*.yaml`: an exact AVM version pin, inputs marked basic / advanced / hidden with CAF defaults, allowed references, and an example. CI checks every pin against the registry and runs `terraform validate` on each example. Version upgrades are PRs |
| State bootstrap | One shared backend per subscription: an RG + Storage account (blob versioning, soft delete, no public blob access, Entra-only auth), created via `az` as the signed-in user and recorded in local app settings. Each project gets its own state key |
| Credentials | The dev container mounts the host's `~/.azure`. Terraform runs with `ARM_USE_CLI=true`. The UI shows the signed-in account and subscription, and the user confirms the subscription before each plan. The app never stores secrets |
| Apply | Applies only the saved plan file the user reviewed (`terraform apply plan.tfplan`). Requires typing the project name. Destroys and replacements are highlighted and need a second confirmation. One run per project at a time (state lock) |
| Guardrail failures | Severity tiers: high/critical findings block apply. Medium/low can be waived with a written reason that is stored in `project.json` and shown in plan output |
| Accessibility | WCAG 2.2 AA. axe-core reports zero violations in Playwright. Every canvas action can also be done by keyboard or through an equivalent list view |

## Out of scope (v1)

- Exporting projects to Git with a generated CI/CD pipeline. Projects are plain files, so users can commit them by hand (v0.2 candidate)
- Brownfield: importing existing resources or a drift UI. Plan output still shows drift on resources LowDevOps created
- Several environments or subscriptions in one project
- In-app AI or a natural-language entry point (stretch goal only)
- Clouds other than Azure, and Terraform providers beyond `azurerm` / `azapi`
- Hosted, multi-user or team mode. The app is single-user and runs on localhost
- Auto-apply, scheduled runs, or service-principal credentials

## What works with Claude Code in late 2026

The winning pattern is context engineering plus a check Claude can run: a short CLAUDE.md, a written spec, plan mode, and tests or scripts that pass or fail. Anthropic's own guide names the context window as the main constraint and verification as what lets a session run without you watching ([Claude Code best practices](https://code.claude.com/docs/en/best-practices)).

**Prompting**

- **Let Claude interview you, then write SPEC.md.** The official recipe: describe the idea, ask Claude to interview you with AskUserQuestion, write the spec, then start a fresh session to build it. This playbook is that interview, done up front.
- **Give a pass/fail check in every prompt.** "Run the tests and iterate until green" beats "implement X". For whole sessions, use a `/goal` condition or a Stop hook so Claude cannot stop until the check passes.
- **Be specific.** Name files, reference existing patterns, state what is out of scope, and describe what "done" looks like.
- **Explore → Plan → Implement → Commit.** Use plan mode (`Shift+Tab`, or `claude --permission-mode plan`) for anything multi-file; `Ctrl+G` opens the plan for editing before approval.
- **Fresh sessions per task.** After two failed corrections, `/clear` and re-prompt with what you learned. Name sessions with `/rename` and treat them like branches.

**Repo configuration**

- **CLAUDE.md under \~200 lines**: commands Claude can't guess, non-default style rules, architecture decisions, gotchas. No tutorials or file-by-file descriptions. Subdirectory CLAUDE.md files load only when Claude works there, so `backend/` and `frontend/` get their own ([techsy.io](https://techsy.io/en/blog/claude-md-best-practices)).
- **Skills** (`.claude/skills/<name>/SKILL.md`) hold domain knowledge loaded on demand, e.g. AVM conventions or CAF naming. HashiCorp publishes an `azure-verified-modules` agent skill you can install ([hashicorp/agent-skills](https://claudeskills.info/skills/hashicorp/agent-skills/azure-verified-modules/)).
- **Subagents** (`.claude/agents/*.md`) run in isolated context: use them for research and for an adversarial reviewer that checks the diff against the spec.
- **Hooks** (`.claude/settings.json`) are deterministic: auto-format after edits, block writes to protected paths, run `terraform validate` before stop.
- **MCP servers**: the HashiCorp Terraform MCP server gives Claude live registry docs for providers and modules ([terraform-mcp-server](https://github.com/hashicorp/terraform-mcp-server)); Microsoft Learn docs MCP covers Azure guidance.
- **Permissions**: auto mode is now the default starting mode (v2.1.283+); a classifier blocks risky actions. Add allowlists and `/sandbox` for the rest. Never let the build agent hold real Azure credentials.

**Scaling and review**

- Parallel work: git worktrees (`claude -w`), `claude agents` background sessions, `/batch` to fan a change across 5–30 subagents. Agent teams remain experimental and use roughly 15x the tokens of a single session ([Neil Dave](https://theneildave.substack.com/p/5-claude-code-features-shipped-in)), so skip them for a solo MVP.
- Writer/Reviewer: a fresh session or `/code-review` reviews the diff. Tell the reviewer to report only correctness and requirement gaps, or it will push over-engineering.
- `@claude` in GitHub Actions lets you assign issues and review PRs from GitHub once the repo exists.

## How to orchestrate the session

Use spec-driven "vibe coding": you steer intent and review outcomes, Claude writes the code, and specs plus automated checks replace reading every line. The industry has moved this way through 2026; even Karpathy now frames it as agentic engineering against specs with human oversight ([Towards Data Science](https://towardsdatascience.com/from-vibe-coding-to-spec-driven-development/)).

&#91;embedded content: milestone loop · 6 steps, 1 automated gate, 1 human gate\]

Claude loops on its own until `make check` and the spec-reviewer subagent both pass; your only required step is the PR review. Keep each spec to 1–3 pages with an explicit out-of-scope list.

## Target repo structure

One monorepo with a Python API, a React UI, a curated module catalog, and a `.claude/` folder that is versioned like code. Specs live in `docs/specs/`, one folder per feature, so every session starts from a file rather than chat history.

```text
low-dev-ops/
├── CLAUDE.md                     # <200 lines: stack, commands, hard rules, links to docs
├── .claude/
│   ├── settings.json             # permissions allowlist, hooks, MCP servers
│   ├── agents/
│   │   ├── spec-reviewer.md      # adversarial check of a diff vs its spec
│   │   ├── security-reviewer.md  # secrets, injection, credential handling
│   │   └── a11y-reviewer.md      # WCAG 2.2 AA checks on UI diffs
│   └── skills/
│       ├── avm-catalog/SKILL.md  # how to add an AVM module to the catalog
│       ├── caf-naming/SKILL.md   # CAF naming + tagging rules
│       ├── new-milestone/SKILL.md# /new-milestone: spec -> plan -> build -> PR
│       └── azure-verified-modules/ # installed from hashicorp/agent-skills
├── .devcontainer/
│   ├── devcontainer.json
│   └── Dockerfile                # python, node, terraform, az cli, tflint, checkov, trivy
├── .github/
│   ├── workflows/ci.yml          # lint, type-check, test, e2e, terraform validate
│   ├── workflows/claude.yml      # @claude on issues and PRs
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
├── docs/
│   ├── PRD.md                    # product requirements (from this playbook)
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md                # milestones M0-M6 with exit criteria
│   ├── adr/                      # architecture decision records
│   ├── specs/<milestone>/        # spec.md, plan.md, tasks.md per milestone
│   └── user-guide/
├── backend/                      # FastAPI
│   ├── CLAUDE.md                 # backend-only rules (loads lazily)
│   ├── app/
│   │   ├── api/                  # REST routes
│   │   ├── catalog/              # resource/module schema registry
│   │   ├── hcl/                  # model -> HCL generator, HCL -> model parser
│   │   ├── runner/               # terraform init/plan/apply, streaming logs
│   │   ├── guardrails/           # naming, tags, policy, secops scanners
│   │   └── bootstrap/            # state backend creation
│   └── tests/
├── frontend/                     # React + TypeScript + Vite
│   ├── CLAUDE.md
│   ├── src/
│   │   ├── design-system/        # tokens + accessible components
│   │   ├── canvas/               # React Flow diagram
│   │   ├── wizard/               # schema-driven forms
│   │   └── editor/               # Monaco HCL editor
│   └── e2e/                      # Playwright
├── catalog/                      # YAML: one entry per AVM / raw resource
├── policies/                     # OPA/Conftest + Checkov custom rules
├── examples/                     # sample projects (hub-spoke, web app)
├── LICENSE                       # MIT
├── CONTRIBUTING.md
├── SECURITY.md
└── README.md
```

**Key design choice:** a single internal model (JSON, validated by schema) is the source of truth. The wizard, canvas and HCL editor are three views of it, and the HCL generator is deterministic and snapshot-tested. This is what makes "100% GUI, HCL optional" possible, and it is the main thing to protect in every spec.

## Before the first session (about 30 minutes)

Set up the machine and an empty repo so Claude's first session can build, test and open PRs without stopping to ask.

- [ ] **Install tools:** Claude Code (`npm install -g @anthropic-ai/claude-code`, then `claude update`), `gh` CLI (`gh auth login`), Docker Desktop, VS Code + Dev Containers extension, Azure CLI.
- [ ] **Create the repo:** `gh repo create low-dev-ops --public --clone --license mit --gitignore Python` then `cd low-dev-ops`.
- [ ] **Protect `main`:** require a PR and passing CI before merge (Settings → Branches, or ask Claude to do it with `gh api` in M0).
- [ ] **Add MCP servers (user scope):**
  - `claude mcp add terraform -s user -t stdio -- docker run -i --rm hashicorp/terraform-mcp-server`
  - Microsoft Learn docs MCP for Azure guidance (`claude mcp add --transport http microsoft-learn https://learn.microsoft.com/api/mcp`)
  - Optional: Playwright MCP so Claude can screenshot the UI and compare it against designs.
- [ ] **Install the AVM skill:** `npx skills add hashicorp/agent-skills --skill azure-verified-modules --agent claude-code`.
- [ ] **Install the GitHub app:** inside Claude Code run `/install-github-app` so `@claude` works on issues and PRs.
- [ ] **Create a sandbox Azure subscription** (or resource group) for end-to-end tests of plan/apply and the bootstrap. Keep these credentials out of Claude's session: you run apply tests yourself until M5.
- [ ] **Save this playbook** into the repo as `docs/PRD.md` (export the doc as Markdown) so Claude can read it with `@docs/PRD.md`.
- [ ] **Start Claude in the repo:** `claude`, then run `/rename low-dev-ops-m0`. Use plan mode for every milestone kickoff.

## Prompts to give Claude Code

Run these in order. Each prompt ends with a check Claude must pass and stops at a PR for you to review. Start a fresh session (`/clear`) for each milestone.

**Prompt 1 — Finish the spec (plan mode, \~20 min)**

```text
Read @docs/PRD.md. It describes LowDevOps, an open-source local web app that lets
citizen developers, novices and experts design, validate, plan and apply Azure
infrastructure from a GUI (wizard + canvas), with optional HCL editing.

Interview me with AskUserQuestion about anything the PRD leaves open: the internal
model schema, wizard/canvas/HCL sync rules, bootstrap flow for the state backend,
how plan/apply runs with my az login credentials, guardrail failure UX, catalog
format, and accessibility targets. Skip questions the PRD already answers. Dig
into the hard parts and edge cases.

Then write:
- docs/PRD.md (updated), with an explicit Out of scope section
- docs/ARCHITECTURE.md with a component diagram (mermaid)
- docs/ROADMAP.md with milestones M0-M6, each with exit criteria a script or test can check
- docs/adr/0001-*.md for each major decision (stack, single internal model, AVM-first)
Do not write application code yet. Open a PR titled "docs: product spec and roadmap".
```

**Prompt 2 — M0 foundations (new session)**

```text
Implement milestone M0 from @docs/ROADMAP.md. Plan first, then build:
1. Monorepo layout as in the roadmap: backend/ (FastAPI, uv, ruff, mypy --strict, pytest),
   frontend/ (React + TypeScript + Vite, eslint, vitest, Playwright), catalog/, policies/.
2. .devcontainer with Python, Node, Terraform, Azure CLI, tflint, checkov, trivy pinned.
3. Root CLAUDE.md under 150 lines plus backend/CLAUDE.md and frontend/CLAUDE.md:
   exact commands for lint, test, e2e, run; hard rules; links to docs/. No tutorials.
4. .claude/settings.json: allowlist for the project's lint/test/build commands,
   a PostToolUse hook that formats edited files, and a Stop hook that runs `make check`.
   Deny any `terraform apply` and `az` commands that change resources.
5. .claude/agents/spec-reviewer.md, security-reviewer.md, a11y-reviewer.md.
6. .claude/skills/new-milestone/SKILL.md encoding: read spec -> write
   docs/specs/<id>/plan.md and tasks.md -> implement with tests -> make check ->
   spec-reviewer subagent -> fix gaps -> PR.
7. GitHub Actions CI running make check, CONTRIBUTING.md, SECURITY.md, issue and PR templates.
Done when: `make check` passes locally and in the dev container, and a hello-world
API + UI page render (prove it with a Playwright screenshot). Open a PR.

Git workflow (follow strictly, and encode it in CLAUDE.md and hooks as part of M0):
- Before any edit, run `git switch main && git pull`, then create a branch:
  feat/m0-foundations. Never commit to main.
- Branch names: feat/, fix/, docs/, chore/, ci/ + short kebab-case description.
- Conventional Commits (feat:, fix:, docs:, chore:, ci:, test:, refactor:).
  Small, logical commits. Never use --no-verify or force-push.
- Push the branch and open the PR with `gh pr create`, filling in
  .github/pull_request_template.md (summary, linked milestone, test evidence).
- We squash-merge. I merge, not you.
- Add a "Git workflow" section to CLAUDE.md with these rules (5 lines max).
- Add a PreToolUse hook in .claude/settings.json that blocks `git commit`
  and `git push` when the current branch is main.
- Add deny rules: Bash(git push --force*), Bash(git push origin main*),
  Bash(gh pr merge*).
- Add a ruleset/CI check that requires conventional PR titles.
```

**Prompt 3 — Every later milestone (M1-M6)**

```text
/new-milestone M<n>
```

If the skill isn't ready yet, use the long form:

```text
Implement milestone M<n> from @docs/ROADMAP.md. Write docs/specs/M<n>/spec.md first
(interfaces, files touched, out of scope, end-to-end verification), then plan.md and
tasks.md. Implement test-first. Run make check until green. Then use the
spec-reviewer subagent to compare the diff with the spec, and fix only gaps that
affect correctness or the stated requirements. For UI work, use the a11y-reviewer and
attach Playwright screenshots. Open a PR with the evidence (test output, screenshots).
```

**Prompt 4 — Your review loop on each PR**

```text
I reviewed PR #<n>. Changes needed: <list>. Address them, re-run make check, and push.
Then update CLAUDE.md with any rule that would have prevented these issues
(only if it is not already derivable from the code).
```

**Tips while it runs**

- Press `Esc` to redirect; `Esc Esc` or `/rewind` to undo a wrong turn.
- Use `/btw` for side questions so they don't fill context.
- When a milestone's spec is solid, set `/goal make check passes and every task in tasks.md is ticked` and step away.
- Parallelize only independent work, e.g. a second worktree session (`claude -w`) on the design system while the main session builds the HCL generator.

## MVP roadmap

Seven milestones, each one PR with a testable exit criterion. The deterministic HCL engine comes first because every view depends on it; the first real `apply` against a sandbox subscription is the key week-3 gate.

See [ROADMAP.md](ROADMAP.md) for milestones M0–M6 and their exit criteria.

If week 2 slips, cut AKS and Functions from the catalog before cutting guardrails; landing zones can move to v0.2.

## Risks and open questions

The biggest risk is scope: three synced editors plus in-app apply is a lot for 2–4 weeks. Protect the timeline by keeping the catalog small and treating landing-zone patterns as the last milestone.

| Risk | Mitigation |
| --- | --- |
| Two-way HCL ↔ GUI sync breaks on hand-edited HCL | HCL the model can't represent becomes an opaque "custom HCL" node (view-only in GUI); parse on save, model unchanged on error; round-trip tests on every catalog entry |
| AVM modules have many inputs; forms overwhelm novices | Catalog YAML marks each input as basic / advanced / hidden with CAF defaults |
| `apply` with user credentials causes damage | Plan → guardrails → typed confirmation; destroy needs a second confirmation; no auto-apply |
| Claude invents module inputs or versions | Terraform MCP server + AVM skill; CI runs `terraform validate` on generated examples |
| CLAUDE.md drifts and gets ignored | Keep under 200 lines; prune at each milestone; move rules to hooks where possible |
| Public repo leaks secrets or state | `.gitignore` for state and tfvars, secret scanning in CI, state only in Azure Storage |

**Open questions (resolved)**

- [x] Product name and license: **LowDevOps**, **MIT**.
- [x] Multi-subscription / multi-environment: no. One subscription and one environment per project in v1.
- [x] Git export with a CI pipeline: out of scope for v1. Projects are plain files that can be committed by hand.

## Sources

- [Best practices for Claude Code](https://code.claude.com/docs/en/best-practices) — Anthropic
- [CLAUDE.md best practices](https://techsy.io/en/blog/claude-md-best-practices) — techsy.io, Jun 2026
- [Claude Code features shipped in March 2026](https://theneildave.substack.com/p/5-claude-code-features-shipped-in) — agent teams token cost
- [Spec-driven development in 2026](https://devtoollab.com/blog/spec-driven-development-ai-agents) — DevToolLab
- [Vibe coding vs spec-driven development](https://www.augmentcode.com/guides/vibe-coding-vs-spec-driven-development) — Augment Code
- [Azure Verified Modules](https://azure.github.io/Azure-Verified-Modules/overview/) — Microsoft
- [azure-verified-modules agent skill](https://claudeskills.info/skills/hashicorp/agent-skills/azure-verified-modules/) — HashiCorp
- [Terraform MCP server](https://github.com/hashicorp/terraform-mcp-server) — HashiCorp
