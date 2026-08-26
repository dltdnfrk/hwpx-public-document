from __future__ import annotations

import uuid
from typing import Any


def enforce_official_rules(project: dict[str, Any], catalog: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = project.get("templateBinding") or {}
    template_id = binding.get("templateID")
    rules = [
        rule
        for entry in catalog.get("entries", [])
        if entry.get("templateID") == template_id
        for rule in entry.get("officialRules") or []
        if rule.get("field") == "title"
    ]
    rules.sort(key=lambda rule: int(rule.get("precedence") or 0), reverse=True)
    if not rules:
        return project, {"appliedRules": [], "conflicts": [], "contentChanged": False}
    rule = rules[0]
    required = rule["requiredValue"]
    elements = list(project.get("elements") or [])
    title_elements = [
        element
        for element in elements
        if element.get("styleID") == "style-title" or element.get("elementID") == "element-title"
    ]
    submitted = project.get("title") if project.get("title") != required else next(
        (element.get("text") for element in title_elements if element.get("text") != required),
        None,
    )
    if submitted is None:
        return project, {"appliedRules": rules, "conflicts": [], "contentChanged": False}

    updated_elements = []
    for element in elements:
        if (
            element.get("styleID") == "style-title" or element.get("elementID") == "element-title"
        ) and element.get("text") != required:
            updated = dict(element)
            updated["text"] = required
            updated_elements.append(updated)
        else:
            updated_elements.append(element)
    created_at = _now()
    revision_id = f"revision-official-rule-{uuid.uuid4()}"
    governed = dict(project)
    governed["title"] = required
    governed["elements"] = updated_elements
    governed["currentRevisionID"] = revision_id
    governed["revisions"] = list(project.get("revisions") or []) + [{
        "revisionID": revision_id,
        "parentRevisionID": project.get("currentRevisionID"),
        "createdAt": created_at,
        "summary": "official-rule-enforced:title",
        "elementIDs": [element.get("elementID") for element in updated_elements],
        "snapshotElements": updated_elements,
    }]
    governed["history"] = list(project.get("history") or []) + [{
        "eventID": f"history-official-rule-{uuid.uuid4()}",
        "kind": "official-rule-enforced:title",
        "revisionID": revision_id,
        "createdAt": created_at,
    }]
    return governed, {
        "appliedRules": rules,
        "conflicts": [{
            "field": "title",
            "submittedValue": submitted,
            "requiredValue": required,
            "precedence": rule.get("precedence"),
            "source": rule.get("source"),
            "warning": (
                f"공식 규칙 충돌: 제출 제목 '{submitted}' 대신 공식 규칙"
                f"(우선순위 {rule.get('precedence')})의 필수 제목을 적용했습니다: '{required}'."
            ),
        }],
        "contentChanged": True,
    }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
