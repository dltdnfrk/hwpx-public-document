from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

from public_document import (
    BetaDocumentGroup,
    CloudProviderAdapter,
    Evidence,
    GuidedAnswers,
    HWPCompatibilityError,
    HWPExportOutcome,
    HWPUnavailableError,
    ManualDraftResult,
    build_policy_plan_draft,
    export_hwpx,
    complete_manual_draft,
    ProviderKind,
    ProviderRegistry,
    ProviderRequest,
    ProviderUnavailableError,
    validate_draft,
)
from privacy import ConsentRequiredError, ExternalTransmissionGateway, InMemoryConsentStore


def _answers() -> GuidedAnswers:
    return GuidedAnswers(
        title="폭염 취약계층 보호 계획",
        issuing_organization="서울특별시 안전총괄과",
        audience="시민과 자치구 담당자",
        purpose="폭염 취약계층의 건강 피해를 줄이기 위한 보호 조치를 시행한다.",
        background="최근 폭염일수가 늘어 취약계층 보호와 현장 대응을 함께 강화할 필요가 있다.",
        current_state="동주민센터 25곳이 안부 확인과 무더위쉼터 안내를 수행하고 있다.",
        objectives="취약계층 안부 확인을 확대하고 쉼터 접근성을 높인다.",
        actions="주 2회 안부 확인, 쉼터 냉방 점검, 폭염 예보 시 문자 안내를 시행한다.",
        owners="안전총괄과와 25개 동주민센터",
        schedule="2026년 6월부터 9월까지",
        resources="기존 재난관리 예산과 자원봉사 인력을 활용한다.",
        risks="고령 1인 가구의 연락 두절과 쉼터 접근성 편차",
        controls="연락 실패 시 방문 확인하고 자치구별 점검표로 쉼터 상태를 확인한다.",
        outcomes="안부 확인 이행률과 쉼터 운영 상태를 월별로 점검한다.",
        follow_up="9월 말 결과를 취합해 다음 연도 계획에 반영한다.",
        contact="안전총괄과 재난대응팀",
        date="2026-05-20",
    )


def test_policy_planning_flow_builds_reviewable_draft_with_evidence() -> None:
    evidence = Evidence(
        evidence_id="ev-001",
        source_title="2026년 폭염 대응 내부 점검자료",
        locator="p.2, 표 1",
        excerpt="동주민센터 25곳에서 안부 확인과 무더위쉼터 안내를 수행하고 있다.",
    )

    draft = build_policy_plan_draft(_answers(), (evidence,))

    assert draft.title == "폭염 취약계층 보호 계획"
    assert draft.page_count >= 1
    assert draft.critical_omissions == ()
    assert any("25곳" in claim.text for claim in draft.claims)
    assert draft.claims[0].evidence_ids == ("ev-001",)
    assert all(paragraph.evidence_ids for section in draft.sections for paragraph in section.paragraphs)


def test_export_hwpx_is_valid_editable_and_byte_deterministic(tmp_path: Path) -> None:
    evidence = Evidence(
        evidence_id="ev-001",
        source_title="2026년 폭염 대응 내부 점검자료",
        locator="p.2, 표 1",
        excerpt="동주민센터 25곳에서 안부 확인과 무더위쉼터 안내를 수행하고 있다.",
    )
    draft = build_policy_plan_draft(_answers(), (evidence,))
    first = export_hwpx(draft, tmp_path / "draft-1.hwpx", operation_id="op-001")
    second = export_hwpx(draft, first, operation_id="op-001")

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as package:
        names = set(package.namelist())
        assert {"mimetype", "version.xml", "Contents/content.hpf", "Contents/header.xml", "Contents/section0.xml", "Contents/styles.xml"} <= names
        assert package.read("mimetype") == b"application/hwp+zip"
        for name in names - {"mimetype"}:
            ElementTree.fromstring(package.read(name))
        assert "[확인 필요]".encode() not in package.read("Contents/section0.xml")
        assert package.read("Contents/section0.xml").count(b"<hp:p") >= 9


def test_beta_policy_group_is_labeled_and_keeps_review_scope_visible(tmp_path: Path) -> None:
    evidence = Evidence(
        evidence_id="ev-001",
        source_title="2026년 폭염 대응 내부 점검자료",
        locator="p.2, 표 1",
        excerpt="동주민센터 25곳에서 안부 확인과 무더위쉼터 안내를 수행하고 있다.",
    )

    draft = build_policy_plan_draft(_answers(), (evidence,))
    output = export_hwpx(draft, tmp_path / "beta.hwpx", operation_id="op-beta")

    assert draft.beta_group is BetaDocumentGroup.POLICY_PLANNING
    assert draft.beta_label == "베타"
    assert "1차 검토" in draft.quality_notice
    assert draft.sections[0].section_id == "identity"
    with zipfile.ZipFile(output) as package:
        assert "[베타]".encode() in package.read("Contents/section0.xml")


def test_export_validation_reports_complete_checklist_and_grounded_numbers() -> None:
    evidence = Evidence(
        evidence_id="ev-001",
        source_title="2026년 폭염 대응 내부 점검자료",
        locator="p.2, 표 1",
        excerpt="동주민센터 25곳에서 안부 확인과 무더위쉼터 안내를 수행하고 있다.",
    )

    draft = build_policy_plan_draft(_answers(), (evidence,))

    result = validate_draft(draft)

    assert result.required_structure_percent == 100
    assert result.checklist_score == 100
    assert result.critical_omissions == ()
    assert result.unsupported_numeric_claims == ()
    assert result.status == "reviewable"


