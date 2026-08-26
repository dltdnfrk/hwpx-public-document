from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from typing import Final

from .document_models import (
    BetaDocumentGroup,
    Claim,
    ClaimKind,
    CurrentOfficialRule,
    Draft,
    DraftValidation,
    Evidence,
    EvidenceProvenance,
    GuidedAnswers,
    Paragraph,
    ParagraphStatus,
    Section,
    TemplateConflictWarning,
    TemplateRegistry,
    _BETA_GROUP_LABELS,
)


_GROUPS: Final = (
    ("identity", "문서 식별", ("title", "document_type", "issuing_organization", "audience")),
    ("executive_context", "추진 배경 및 목적", ("background", "purpose")),
    ("evidence", "근거 자료", ("evidence_summary",)),
    ("current_state", "현황", ("current_state",)),
    ("plan", "추진 계획", ("objectives", "actions", "owners", "schedule", "resources")),
    ("risk_controls", "위험 요인 및 관리", ("risks", "controls")),
    ("results", "기대 효과 및 후속 조치", ("outcomes", "follow_up")),
    ("formal_finish", "결론 및 담당", ("conclusion", "contact", "date")),
)


def _marker(value: str, field: str, omissions: list[str]) -> str:
    cleaned = value.strip()
    if cleaned:
        return cleaned
    omissions.append(f"{field}: [확인 필요]")
    return "[확인 필요]"


_NUMERIC_CLAIM: Final = re.compile(
    r"(?:\d{4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?|\d+(?:\.\d+)?(?:개|곳|명|인|회|일|개월|월|년|%|원|만원|억원|분|시간)?)(?!인\s*가구)"
)
_GROUNDED_FIELDS: Final = frozenset(
    {
        "background", "purpose", "current_state", "objectives", "owners", "resources",
        "risks", "controls", "outcomes",
    }
)
_PLAN_FIELDS: Final = frozenset({"actions", "schedule", "follow_up"})


def _evidence_for_claim(claim: str, evidence: tuple[Evidence, ...]) -> tuple[str, ...]:
    return tuple(
        item.evidence_id
        for item in evidence
        if item.provenance_status is EvidenceProvenance.VERIFIED
        and (claim in item.excerpt or claim.rstrip("개곳명인회일개월월년%원만원억원분시간") in item.excerpt)
    )


def _ground_numeric_claims(
    value: str,
    field: str,
    evidence: tuple[Evidence, ...],
    omissions: list[str],
) -> str:
    def replace(match: re.Match[str]) -> str:
        claim = match.group(0)
        if value[match.end() :].lstrip().startswith("가구"):
            return claim
        if _evidence_for_claim(claim, evidence):
            return claim
        omissions.append(f"{field}: numeric claim {claim}: [확인 필요] (근거 부족)")
        return "[확인 필요]"

    return _NUMERIC_CLAIM.sub(replace, value)


