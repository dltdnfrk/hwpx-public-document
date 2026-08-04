from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import zipfile

import pytest

from corrections import Correction, CorrectionKind, CorrectionSession, TableCell
from hwpx import validate_hwpx
from privacy import ExternalTransmissionGateway, InMemoryConsentStore
from public_document import (
    DocumentTable,
    DocumentTableCell,
    DuplicateWriteError,
    Evidence,
    GuidedAnswers,
    PageLimitExceededError,
    ProviderCapabilities,
    ProviderKind,
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
    build_policy_plan_draft,
    export_hwpx,
    build_beta_draft,
)


def _answers(**overrides: str) -> GuidedAnswers:
    values = {
        "title": "검토 계획",
        "issuing_organization": "기관",
        "audience": "시민",
        "purpose": "보호 조치를 시행한다.",
        "background": "추진 배경이다.",
        "current_state": "현황을 점검한다.",
        "objectives": "접근성을 높인다.",
        "actions": "점검을 시행한다.",
        "owners": "담당 부서",
        "schedule": "상반기",
        "resources": "기존 예산",
        "risks": "연락 두절",
        "controls": "방문 확인",
        "outcomes": "운영 상태를 점검한다.",
        "follow_up": "결과를 반영한다.",
        "contact": "담당팀",
        "date": "2026-05-20",
    }
    values.update(overrides)
    return GuidedAnswers(**values)


def test_document_identity_and_provenance_are_stable() -> None:
    evidence = Evidence("ev-1", "자료", "p.1", "현황")
    first = build_policy_plan_draft(_answers(), (evidence,))
    second = build_policy_plan_draft(_answers(), (Evidence("ev-1", "자료", "p.1", "현황"),))

    assert first.document_id == second.document_id
    assert first.period == "상반기"
    assert first.sections[0].paragraphs[0].status.value == "confirmed"


def test_numeric_grounding_covers_non_current_state_fields() -> None:
    draft = build_policy_plan_draft(_answers(objectives="12명에게 교육한다."), ())

    assert any("objectives: numeric claim 12명" in omission for omission in draft.critical_omissions)
    assert "[확인 필요]" in draft.sections[4].paragraphs[0].text
    assert draft.sections[4].paragraphs[0].status.value == "review-required"


def test_each_beta_group_has_visible_label_and_valid_export(tmp_path: Path) -> None:
    from public_document import BetaDocumentGroup

    evidence = (Evidence("ev-beta", "자료", "p.1", "현황"),)
    for index, group in enumerate(BetaDocumentGroup):
        draft = build_beta_draft(group, _answers(), evidence)
        output = export_hwpx(draft, tmp_path / f"beta-{index}.hwpx", operation_id=f"gap-beta-{index}")

        assert draft.beta_label == "베타"
        with zipfile.ZipFile(output) as package:
            assert group.value.encode() in package.read("Contents/content.hpf")
        assert validate_hwpx(output, draft).is_valid


def test_operation_id_cannot_write_two_destinations(tmp_path: Path) -> None:
    draft = build_policy_plan_draft(_answers(), ())
    export_hwpx(draft, tmp_path / "first.hwpx", operation_id="gap-duplicate-write")

    with pytest.raises(DuplicateWriteError):
        export_hwpx(draft, tmp_path / "second.hwpx", operation_id="gap-duplicate-write")


def test_page_limit_is_enforced_at_export_boundary(tmp_path: Path) -> None:
    draft = replace(build_policy_plan_draft(_answers(), ()), page_count=6)

    with pytest.raises(PageLimitExceededError):
        export_hwpx(draft, tmp_path / "too-long.hwpx", operation_id="gap-page-limit")


def test_title_and_table_corrections_update_the_serialized_document(tmp_path: Path) -> None:
    draft = build_policy_plan_draft(_answers(), ())
    session = CorrectionSession(draft, (TableCell("tbl-1", 0, 0, "기존 셀"),))
    preview = session.preview(
        (
            Correction(CorrectionKind.TITLE_REPLACEMENT, "title", "새 제목"),
            Correction(CorrectionKind.TABLE_CELL_REPLACEMENT, "tbl-1:0:0", "새 셀"),
        )
    )
    session.apply(preview)
    output = export_hwpx(session.draft, tmp_path / "corrected.hwpx", operation_id="gap-correction")

    assert session.draft.sections[0].paragraphs[0].text == "새 제목"
    assert session.draft.tables[0].cells[0].text == "새 셀"
    assert validate_hwpx(output, session.draft).is_valid


class _CloudRecordingAdapter:
    kind = ProviderKind.OPENAI
    capabilities = ProviderCapabilities(True, True, False)

    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return ProviderResponse(())


def test_provider_registry_requires_consent_gateway_for_external_adapter() -> None:
    adapter = _CloudRecordingAdapter()
    registry = ProviderRegistry((adapter,))

    with pytest.raises(RuntimeError, match="requires consent gateway"):
        registry.generate(ProviderRequest("본문", "doc-1"), preferred=ProviderKind.OPENAI)

    consent = InMemoryConsentStore()
    gateway = ExternalTransmissionGateway(adapter, consent)
    consent.grant("doc-1", ProviderKind.OPENAI)
    response = ProviderRegistry((adapter,), consent_gateway=gateway).generate(
        ProviderRequest("본문", "doc-1"),
        preferred=ProviderKind.OPENAI,
    )

    assert response == ProviderResponse(())
    assert adapter.requests[0].document_id == "doc-1"


class _Transport:
    def generate(self, provider: ProviderKind, request: ProviderRequest) -> ProviderResponse:
        assert provider is ProviderKind.OPENAI
        assert request.instruction == "본문"
        return ProviderResponse(())


def test_configured_cloud_adapter_uses_transport_contract() -> None:
    from public_document import CloudProviderAdapter

    adapter = CloudProviderAdapter(ProviderKind.OPENAI, _Transport())

    assert adapter.generate(ProviderRequest("본문")) == ProviderResponse(())
    assert adapter.generate_calls == 1
