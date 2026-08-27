from __future__ import annotations

from typing import Any


KNOWN_FIELDS = ("title", "endMark", "attachment", "senderName")


def highest_precedence_rules(catalog: dict[str, Any], template_id: Any) -> list[dict[str, Any]]:
    selected = {}
    for entry in catalog.get("entries") or []:
        if entry.get("templateID") != template_id:
            continue
        for rule in entry.get("officialRules") or []:
            field = rule.get("field")
            if field not in KNOWN_FIELDS:
                continue
            current = selected.get(field)
            if current is None or int(rule.get("precedence") or 0) > int(current.get("precedence") or 0):
                selected[field] = rule
    return [selected[field] for field in KNOWN_FIELDS if field in selected]


def is_title_element(element: dict[str, Any]) -> bool:
    return element.get("styleID") == "style-title" or element.get("elementID") == "element-title"


def has_end_mark(elements: list) -> bool:
    for element in elements:
        text = str(element.get("text") or "").strip()
        if element.get("styleID") == "style-end-mark" or text == "끝" or text.endswith(" 끝"):
            return True
    return False


def has_attachments(project: dict[str, Any]) -> bool:
    if project.get("assets"):
        return True
    for element in project.get("elements") or []:
        if element.get("kind") == "attachment" or element.get("styleID") == "style-attachment":
            return True
    return False


def has_attachment_label(elements: list) -> bool:
    for element in elements:
        text = str(element.get("text") or "").strip()
        if element.get("styleID") == "style-attachment" or text == "붙임" or text.startswith("붙임"):
            return True
    return False


def is_internal_approval(elements: list) -> bool:
    for element in elements:
        text = str(element.get("text") or "")
        if element.get("styleID") == "style-internal-approval" or "내부결재" in text:
            return True
    return False


def has_sender_name(elements: list) -> bool:
    for element in elements:
        text = str(element.get("text") or "").strip()
        if element.get("styleID") == "style-sender-name" or text == "발신명의" or text.startswith("발신명의"):
            return True
    return False


def insert_marker(elements: list, element_id: str, text: str, style_id: str) -> list:
    order = max([int(element.get("order") or 0) for element in elements] or [-1]) + 1
    added = {
        "elementID": element_id,
        "kind": "paragraph",
        "order": order,
        "text": text,
        "contentHTML": text,
        "inlineIDs": [],
        "styleID": style_id,
        "evidenceIDs": [],
    }
    return list(elements) + [added]


def apply_title(project: dict[str, Any], rule: dict[str, Any]):
    required = rule["requiredValue"]
    elements = list(project.get("elements") or [])
    title_elements = [element for element in elements if is_title_element(element)]
    submitted = project.get("title") if project.get("title") != required else next(
        (element.get("text") for element in title_elements if element.get("text") != required),
        None,
    )
    if submitted is None:
        return None
    updated = []
    for element in elements:
        if is_title_element(element) and element.get("text") != required:
            changed = dict(element)
            changed["text"] = required
            updated.append(changed)
        else:
            updated.append(element)
    governed = dict(project)
    governed["title"] = required
    governed["elements"] = updated
    conflict = {
        "field": "title",
        "submittedValue": submitted,
        "requiredValue": required,
        "precedence": rule.get("precedence"),
        "source": rule.get("source"),
        "warning": (
            "공식 규칙 충돌: 제출 제목 '{0}' 대신 공식 규칙"
            "(우선순위 {1})의 필수 제목을 적용했습니다: '{2}'."
        ).format(submitted, rule.get("precedence"), required),
    }
    return governed, conflict


def apply_skeleton(project: dict[str, Any], rule: dict[str, Any]):
    field = rule.get("field")
    required = rule["requiredValue"]
    elements = list(project.get("elements") or [])
    if field == "endMark":
        if has_end_mark(elements):
            return None
        elements = insert_marker(elements, "element-end-mark", required, "style-end-mark")
    elif field == "attachment":
        if not has_attachments(project) or has_attachment_label(elements):
            return None
        elements = insert_marker(elements, "element-attachment", required, "style-attachment")
    elif field == "senderName":
        if is_internal_approval(elements) or has_sender_name(elements):
            return None
        elements = insert_marker(elements, "element-sender-name", required, "style-sender-name")
    else:
        return None
    governed = dict(project)
    governed["elements"] = elements
    conflict = {
        "field": field,
        "submittedValue": "",
        "requiredValue": required,
        "precedence": rule.get("precedence"),
        "source": rule.get("source"),
        "warning": (
            "공식 규칙 충돌: 제출 본문에 「{0}」가 없어 공식 규칙"
            "(우선순위 {1})의 필수 표기를 적용했습니다: '{0}'."
        ).format(required, rule.get("precedence")),
    }
    return governed, conflict
