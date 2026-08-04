from __future__ import annotations

import pytest

from corrections import (
    Correction,
    CorrectionKind,
    CorrectionSession,
    CorrectionStatus,
    TableCell,
)
from public_document import Evidence, GuidedAnswers, build_policy_plan_draft


def _draft():
    answers = GuidedAnswers(
        title="계획",
        issuing_organization="기관",
        audience="시민",
        purpose="목적",
        background="배경",
        current_state="현황",
        objectives="목표",
        actions="조치",
        owners="담당",
        schedule="일정",
        resources="자원",
        risks="위험",
        controls="관리",
        outcomes="성과",
        follow_up="후속",
        contact="담당팀",
        date="2026-05-20",
    )
    evidence = Evidence("ev-1", "자료", "p.1", "현황")
    return build_policy_plan_draft(answers, (evidence,))


def test_preview_and_apply_allowlisted_corrections() -> None:
    session = CorrectionSession(_draft(), (TableCell("tbl-1", 0, 0, "기존 셀"),))
    corrections = (
        Correction(CorrectionKind.TITLE_REPLACEMENT, "title", "수정 계획"),
        Correction(CorrectionKind.PARAGRAPH_REPLACEMENT, "p-05", "수정 현황"),
        Correction(CorrectionKind.PARAGRAPH_APPEND, "p-05", " 추가 설명"),
        Correction(CorrectionKind.PARAGRAPH_PRESET, "p-05", "emphasis"),
        Correction(CorrectionKind.TABLE_CELL_REPLACEMENT, "tbl-1:0:0", "수정 셀"),
    )

    preview = session.preview(corrections)
    assert preview.status is CorrectionStatus.PROPOSED
    assert preview.accepted == corrections
    assert session.revision == 0

    result = session.apply(preview)

    assert result.status is CorrectionStatus.APPLIED
    assert session.revision == 1
    assert session.draft.title == "수정 계획"
    assert session.draft.sections[1].paragraphs[0].text == "수정 현황 추가 설명"
    assert session.draft.sections[1].paragraphs[0].preset == "emphasis"
    assert session.table_cells[0].text == "수정 셀"


def test_mixed_corrections_partially_apply_and_rejected_operation_keeps_revision() -> None:
    session = CorrectionSession(_draft())
    mixed = session.preview(
        (
            Correction(CorrectionKind.PARAGRAPH_REPLACEMENT, "p-05", "검토 문장"),
            Correction(CorrectionKind.PARAGRAPH_REPLACEMENT, "missing", "무시"),
            Correction(CorrectionKind.PARAGRAPH_PRESET, "p-05", "없는 프리셋"),
        )
    )

    result = session.apply(mixed)

    assert result.status is CorrectionStatus.PARTIALLY_APPLIED
    assert len(result.rejected) == 2
    assert session.revision == 1
    current = session.draft.sections[1].paragraphs[0]
    assert current.text == "검토 문장"

    rejected = session.apply(
        session.preview((Correction(CorrectionKind.TITLE_REPLACEMENT, "unknown", ""),))
    )
    assert rejected.status is CorrectionStatus.REJECTED
    assert rejected.revision == 1
    assert session.revision == 1
    assert session.draft.title == "계획"


def test_undo_restores_last_applied_revision_and_preview_can_remove_patch() -> None:
    session = CorrectionSession(_draft())
    preview = session.preview(
        (
            Correction(CorrectionKind.TITLE_REPLACEMENT, "title", "새 제목"),
            Correction(CorrectionKind.PARAGRAPH_REPLACEMENT, "p-05", "새 문장"),
        )
    )
    trimmed = preview.remove(0)
    session.apply(trimmed)

    assert session.draft.title == "계획"
    assert session.draft.sections[1].paragraphs[0].text == "새 문장"
    assert session.undo() is True
    assert session.revision == 0
    assert session.draft.title == "계획"
    assert session.draft.sections[1].paragraphs[0].text == "배경"
    assert session.undo() is False


def test_invalid_correction_kind_is_rejected_without_mutating_preview_source() -> None:
    session = CorrectionSession(_draft())

    with pytest.raises(ValueError, match="allowlisted correction kind"):
        Correction("raw-xml", "p-05", "bad")

    assert session.revision == 0
