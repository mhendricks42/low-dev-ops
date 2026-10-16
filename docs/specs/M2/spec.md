# M2 — Catalog: spec

## Context

ROADMAP §M2: the catalog YAML format, plus entries for the foundation set (RG, VNet, NSG, Key Vault, Storage) and compute (App Service, Container Apps, Functions, AKS). ADR-0003 fixes the shape of an entry: an exact AVM pin, every input marked basic / advanced / hidden, CAF defaults, allowed references and an example. ARCHITECTURE gives the `catalog` component its job: load `catalog/*.yaml` and serve input schemas, defaults and allowed refs to the wizard and canvas (M3).

M2 is backend-only, like M1: a library, its tests, a check script and a CI job. No UI and no API routes.

## Entries (`catalog/<module>.yaml`)

One file per AVM module, named after the module. The model's `catalogRef` (`<module>@<version>`) points at exactly one entry.

| Need                       | File                                           | AVM module                                              | CAF abbreviation               |
| -------------------------- | ---------------------------------------------- | ------------------------------------------------------- | ------------------------------ |
| Resource group             | `avm-res-resources-resourcegroup.yaml`         | `Azure/avm-res-resources-resourcegroup/azurerm`         | `rg`                           |
| Virtual network            | `avm-res-network-virtualnetwork.yaml`          | `Azure/avm-res-network-virtualnetwork/azurerm`          | `vnet`                         |
| Network security group     | `avm-res-network-networksecuritygroup.yaml`    | `Azure/avm-res-network-networksecuritygroup/azurerm`    | `nsg`                          |
| Key Vault                  | `avm-res-keyvault-vault.yaml`                  | `Azure/avm-res-keyvault-vault/azurerm`                  | `kv`                           |
| Storage account            | `avm-res-storage-storageaccount.yaml`          | `Azure/avm-res-storage-storageaccount/azurerm`          | `st`                           |
| App Service plan           | `avm-res-web-serverfarm.yaml`                  | `Azure/avm-res-web-serverfarm/azurerm`                  | `asp`                          |
| App Service and Functions  | `avm-res-web-site.yaml`                        | `Azure/avm-res-web-site/azurerm`                        | `app` (`func` by `kind` is M4) |
| Container Apps environment | `avm-res-app-managedenvironment.yaml`          | `Azure/avm-res-app-managedenvironment/azurerm`          | `cae`                          |
| Container app              | `avm-res-app-containerapp.yaml`                | `Azure/avm-res-app-containerapp/azurerm`                | `ca`                           |
| AKS                        | `avm-res-containerservice-managedcluster.yaml` | `Azure/avm-res-containerservice-managedcluster/azurerm` | `aks`                          |

App Service and Functions share the `web/site` module, so they are one entry with a basic `kind` input (`webapp` or `functionapp`). The RG, VNet and NSG pins stay at the versions the M1 fixtures use (0.4.0, 0.22.3, 0.6.0). The other pins are the latest release when the entry is written. No raw `azurerm`/`azapi` entries are needed, so the `rawReason` field below stays unused in M2.

## Format

```yaml
schemaVersion: 1
module: avm-res-network-virtualnetwork # must equal the file name
version: 0.22.3 # exact semver, no ranges
title: Virtual network
category: foundation # foundation | compute
cafAbbreviation: vnet
inputs:
  name: { tier: basic, fill: name } # filled from naming (M4)
  location: { tier: basic, fill: location } # filled from subscription.location
  address_space:
    {
      tier: basic,
      default: ["10.0.0.0/16"],
      description: "Address ranges in CIDR form.",
    }
  subnets: { tier: advanced }
  enable_telemetry: { tier: hidden, default: false }
refs: # inputs another resource's output may set
  - {
      input: parent_id,
      from: avm-res-resources-resourcegroup,
      output: resource_id,
    }
outputs: [name, resource, resource_id]
example: { name: vnet-example } # optional input overrides for the example
```

