from __future__ import annotations

from pathlib import Path

from public_document import (
    Evidence,
    GuidedAnswers,
    build_policy_plan_draft,
    export_hwpx,
    hwpx_content_hash,
    validate_hwpx,
)


def _draft():
    answers = GuidedAnswers(
        title="폭염 취약계층 보호 계획",
        issuing_organization="서울특별시 안전총괄과",
        audience="시민과 자치구 담당자",
        purpose="보호 조치를 시행한다.",
        background="폭염 대응을 강화한다.",
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
    return build_policy_plan_draft(
        answers,
        (Evidence("ev-1", "점검자료", "p.1", "25곳에서 점검한다."),),
    )


def test_repeated_export_has_same_normalized_hash_and_passes_validation(tmp_path: Path) -> None:
    draft = _draft()
    first = export_hwpx(draft, tmp_path / "first.hwpx", operation_id="revision-1")
    second = export_hwpx(draft, first, operation_id="revision-1")

    assert hwpx_content_hash(first) == hwpx_content_hash(second)
    result = validate_hwpx(first, draft)
    assert result.is_valid
    assert result.package_valid
    assert result.schema_profile_valid
    assert result.internal_references_valid
    assert result.metadata_valid
