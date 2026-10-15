# M1 — Internal model + HCL engine: spec

## Context

ROADMAP §M1: the Pydantic model, the generated JSON Schema, a deterministic generator and a parser with opaque `customHcl`. Fixtures use RG, VNet and NSG. This is the core of ADR-0002: `project.json` is the source of truth, and HCL is a derived view that can also be edited. M1 is backend-only, a library with no UI and no API routes.

## Interfaces (`backend/app/`)

**`app/model.py`: Pydantic v2 models**, camelCase JSON aliases, `extra="forbid"`:
- `Project`
  - `schemaVersion: Literal[1]`
  - `meta{name, created, lowdevopsVersion}`
  - `subscription{id, tenantId, location}`
  - `naming{workload, env, region, pattern}`
  - `tags: dict[str, str]`
  - `resources: list[Resource]`
  - `customHcl: list[CustomHcl]`
  - `waivers: list[Waiver]`
- `Resource`
  - `id`: pattern `^[a-z][a-z0-9_]{0,62}$`, unique within the project
  - `catalogRef`: pattern `^avm-[a-z0-9-]+@\d+\.\d+\.\d+$`, an exact pin
  - `parent: str | None`
  - `inputs: dict[str, JsonValue]`
  - `refs: list[Ref{input, to, output}]`
  - `layout: {x, y} | None`
- `CustomHcl{id, hcl}`
- `Waiver{findingId, resource, reason, by, at}`
- Cross-field validators reject:
  - a duplicate id
  - a `parent` or `refs.to` that doesn't point at an existing resource
  - a ref to the resource itself
  - an input set both literally and by a ref
  - an input or ref input named after a module meta-argument (`source`, `version`, `count`, `for_each`, `depends_on`, `providers`, `lifecycle`)
  - a non-finite number (NaN or Infinity) anywhere in `inputs`
- The fields mirror `docs/ARCHITECTURE.md`. `JsonValue` is a recursive JSON value.

**`app/schema.py`:** `project_json_schema() -> dict` (Pydantic `model_json_schema`, by alias). The output is committed as `backend/schema/project.schema.json`, which `make schema` regenerates. A test fails if the committed file drifts from the generated one.

**`app/hcl/generate.py`: `generate(project: Project) -> str`**, the content of one `main.tf`:
1. A fixed header:
   - `terraform { required_version = ">= 1.11, < 2.0"; required_providers { azapi = { source = "Azure/azapi", version = "~> 2.12" } } }`
   - `provider "azapi" {}`
2. One `module "<id>"` block per resource, in model order:
   - `source = "Azure/<avm-name>/azurerm"` and `version = "<x.y.z>"`, both taken from `catalogRef`.
   - Then the inputs and refs merged and sorted by key. Literals render as HCL. A ref renders as `module.<to>.<output>`.
   - `=` signs are aligned exactly as `terraform fmt` does. CI checks this with `terraform fmt -check`.
3. Each `customHcl` entry, verbatim, in model order.

Sections are separated by one blank line, and the file ends with exactly one `\n`. The output is a pure function of the model. `parent`, `layout`, `tags`, `naming`, `meta`, `subscription` and `waivers` are not emitted.

**`app/hcl/parse.py`: `parse(hcl: str, previous: Project) -> Project`** (raises `HclParseError(message, line)`):
1. A small top-level block splitter (aware of strings, heredocs and comments) cuts the file into top-level blocks with their exact source text. `python-hcl2` (ADR-0001) parses each block's body.
2. The canonical header block is recognized and dropped.
3. A `module` block is **mapped** to a `Resource` when all of these hold:
   - its source matches `^Azure/(avm-[a-z0-9-]+)/azurerm$` with an exact semver `version`
   - its label matches the id pattern
   - every attribute is either a literal (string, number, bool, null, or a list or object of literals) or a bare `module.<id>.<output>` reference to another mapped resource
   - heredocs and expression object keys don't count as literals
   - the block has no comment inside it, directly above it or trailing it, so a comment is never lost
