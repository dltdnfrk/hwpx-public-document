from __future__ import annotations

import uuid
from typing import Any

from .official_rules_skeleton import apply_skeleton, apply_title, highest_precedence_rules
from .official_style_lint import dry_run_lint


def enforce_official_rules(project: dict[str, Any], catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = project.get("templateBinding") or {}
    rules = highest_precedence_rules(catalog, binding.get("templateID"))
    governed = dict(project)
    conflicts = []
    changed_fields = []
    for rule in rules:
        field = rule.get("field")
        result = apply_title(governed, rule) if field == "title" else apply_skeleton(governed, rule)
        if result is None:
            continue
        governed, conflict = result
        conflicts.append(conflict)
        changed_fields.append(field)
    style_lint = dry_run_lint(governed, catalog)
    if not changed_fields:
        return governed, {
            "appliedRules": rules,
            "conflicts": [],
            "contentChanged": False,
            "styleLint": style_lint,
        }
    created_at = _now()
    revision_id = "revision-official-rule-{0}".format(uuid.uuid4())
    kind = "official-rule-enforced:{0}".format(",".join(changed_fields))
    elements = list(governed.get("elements") or [])
    governed["currentRevisionID"] = revision_id
    governed["revisions"] = list(project.get("revisions") or []) + [{
        "revisionID": revision_id,
        "parentRevisionID": project.get("currentRevisionID"),
        "createdAt": created_at,
        "summary": kind,
        "elementIDs": [element.get("elementID") for element in elements],
        "snapshotElements": elements,
    }]
    governed["history"] = list(project.get("history") or []) + [{
        "eventID": "history-official-rule-{0}".format(uuid.uuid4()),
        "kind": kind,
        "revisionID": revision_id,
        "createdAt": created_at,
    }]
    return governed, {
        "appliedRules": rules,
        "conflicts": conflicts,
        "contentChanged": True,
        "styleLint": style_lint,
    }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
