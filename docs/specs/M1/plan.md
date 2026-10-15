# M1 — implementation plan

Spec: [spec.md](spec.md). Checklist: [tasks.md](tasks.md).

## Approach

**Model (`app/model.py`)**
- Pydantic v2 with `ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")`.
- `JsonValue` comes from `pydantic.JsonValue`, so no custom type is needed.
- A single `model_validator(mode="after")` on `Project` checks for unique ids, that `parent` and `refs.to` exist, that no ref points at its own resource, and that no input is set both literally and by a ref.
- Refs are kept sorted by `input`, the same canonical order the generator and parser use, so equality never depends on list order.
- Fixtures are loaded with `Project.model_validate_json(path.read_text())`.

**Schema (`app/schema.py`)**
- `json.dumps(Project.model_json_schema(by_alias=True), indent=2, sort_keys=True) + "\n"`.
- `python -m app.schema` prints it, and `make schema` writes it to `backend/schema/project.schema.json`.
- A drift test compares the committed file with fresh output.

**Generator (`app/hcl/generate.py`)**
- `render_value()` turns a JSON value into a single line of HCL:
  - strings are quoted and escaped (`\`, `"`, newline/tab, `${`→`$${`, `%{`→`%%{`)
  - ints, floats, bools and `null` render as themselves
  - lists render as `[a, b]`
  - objects render as `{ k = v, "non-ident" = v }`
  - Values stay on one line, so every module body is one alignment group, and `terraform fmt` alignment is simply padding each key to the longest key.
- Module block layout: `source`/`version` (aligned), a blank line, then the sorted inputs and refs (aligned).
- Sections are joined with `"\n\n"`, plus a final `"\n"`.

**Block splitter (`app/hcl/blocks.py`)**
- A character scanner over the top level. It tracks `"…"` strings with escapes and `${ }` nesting, `<<EOF` and `<<-EOF` heredocs, and `#`, `//` and `/* */` comments, and counts braces outside those.
- Each chunk is a block's exact text, including the comment lines directly above it, with surrounding blank lines trimmed.
- An unbalanced brace or an unterminated string, heredoc or comment raises `HclParseError` with the line number.

**Parser (`app/hcl/parse.py`)**
1. Run `hcl2.loads(text)` on the whole file first. A failure becomes `HclParseError(msg, line)`.
2. Split the file into chunks.
3. Drop the chunk that equals the generator's header byte for byte. A user-edited header becomes custom HCL.
4. Each `module "<id>"` chunk is a candidate. Its body comes from `hcl2.loads(chunk)`. Literals are kept, `module.X.Y` strings become refs, and anything else makes the chunk custom. A spike task first confirms how python-hcl2 8.x represents string literals versus expressions.
5. Repeat until stable: demote any candidate whose ref points at a non-candidate.
6. Build the `Project`. Non-HCL fields come from `previous`, and `parent`/`layout` are matched by id. Custom ids are reused when the text matches `previous` exactly, otherwise they become the next free `custom_<n>`.
7. The return value is a model built from scratch, never a mutated `previous`.

**Fixtures**
- `tests/fixtures/valid/{rg,rg-vnet,rg-vnet-nsg,custom-hcl}/project.json` plus `main.tf`.
- `tests/fixtures/invalid/<rule>.json`, with the expected error fragment kept in a dict in `test_model.py`.
- The snapshot test writes `main.tf` when `UPDATE_SNAPSHOTS=1`. It is never edited by hand.

**CI**
- A new `terraform-validate` job using `hashicorp/setup-terraform@v4.0.1` with `terraform_version: 1.16.6`.
- It loops over `backend/tests/fixtures/valid/*/`. Each fixture is copied to a temp dir, then `terraform fmt -check`, `init -backend=false -input=false` and `validate` run there.

## Files

- **New:**
  - `backend/app/{model,schema}.py`
  - `backend/app/hcl/{__init__,blocks,generate,parse}.py`
  - `backend/schema/project.schema.json`
  - `backend/tests/{test_model,test_schema,test_generate,test_blocks,test_parse,test_roundtrip}.py`
  - `backend/tests/conftest.py`, with `load_project()` and the fixture lists
  - `backend/tests/fixtures/**`
  - `docs/specs/M1/{plan,tasks}.md`
- **Edited:**
  - `backend/pyproject.toml` and `uv.lock` (`uv add python-hcl2==8.1.4`)
  - `Makefile` (`schema` target)
  - `.github/workflows/ci.yml` (the `terraform-validate` job)
  - `backend/CLAUDE.md` (add `make schema` and the snapshot-update command)

## Risks

- `terraform validate` runs only in CI, because the registry is blocked here. The first push may need one fix-up round on module input types.
- python-hcl2's representation of values is the main unknown. The spike task settles it before parser work begins. If it can't separate literals from expressions reliably, the parser reads mapped module bodies with the block scanner plus a small literal parser instead.
- Re-generating moves custom blocks after the modules (sync rule 4: saving reformats). This is documented in the spec, and `custom-hcl/main.tf` is already in canonical order.