def build_policy_plan_draft(
    answers: GuidedAnswers,
    evidence: tuple[Evidence, ...],
    *,
    template_registry: TemplateRegistry | None = None,
    current_rules: tuple[CurrentOfficialRule, ...] = (),
    document_id: str | None = None,
) -> Draft:
    omissions: list[str] = []
    title = _marker(answers.title, "title", omissions)
    organization = _marker(answers.issuing_organization, "issuing_organization", omissions)
    audience = _marker(answers.audience, "audience", omissions)
    source_ids = tuple(item.evidence_id for item in evidence)
    evidence_summary = "\n".join(
        f"{item.source_title} ({item.locator}): {item.excerpt}" for item in evidence
    ) or "[확인 필요]"
    values: dict[str, str] = {
        "title": title,
        "document_type": "정책·기획",
        "issuing_organization": organization,
        "audience": audience,
        "background": answers.background,
        "purpose": answers.purpose,
        "evidence_summary": evidence_summary,
        "current_state": answers.current_state,
        "objectives": answers.objectives,
        "actions": answers.actions,
        "owners": answers.owners,
        "schedule": answers.schedule,
        "resources": answers.resources,
        "risks": answers.risks,
        "controls": answers.controls,
        "outcomes": answers.outcomes,
        "follow_up": answers.follow_up,
        "conclusion": f"{title}을(를) 위와 같이 추진하고 결과를 점검한다.",
        "contact": answers.contact,
        "date": answers.date,
    }
    template = template_registry.select(organization) if template_registry is not None else None
    warnings: list[TemplateConflictWarning] = []
    presets: dict[str, str] = {}
    if template is not None:
        for override in template.overrides:
            if override.field in values:
                values[override.field] = override.value
                presets[override.field] = override.paragraph_preset
                for rule in current_rules:
                    if rule.field == override.field and rule.required_value != override.value:
                        warnings.append(
                            TemplateConflictWarning(
                                override.field,
                                override.value,
                                rule.required_value,
                                rule.source,
                            )
                        )
    for rule in current_rules:
        if rule.field in values:
            values[rule.field] = rule.required_value
    title = values["title"]
    values["conclusion"] = f"{title}을(를) 위와 같이 추진하고 결과를 점검한다."
    for field in _GROUNDED_FIELDS:
        values[field] = _ground_numeric_claims(values[field], field, evidence, omissions)
    sections: list[Section] = []
    paragraph_number = 1
    for section_id, heading, fields in _GROUPS:
        paragraphs: list[Paragraph] = []
        for field in fields:
            text = _marker(values[field], field, omissions)
            status = ParagraphStatus.REVIEW_REQUIRED if "[확인 필요]" in text else ParagraphStatus.CONFIRMED
            paragraphs.append(
                Paragraph(f"p-{paragraph_number:02d}", text, presets.get(field, "body"), source_ids, status)
            )
            paragraph_number += 1
        sections.append(Section(section_id, heading, tuple(paragraphs)))
    claims_list: list[Claim] = []
    grounded_and_plan_fields = [f for group in _GROUPS for f in group[2] if f in (_GROUNDED_FIELDS | _PLAN_FIELDS)]
    for field in grounded_and_plan_fields:
        for match in _NUMERIC_CLAIM.finditer(values[field]):
            if values[field][match.end() :].lstrip().startswith("가구"):
                continue
            claim = match.group(0)
            kind = ClaimKind.FACTUAL if field in _GROUNDED_FIELDS else ClaimKind.PLAN_INPUT
            claims_list.append(Claim(f"{field}: {claim}", _evidence_for_claim(claim, evidence), kind))
    claims = tuple(dict.fromkeys(claims_list))
    stable_id = document_id or hashlib.sha256(
        "|".join((organization, audience, answers.date, answers.purpose)).encode("utf-8")
    ).hexdigest()[:24]
    period = answers.period.strip() or answers.schedule.strip()
    all_text = sum(len(paragraph.text) for section in sections for paragraph in section.paragraphs)
    return Draft(
        title,
        organization,
        audience,
        tuple(sections),
        evidence,
        claims,
        tuple(dict.fromkeys(omissions)),
        max(1, (all_text + 1799) // 1800),
        BetaDocumentGroup.POLICY_PLANNING,
        "베타",
        "정책·기획 베타 문서이며 외부 마무리 전 1차 검토를 위한 초안입니다.",
        tuple(warnings),
        stable_id,
        period,
    )


def build_beta_draft(
    group: BetaDocumentGroup,
    answers: GuidedAnswers,
    evidence: tuple[Evidence, ...],
    *,
    template_registry: TemplateRegistry | None = None,
    current_rules: tuple[CurrentOfficialRule, ...] = (),
    document_id: str | None = None,
) -> Draft:
    draft = build_policy_plan_draft(
        answers,
        evidence,
        template_registry=template_registry,
        current_rules=current_rules,
        document_id=document_id,
    )
    if group is BetaDocumentGroup.POLICY_PLANNING:
        return draft
    label = _BETA_GROUP_LABELS[group]
    return replace(
        draft,
        beta_group=group,
        quality_notice=f"{label} 베타 문서이며 외부 마무리 전 1차 검토를 위한 초안입니다.",
    )


def validate_draft(draft: Draft) -> DraftValidation:
    expected = {group[0]: len(group[2]) for group in _GROUPS}
    actual = {section.section_id: len(section.paragraphs) for section in draft.sections}
    structure_complete = actual == expected and all(
        paragraph.text.strip()
        for section in draft.sections
        for paragraph in section.paragraphs
    )
    required_structure_percent = 100 if structure_complete else 0
    completed_groups = sum(
        section.section_id in expected
        and len(section.paragraphs) == expected[section.section_id]
        and all(paragraph.text.strip() for paragraph in section.paragraphs)
        for section in draft.sections
    )
    checklist_score = round(completed_groups / len(_GROUPS) * 100)
    unsupported = tuple(
        claim.text
        for claim in draft.claims
        if claim.kind is ClaimKind.FACTUAL and not claim.evidence_ids
    )
    table_dimensions_valid = all(
        len({cell.column for cell in table.cells}) <= len(table.columns)
        and all(cell.table_id == table.table_id for cell in table.cells)
        for table in draft.tables
    )
    status = "reviewable" if not draft.critical_omissions and not unsupported else "evidence_blocked"
    return DraftValidation(
        required_structure_percent,
        checklist_score,
        draft.critical_omissions,
        unsupported,
        status,
        draft.warnings,
        draft.page_count,
        table_dimensions_valid,
    )