def test_export_validation_marks_unsupported_numbers_without_inventing_them() -> None:
    answers = _answers()
    answers = GuidedAnswers(**{**answers.__dict__, "current_state": "현재 17곳에서 점검을 수행하고 있다."})

    draft = build_policy_plan_draft(answers, ())

    result = validate_draft(draft)

    assert result.required_structure_percent == 100
    assert result.checklist_score == 100
    assert result.unsupported_numeric_claims == ()
    assert any("17곳" in omission for omission in result.critical_omissions)
    assert result.status == "evidence_blocked"
    assert "[확인 필요]" in draft.sections[3].paragraphs[0].text


def test_export_preserves_evidence_blocked_marker(tmp_path: Path) -> None:
    answers = GuidedAnswers(**{**_answers().__dict__, "current_state": "현재 17곳에서 점검을 수행하고 있다."})
    draft = build_policy_plan_draft(answers, ())

    output = export_hwpx(draft, tmp_path / "blocked.hwpx", operation_id="op-blocked")

    with zipfile.ZipFile(output) as package:
        content = package.read("Contents/section0.xml").decode()
    assert "[확인 필요]" in content


def test_manual_workflow_finishes_without_any_provider(tmp_path: Path) -> None:
    evidence = Evidence(
        evidence_id="ev-001",
        source_title="2026년 폭염 대응 내부 점검자료",
        locator="p.2, 표 1",
        excerpt="동주민센터 25곳에서 안부 확인과 무더위쉼터 안내를 수행하고 있다.",
    )

    result = complete_manual_draft(
        _answers(),
        (evidence,),
        tmp_path / "manual.hwpx",
        operation_id="manual-op-001",
    )

    assert isinstance(result, ManualDraftResult)
    assert result.draft.validation.status == "reviewable"
    assert result.hwpx_validation.is_valid
    assert result.output_path.exists()
    assert result.hwp_export == HWPExportOutcome(
        True,
        tmp_path / "manual.hwp",
        None,
        None,
    )
    assert (tmp_path / "manual.hwp").read_bytes().startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")


def test_required_hwp_unavailability_keeps_hwpx_and_reports_diagnostic(tmp_path: Path) -> None:
    class UnavailableAdapter:
        def export(self, hwpx_path: Path, destination: Path) -> Path:
            del hwpx_path, destination
            raise HWPUnavailableError("local HWP adapter is unavailable")

    result = complete_manual_draft(
        _answers(),
        (Evidence("ev-001", "점검자료", "p.2", "동주민센터 25곳에서 점검한다."),),
        tmp_path / "canonical.hwpx",
        operation_id="required-hwp-unavailable",
        hwp_adapter=UnavailableAdapter(),
    )

    assert result.output_path.exists()
    assert result.hwpx_validation.is_valid
    assert result.hwp_export == HWPExportOutcome(
        False,
        None,
        "HWP 내보내기가 차단되었습니다.",
        "local HWP adapter is unavailable",
    )
    assert not (tmp_path / "canonical.hwp").exists()


def test_hwp_compatibility_failure_keeps_hwpx_and_reports_diagnostic(tmp_path: Path) -> None:
    class IncompatibleAdapter:
        def export(self, hwpx_path: Path, destination: Path) -> Path:
            del hwpx_path, destination
            raise HWPCompatibilityError("compatibility test failed: unsupported table preset")

    result = complete_manual_draft(
        _answers(),
        (Evidence("ev-001", "점검자료", "p.2", "동주민센터 25곳에서 점검한다."),),
        tmp_path / "canonical.hwpx",
        operation_id="required-hwp-incompatible",
        hwp_adapter=IncompatibleAdapter(),
        hwp_destination=tmp_path / "finished.hwp",
    )

    assert result.output_path.exists()
    assert result.hwpx_validation.is_valid
    assert result.hwp_export.available is False
    assert result.hwp_export.output_path is None
    assert result.hwp_export.warning == "HWP 내보내기가 차단되었습니다."
    assert result.hwp_export.diagnostic == "compatibility test failed: unsupported table preset"


def test_manual_workflow_finishes_when_ai_is_unavailable_or_consent_denied(tmp_path: Path) -> None:
    evidence = Evidence(
        evidence_id="ev-001",
        source_title="2026년 폭염 대응 내부 점검자료",
        locator="p.2, 표 1",
        excerpt="동주민센터 25곳에서 안부 확인과 무더위쉼터 안내를 수행하고 있다.",
    )

    with pytest.raises(ProviderUnavailableError):
        ProviderRegistry(()).generate(ProviderRequest("draft"), preferred=ProviderKind.OPENAI)

    gateway = ExternalTransmissionGateway(
        CloudProviderAdapter(ProviderKind.OPENAI),
        InMemoryConsentStore(),
    )
    with pytest.raises(ConsentRequiredError):
        gateway.transmit("manual-doc", "본문", provider=ProviderKind.OPENAI)

    result = complete_manual_draft(
        _answers(),
        (evidence,),
        tmp_path / "manual-without-ai.hwpx",
        operation_id="manual-without-ai-001",
    )

    assert result.draft_validation.status == "reviewable"
    assert result.hwpx_validation.is_valid
    assert result.output_path.exists()
