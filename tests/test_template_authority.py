from __future__ import annotations

import zipfile
from pathlib import Path

from public_document import (
    CurrentOfficialRule,
    Evidence,
    GuidedAnswers,
    InstitutionTemplate,
    TemplateOverride,
    TemplateRegistry,
    build_policy_plan_draft,
    export_hwpx,
)


def _answers() -> GuidedAnswers:
    return GuidedAnswers(
        title="기본 계획",
        issuing_organization="서울특별시 안전총괄과",
        audience="시민",
        purpose="보호 조치를 시행한다.",
        background="추진 배경이다.",
        current_state="25곳에서 점검한다.",
        objectives="접근성을 높인다.",
        actions="점검을 시행한다.",
        owners="안전총괄과",
        schedule="2026년 6월",
        resources="기존 예산",
        risks="연락 두절",
        controls="방문 확인",
        outcomes="운영 상태를 점검한다.",
        follow_up="결과를 반영한다.",
        contact="재난대응팀",
        date="2026-05-20",
    )


def test_current_official_rule_wins_and_template_conflict_is_warning(tmp_path: Path) -> None:
    template = InstitutionTemplate(
        template_id="seoul-plan-v2",
        institution="서울특별시 안전총괄과",
        overrides=(
            TemplateOverride("title", "폭염 취약계층 보호 시행계획"),
            TemplateOverride("purpose", "시민 보호를 위한 기관 공동 대응을 시행한다."),
        ),
    )
    registry = TemplateRegistry((template,))
    rules = (
        CurrentOfficialRule(
            field="title",
            required_value="폭염 취약계층 보호 계획",
            source="2026년 공문서 작성 규정 제4조",
        ),
    )

    draft = build_policy_plan_draft(
        _answers(),
        (Evidence("ev-1", "점검자료", "p.1", "25곳에서 점검한다."),),
        template_registry=registry,
        current_rules=rules,
    )

    assert draft.title == "폭염 취약계층 보호 계획"
    assert draft.sections[1].paragraphs[1].text == "시민 보호를 위한 기관 공동 대응을 시행한다."
    assert len(draft.warnings) == 1
    warning = draft.warnings[0]
    assert warning.field == "title"
    assert warning.template_value == "폭염 취약계층 보호 시행계획"
    assert warning.required_value == "폭염 취약계층 보호 계획"
    assert warning.rule_source == "2026년 공문서 작성 규정 제4조"
    assert draft.validation.status == "reviewable"
    assert draft.validation.warnings == draft.warnings
    output = export_hwpx(draft, tmp_path / "template.hwpx", operation_id="template-warning")
    with zipfile.ZipFile(output) as package:
        assert "[경고]".encode() in package.read("Contents/section0.xml")
