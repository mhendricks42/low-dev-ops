---
name: caf-naming
description: CAF naming and tag rules in LowDevOps: how names are generated and checked, and how to add a resource type's limits. Use when changing naming, nameRules, required tags or the naming tests.
---

# CAF naming and tags

**Where it lives.**

- Backend: `backend/app/guardrails/naming.py` (`caf_name`, `check_names`).
- Frontend: `frontend/src/model/naming.ts` (`cafName`) runs the same algorithm.
- Both are tested against `backend/tests/fixtures/naming-cases.json`. Change one, change both, and regenerate the vectors.

**Algorithm.**

1. Fill `project.naming.pattern` (`{type}`, `{workload}`, `{env}`, `{region}`). `{type}` is the entry's `cafAbbreviation`, except `func` for `avm-res-web-site` with `kind: functionapp`.
2. Lowercase if `nameRules.lowercase`.
3. Drop characters outside `nameRules.chars`, which is why storage accounts lose their hyphens. Collapse runs of `-_.` and strip them from both ends.
4. If the name is longer than `max`, trim `{workload}` first so env and region survive, then hard-truncate.

**Checks.** `LDO_NAME_LENGTH` and `LDO_NAME_CHARS` are high: Azure would reject the name. `LDO_NAME_PATTERN` is low: the name is valid but off the project pattern.

**Add a resource type.** Every catalog entry with a `fill: name` input needs `nameRules: { min, max, chars, lowercase? }`, taken from Microsoft's "Naming rules and restrictions for Azure resources" page. Then add vectors for it to `naming-cases.json`.

**Tags.**

- `project.requiredTags` defaults to `["env", "owner"]` (CAF minimum).
- The generator merges project `tags` under each module's own (the resource wins). The parser drops values equal to the project's.
- Each missing tag is its own medium finding, `LDO_TAG_MISSING:<key>`.
