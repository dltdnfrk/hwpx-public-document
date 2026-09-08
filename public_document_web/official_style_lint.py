from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from .official_rules_skeleton import (
    has_attachment_label,
    has_attachments,
    has_end_mark,
    has_sender_name,
    highest_precedence_rules,
    is_internal_approval,
)
from .paths import RESOURCES

LINT_PATH = RESOURCES / "Rules" / "official-style-lint-1.0.0.json"


class LintReport(TypedDict):
    dryRun: bool
    findings: list[dict[str, Any]]


def load_lint_rules(path: Path | None = None) -> list[dict[str, Any]]:
    payload = json.loads((path or LINT_PATH).read_text(encoding="utf-8"))
    return list(payload.get("rules") or [])


def dry_run_lint(
    project: dict[str, Any],
    catalog: dict[str, Any] | None = None,
    path: Path | None = None,
) -> LintReport:
    findings: list[dict[str, Any]] = []
    elements = list(project.get("elements") or [])
    title_rule = None
    fields = {"endMark", "attachment", "senderName", "title"}
    if catalog is not None:
        binding = project.get("templateBinding") or {}
        applied = highest_precedence_rules(catalog, binding.get("templateID"))
        fields = {rule.get("field") for rule in applied}
        for rule in applied:
            if rule.get("field") == "title":
                title_rule = rule
                break
    for rule in load_lint_rules(path):
        kind = rule.get("kind")
        hit = False
        if kind == "endMark" and "endMark" in fields:
            hit = not has_end_mark(elements)
        elif kind == "attachment" and "attachment" in fields:
            hit = has_attachments(project) and not has_attachment_label(elements)
        elif kind == "senderName" and "senderName" in fields:
            hit = not is_internal_approval(elements) and not has_sender_name(elements)
        elif kind == "titleLock" and "title" in fields:
            hit = bool(title_rule) and project.get("title") != title_rule.get("requiredValue")
        if hit:
            findings.append({
                "ruleID": rule.get("id"),
                "citation": rule.get("citation"),
                "message": rule.get("message"),
                "dryRun": True,
            })
    return {"dryRun": True, "findings": findings}


def apply_lint(
    project: dict[str, Any],
    catalog: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    report = dry_run_lint(project, catalog)
    locked = [item for item in report["findings"] if item.get("ruleID") == "lint-title-lock"]
    if locked:
        return project, {
            "dryRun": False,
            "applied": False,
            "findings": locked,
            "message": "공식 제목 덮어쓰기를 되돌리지 않습니다.",
        }
    return project, {
        "dryRun": False,
        "applied": False,
        "findings": report["findings"],
        "message": "린트 적용은 명시적 교정 경로가 아닙니다. dry_run 결과만 남깁니다.",
    }
