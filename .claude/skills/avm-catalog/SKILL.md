---
name: avm-catalog
description: Add an Azure Verified Module to catalog/ or bump an entry's pin. Use for "add <service> to the catalog" or "bump <module>".
---

# Add or bump a catalog entry

1. **Find the module and pin.** The source is `github.com/Azure/terraform-azurerm-<module>`. Pick the latest release tag:
   `git ls-remote --tags --refs https://github.com/Azure/terraform-azurerm-<module>`. Pins are exact (`1.2.3`), never ranges.
2. **Read the interface at that tag.** Shallow-clone it into the scratchpad (`git clone --depth 1 --branch v<version> …`) and read `variables*.tf` and `outputs*.tf`: required inputs (no `default`), each input's type and `validation` blocks, and the outputs.
3. **Write `catalog/<module>.yaml`** (see `catalog/README.md`):
   - List every required input. Add optional inputs only when a user would set them; everything else stays hidden at the module's default.
   - Basic inputs get a CAF/WAF-aligned `default`, a `fill`, or an allowed ref. Prefer secure defaults: no public network access, TLS 1.2, no shared keys.
   - Always include `enable_telemetry: { tier: hidden, default: false }`.
   - Declare `refs` for inputs that take another entry's output (`parent_id` ← RG `resource_id`, `resource_group_name` ← RG `name`).
   - Set `example.name` to a name the module's name validation accepts.
4. **Test offline.** `make check`. `test_entries.py` and `test_example.py` pick the entry up automatically. For a bump, also update any fixture `project.json` using the old pin and regenerate snapshots (`UPDATE_SNAPSHOTS=1`), never by hand.
5. **Prove it in CI.** The `check-catalog` job must be green: pin resolves, inputs and outputs exist in the module, example validates. Version bumps are their own PR (ADR-0003).
