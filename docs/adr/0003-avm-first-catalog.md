# 0003. Azure Verified Modules first, with exact version pins

- **Status:** Accepted (2026-10-15)

## Context

The catalog decides what users can build. Hand-writing raw `azurerm` resources means re-implementing Microsoft's secure defaults. Azure Verified Modules (AVM) are Microsoft-supported resource and pattern modules with consistent interfaces, but they have many inputs and release often.

## Decision

- Catalog entries wrap AVM resource and pattern modules. Raw `azurerm` / `azapi` resources are used only where AVM has a gap, and the entry records why.
- Each `catalog/*.yaml` pins an exact module version, marks every input basic / advanced / hidden, supplies CAF defaults, declares allowed references (inputs ← outputs), and includes an example.
- `scripts/check-catalog` runs in CI: schema-valid YAML, every pin exists in the registry, and every example passes `terraform validate`.
- Version upgrades are explicit PRs that re-run snapshot and round-trip tests.

## Consequences

- Generated HCL is reproducible, and novices only see basic inputs.
- Someone has to bump pins. An outdated pin is safe, just stale.
- The generator emits `module` blocks, so the plan shows AVM's internal resources. The UI shows the module as one node.
