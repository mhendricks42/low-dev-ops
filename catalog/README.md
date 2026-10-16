# Catalog

One YAML entry per AVM module, named after the module (`avm-res-web-site.yaml`). The model's `catalogRef` (`<module>@<version>`) points at exactly one entry. Why AVM and exact pins: [ADR-0003](../docs/adr/0003-avm-first-catalog.md). Format and rules: [M2 spec](../docs/specs/M2/spec.md).

| Field | Meaning |
| --- | --- |
| `module`, `version` | The AVM module and its exact pin. The file name must equal `module`. |
| `title`, `category`, `cafAbbreviation` | What the UI shows, `foundation` or `compute`, and the CAF prefix naming uses (M4). |
| `inputs` | Module inputs worth showing, each `basic`, `advanced` or `hidden`. Basic inputs need a `default`, a `fill` (`name`, `location`, `tenant_id`) or an allowed ref. Hidden inputs need a `default`. |
| `refs` | Inputs another resource's output may set, such as `parent_id` ← the resource group's `resource_id`. |
| `outputs` | Outputs other entries may reference. |
| `example` | Input overrides for the generated example, usually a `name` the module's validation accepts. |

Module inputs not listed stay hidden at the module's own default; `check-catalog` prints them as a warning.

`catalog.schema.json` is generated from `backend/app/catalog/model.py` by `make schema`. Never edit it by hand.

## Checks

- `make test` loads every entry and checks the rules above, offline.
- `make catalog` (CI job `check-catalog`) runs `terraform init` on each entry's generated example, which proves the pin exists, checks every listed input and output against the downloaded module, then runs `terraform validate`. It needs registry.terraform.io.

To add an entry or bump a pin, follow `.claude/skills/avm-catalog/SKILL.md`.