- `tier: basic` inputs must have a `default`, a `fill` (`name`, `location` or `tenant_id`, taken from naming or `subscription`), or be set by an allowed ref. That is the "basic inputs have CAF defaults" rule.
- `hidden` inputs must have a `default`, and the wizard never shows them.
- `refs[].input` must be listed under `inputs`. `refs[].from` names another catalog entry and `output` must be in that entry's `outputs`.
- **Example:** each entry builds a small `Project` from itself: its own resource with every basic input at its default or fill value (`example` overrides win, for names a module's validation would reject), plus one resource per ref target so each `refs` line is exercised. `check-catalog` renders it with the M1 generator and validates it. No hand-written example HCL to drift.

## Interfaces (`backend/app/catalog/`)

- `model.py`: Pydantic `CatalogEntry`, `InputSpec{tier, default, fill, description}`, `AllowedRef{input, from, output}`, with `extra="forbid"`. JSON Schema committed as `catalog/catalog.schema.json`, regenerated by `make schema`, with a drift test.
- `load.py`: `load_catalog(path) -> Catalog`. Reads every `catalog/*.yaml` with `yaml.safe_load`, validates each entry, and fails on a file/module name mismatch, a duplicate module, a ref to an unknown entry or output, or a basic/hidden input that breaks the rules above. `Catalog.get(catalog_ref)` looks up `<module>@<version>`.
- `check_project.py`: `check_project(project, catalog) -> list[CatalogIssue]`. Flags a `catalogRef` with no matching entry (or a different version), and a ref the entry does not allow, as errors. An input name the entry does not list is a warning, since unlisted module inputs stay allowed (see Decision). This is the M1 out-of-scope item "validating input names against module schemas".
- `example.py`: `example_project(entry, catalog) -> Project`, as described above.
- `check.py` (`python -m app.catalog.check <catalog-dir>`), wrapped by `scripts/check-catalog`. For each entry, in a temp dir:
  1. Write `generate(example_project(entry))` to `main.tf`.
  2. `terraform init -backend=false` (argument list, explicit timeout). Init resolving `version` exactly proves the pin exists in the registry.
  3. Read the downloaded module's `variables.tf` and `outputs.tf` with python-hcl2. Every catalog input and output must exist in the module, every required module variable must be in the catalog, and every module variable not listed is reported (see Decision).
  4. `terraform validate`.
     It exits non-zero on the first failing entry and names the entry and step.

## Files touched

- `catalog/*.yaml` (10 entries), `catalog/catalog.schema.json`, `catalog/README.md`
- `backend/app/catalog/{__init__,model,load,check_project,example,check}.py`
- `backend/pyproject.toml` and `uv.lock` (adds `pyyaml`)
- `backend/tests/catalog/test_{load,entries,check_project,example,check}.py`, with bad-entry fixtures under `backend/tests/fixtures/catalog-invalid/`. `test_check.py` fakes `terraform` with a stub on `PATH`.
- A test that every M1 valid fixture passes `check_project` against the real catalog.
- `scripts/check-catalog`, a `make catalog` target (not part of `make check`, since it needs network and terraform)
- CI: a `check-catalog` job (pinned setup-terraform, `persist-credentials: false`, like `terraform-validate`)
- `.claude/skills/avm-catalog/SKILL.md`: how to add an entry or bump a pin (the PRD lists it)
- `backend/CLAUDE.md`: the new commands

## Exit criteria → proof

| Criterion                                 | Proof                                                                                                          |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Every YAML passes the catalog schema      | `test_load.py` loads the real catalog; each bad-entry fixture fails for its stated reason                      |
| Every AVM pin exists in the registry      | `check-catalog` step 2, in the CI job                                                                          |
| Every example passes `terraform validate` | `check-catalog` step 4, in the CI job                                                                          |
| Basic inputs have CAF defaults            | `test_entries.py`, parametrized over every entry                                                               |
| Allowed refs point at real outputs        | `test_entries.py` (output listed in the target entry) and `check-catalog` step 3 (output exists in the module) |

## Decision: inputs the catalog doesn't list (decided 2026-10-16: shown only)

ADR-0003 says each entry marks every input. AVM modules have many (AKS has well over 100), and most never need a UI. **Default:** list every required input and every input worth showing; `check-catalog` prints the unlisted module variables as a warning, and the app treats them as hidden with the module's own default. The stricter option fails the check until every variable is listed, which makes the AKS and web/site entries several hundred lines each.

## Out of scope

- API routes and UI for the catalog (M3)
- Applying naming patterns and tags to `name` and `tags` (M4); M2 only records `fill: name` and the abbreviation. Choosing `func` over `app` for Function Apps is part of M4 naming.
- Landing-zone patterns (M6)
- Subnets as their own entries, private endpoints, diagnostic settings
- Running `terraform plan`

## Risks

- **registry.terraform.io is blocked in this sandbox**, as in M1, so `check-catalog` only runs in CI. Module interfaces are read from their GitHub sources while writing entries, and the CI job is the proof.
- **AVM pins move fast.** An old pin is safe, just stale (ADR-0003). Bumping is a separate PR.
- **Required variables with complex types** (AKS node pools, container app templates) need defaults that pass `validate`; the example builder uses the entry's defaults, so those defaults must be complete objects.

## Verification

1. `make check`, with the new tests under pytest.
2. `make schema && git diff --exit-code`.
3. After pushing, the CI `check-catalog` and `terraform-validate` jobs are green.
4. spec-reviewer and security-reviewer (new subprocess calls and CI job), then a PR titled `feat: M2 catalog`.
