"""Required tags: every resource must end up with each of project.required_tags (M4)."""

from app.guardrails.findings import Finding
from app.model import Project


def check_tags(project: Project) -> list[Finding]:
    found: list[Finding] = []
    for r in project.resources:
        own = r.inputs.get("tags")
        # The generator merges project tags under the resource's own (M4 spec, Tags).
        effective = {**project.tags, **(own if isinstance(own, dict) else {})}
        found += [
            Finding(
                id=f"LDO_TAG_MISSING:{key}",  # one finding (and waiver) per tag
                resource=r.id,
                severity="medium",
                source="tags",
                message=f"missing required tag '{key}'",
            )
            for key in project.required_tags
            if not effective.get(key)
        ]
    return found
