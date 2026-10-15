# Security policy

## Reporting a vulnerability

Please do **not** open a public issue. Report it privately through [GitHub Security Advisories](https://github.com/mhendricks42/low-dev-ops/security/advisories/new) and include the steps to reproduce and the impact. You can expect an acknowledgement within 5 working days.

## Supported versions

Only the latest release and `main` get security fixes.

## Security model

LowDevOps is a single-user tool that runs on your machine. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#trust-boundaries-and-safety) for the details.

- The API binds to `127.0.0.1` only and has no authentication.
- The app never stores credentials. Terraform and `az` use your own `az login` session (`ARM_USE_CLI=true`).
- Subprocesses run with argument lists, never a shell, and inputs are validated before they reach a path or a command.
- `apply` runs only a reviewed, saved plan, after a typed confirmation.
- Terraform state lives only in your Azure Storage backend and is never written to the repo.

In scope: anything that lets a web page, a crafted `project.json`, HCL or catalog entry run commands, read files outside the workspace, leak credentials, or apply changes that were not reviewed.
