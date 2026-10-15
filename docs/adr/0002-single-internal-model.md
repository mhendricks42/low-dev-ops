# 0002. A single internal model is the source of truth

- **Status:** Accepted (2026-10-15)

## Context

Users must be able to do everything in the GUI, while experts can edit HCL. A wizard, a canvas and an HCL editor that each kept their own state would drift apart, and two-way sync with free-form HCL is the project's biggest technical risk.

## Decision

- Each project is one `project.json` on disk, validated by a JSON Schema generated from Pydantic. There is no database.
- The wizard, canvas and HCL editor are views of that model. Generated `.tf` files are derived and are never the source.
- The generator is deterministic and its output is canonical (snapshot-tested).
- HCL edits are parsed on save. Blocks that map to catalog entries become model resources. Anything else becomes an opaque `customHcl` entry: kept verbatim, shown on the canvas, view-only in the wizard. If parsing fails, the model is left unchanged.
- Canvas edges are typed references (`refs`) that the catalog allows. Containment is a `parent` field.

## Consequences

- Round-trip tests (`parse(generate(m)) == m`) on every catalog entry become a required CI gate.
- Saving HCL reformats mapped blocks. Experts who want their own formatting keep it only inside custom HCL.
- Custom HCL can reference model resources, but the GUI cannot check those references. Plan and `terraform validate` catch errors.
- Projects are plain files, so committing them to Git works without any export feature.
