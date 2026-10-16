# M2 — implementation plan

Spec: [spec.md](spec.md). Checklist: [tasks.md](tasks.md).

## Approach

**Interfaces first.** The registry is blocked in this sandbox, but GitHub is not. Each module is shallow-cloned at its pinned tag and its `variables.tf` / `outputs.tf` read with python-hcl2, so required inputs, outputs and validation rules are known before an entry is written. Pins (latest tag on 2026-10-16):

| Module                          | Pin    | Required inputs                                                            |
| ------------------------------- | ------ | -------------------------------------------------------------------------- |
| resources-resourcegroup         | 0.4.0  | location, name                                                             |
| network-virtualnetwork          | 0.22.3 | location, parent_id                                                        |
| network-networksecuritygroup    | 0.6.0  | location, name, parent_id                                                  |
| keyvault-vault                  | 0.12.0 | location, name, resource_group_name, tenant_id                             |
| storage-storageaccount          | 0.10.0 | location, name, parent_id                                                  |
| web-serverfarm                  | 2.0.8  | location, name, os_type, parent_id                                         |
| web-site                        | 0.24.1 | location, name, parent_id, service_plan_resource_id                        |
| app-managedenvironment          | 0.5.1  | location, name, resource_group_name                                        |
| app-containerapp                | 0.9.0  | container_app_environment_resource_id, name, resource_group_name, template |
| containerservice-managedcluster | 0.8.5  | location, name, parent_id                                                  |

Key Vault, the Container Apps environment and the container app take a resource group _name_, so their refs use the RG's `name` output; the rest take `parent_id` ← `resource_id`.

**Catalog model (`app/catalog/model.py`).** Pydantic v2, camelCase aliases and `extra="forbid"`, like `app/model.py`. Input and output names reuse `NAME_PATTERN` and `RESERVED_NAMES`, so nothing in YAML can inject HCL. `module` matches `^avm-[a-z0-9-]+$` and `version` an exact semver. Per-entry rules (basic/hidden defaults, ref inputs listed) are an `after` validator; cross-entry rules (ref targets and outputs) live in the loader.

**Loader (`app/catalog/load.py`).** `yaml.safe_load` only. Errors carry the file name. `Catalog` is a frozen mapping from module name to entry, with `get(catalog_ref)` that returns `None` for an unknown module or a different version.

**Example builder (`app/catalog/example.py`).** Builds a valid `Project` (fixed meta, subscription, naming). The subject resource gets every basic input at its default or fill value, plus `example` overrides. For each allowed ref (first one per input) it adds the target entry's own example resource, recursively and de-duplicated, ordered so targets come first. Resource ids are `<abbreviation>1`. Fill values: `name` → `example` override or `<abbr>-lowdevops-ex`, `location` → `westeurope`, `tenant_id` → the zero GUID.

**check_project (`app/catalog/check_project.py`).** Returns `CatalogIssue{resource, severity, message}` sorted by resource then message, so callers and tests get a stable list.

**check-catalog (`app/catalog/check.py`).** One temp dir per entry. `subprocess.run([terraform, "-chdir=…", "init", "-backend=false", "-input=false", "-no-color"], timeout=600, check=False)`, then validate the same way. The binary comes from `shutil.which("terraform")`; no shell anywhere. After init, `.terraform/modules/modules.json` gives the subject module's directory and resolved `Version`; that version must equal the pin. The module's `*.tf` are read with python-hcl2 to get variables (with or without `default`) and outputs. Unlisted variables print as warnings. Exit code 1 names the entry and the failing step. `scripts/check-catalog` is a two-line wrapper that runs it from `backend/` against `../catalog`.

**Schema.** `app/schema.py` gains `catalog_json_schema()`; `make schema` writes both files and a drift test covers `catalog/catalog.schema.json`.

**CI.** A `check-catalog` job mirroring `terraform-validate` (pinned setup-terraform SHA, Terraform 1.16.6, `persist-credentials: false`), plus setup-uv to run the script, and `TF_PLUGIN_CACHE_DIR` so ten inits share one provider download.

## Files

- **New:** `catalog/*.yaml` (10), `catalog/catalog.schema.json`, `backend/app/catalog/{__init__,model,load,example,check_project,check}.py`, `backend/tests/catalog/**`, `backend/tests/fixtures/catalog-invalid/**`, `scripts/check-catalog`, `.claude/skills/avm-catalog/SKILL.md`, `docs/specs/M2/{plan,tasks}.md`
- **Edited:** `backend/pyproject.toml` and `uv.lock` (pyyaml, types-pyyaml), `backend/app/schema.py`, `Makefile` (`schema` writes both schemas; new `catalog` target), `.github/workflows/ci.yml`, `catalog/README.md`, `backend/CLAUDE.md`

## Risks

- **Validation only in CI.** `terraform validate` evaluates module variable validations against the example's literal values (name regexes, GUIDs). Names come from `example` overrides that were checked against each module's regex by hand. The first CI run may still need one fix-up round.
- **azurerm provider.** Key Vault and the Container Apps environment need `hashicorp/azurerm`, which the M1 header does not declare. `terraform validate` does not configure providers, so the implicit provider is fine for M2; a `provider "azurerm" { features {} }` block is needed before plan (M5) and is noted as a follow-up.
- **Provider downloads.** azurerm is large; the plugin cache keeps the CI job to one download per provider.