4. **Every other block becomes a `CustomHcl` entry with its source text kept byte for byte**: `resource`, `locals`, `data`, `output`, comments between blocks, and modules with expressions, interpolation, functions, `var.` or `count`. Ids are reused from `previous` when the text matches, and otherwise numbered `custom_<n>`.
5. Fields HCL doesn't carry (`meta`, `subscription`, `naming`, `tags`, `waivers`, and each resource's `parent` and `layout`, matched by id) come from `previous`. Resources not in `previous` get `parent=None` and `layout=None`.
6. On a syntax error, it raises and never returns a partial model (ARCHITECTURE sync rule 3).

**Round-trip contract:** `parse(generate(m), previous=m) == m` for every valid fixture.

## Files touched

- `backend/app/model.py`, `backend/app/schema.py`, `backend/app/hcl/{__init__,generate,parse,blocks}.py`
- `backend/schema/project.schema.json`
- `backend/pyproject.toml` and `uv.lock` (adds `python-hcl2`)
- **Valid fixtures**, each in `backend/tests/fixtures/valid/<name>/` with `project.json` plus the expected `main.tf`:
  - `rg`
  - `rg-vnet`: VNet `parent_id` ← `rg1.resource_id`
  - `rg-vnet-nsg`
  - `custom-hcl`: RG plus a hand-formatted `resource "azapi_resource"`, a `locals` block with comments, and a module using `var.`
- **Invalid fixtures:** `backend/tests/fixtures/invalid/*.json`, one rule broken in each: bad id, duplicate id, dangling ref, dangling parent, unpinned `catalogRef`, unknown field, wrong `schemaVersion`.
- **Tests:** `backend/tests/test_{model,schema,generate,parse,roundtrip}.py`
- **Makefile:** adds a `schema` target.
- **CI:** a new `terraform-validate` job in `.github/workflows/ci.yml`. For each `backend/tests/fixtures/valid/*/main.tf`, it runs `terraform fmt -check`, then `terraform init -backend=false`, then `terraform validate`, using the pinned Terraform 1.16.6.

## Exit criteria → proof

| Criterion | Proof |
| --- | --- |
| Every fixture validates, and invalid ones are rejected | `test_model.py` (parametrized over both dirs). Every invalid fixture must fail for its stated reason. |
| Byte-for-byte snapshots | `test_generate.py`: `generate(load(project.json)) == main.tf` |
| Round-trip | `test_roundtrip.py`: `parse(generate(m), m) == m`, for every valid fixture |
| Custom HCL survives | `test_parse.py`: every custom block's text in `custom-hcl/main.tf` appears unchanged in `generate(parse(text, m))`, and the whole file is byte-identical |
| `terraform validate` | The `terraform-validate` CI job |

Also covered: the parser leaves the model unchanged on a syntax error, and the schema has not drifted.

## Out of scope

- UI and API routes (M3)
- Catalog YAML and validating input names against module schemas (M2). In M1, any `Azure/avm-*` module with a pinned version can be mapped.
- Raw `azurerm`/`azapi` resources as model resources (they stay custom HCL)
- Applying naming or tags (M4)
- Plan and runner (M5)
- TypeScript type generation from the schema (M3)
- Multiple `.tf` files, and `project.json` load/save endpoints

## Risks

- **`terraform validate` can't run locally:** registry.terraform.io is blocked in this sandbox, so validation runs only in CI. I'll check the AVM module interfaces against their GitHub sources:
  - RG 0.4.0: requires `location` and `name`
  - VNet 0.22.3: requires `location` and `parent_id`
  - NSG 0.6.0: requires `location`, `name` and `parent_id`
  - all three use azapi `~> 2.12`
- **Formatting edge cases in the block splitter and python-hcl2** (heredocs, `#`, `//` and `/* */` comments). These get dedicated tests. When the splitter is unsure, it treats the block as custom.
- **Alignment rules:** if hand-aligned `=` drifts from `terraform fmt` on nested objects, CI's `fmt -check` catches it, and the snapshot is regenerated by fixing the generator, never by hand-editing.

## Verification

1. `make check`, with the new tests running under pytest.
2. `make schema && git diff --exit-code`.
3. After pushing, the CI `terraform-validate` job must be green.
4. Then the spec-reviewer subagent and the security-reviewer subagent (the parser takes untrusted input), and a PR titled `feat: M1 internal model and HCL engine`.
