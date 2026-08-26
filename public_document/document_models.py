from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from hwpx import HWPXValidation

    from .hwp_export import HWPExportOutcome


class EvidenceProvenance(Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    STALE = "stale"
    CONTRADICTORY = "contradictory"


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_title: str
    locator: str
    excerpt: str
    provenance_status: EvidenceProvenance = EvidenceProvenance.VERIFIED


@dataclass(frozen=True)
class GuidedAnswers:
    title: str
    issuing_organization: str
    audience: str
    purpose: str
    background: str
    current_state: str
    objectives: str
    actions: str
    owners: str
    schedule: str
    resources: str
    risks: str
    controls: str
    outcomes: str
    follow_up: str
    contact: str
    date: str
    period: str = ""


class ParagraphStatus(Enum):
    CONFIRMED = "confirmed"
    REVIEW_REQUIRED = "review-required"


@dataclass(frozen=True)
class Paragraph:
    paragraph_id: str
    text: str
    preset: str
    evidence_ids: tuple[str, ...]
    status: ParagraphStatus = ParagraphStatus.CONFIRMED


@dataclass(frozen=True)
class DocumentTableCell:
    table_id: str
    row: int
    column: int
    text: str


@dataclass(frozen=True)
class DocumentTable:
    table_id: str
    columns: tuple[str, ...]
    cells: tuple[DocumentTableCell, ...]
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.table_id.strip() or not self.columns:
            raise ValueError("table_id and columns are required")
        coordinates = {(cell.row, cell.column) for cell in self.cells}
        if len(coordinates) != len(self.cells):
            raise ValueError("table cells must have unique coordinates")
        if any(cell.table_id != self.table_id for cell in self.cells):
            raise ValueError("table cell table_id must match the containing table")
        if any(cell.row < 0 or cell.column < 0 or cell.column >= len(self.columns) for cell in self.cells):
            raise ValueError("table cell coordinate is outside the declared columns")

    @property
    def row_count(self) -> int:
        return max((cell.row for cell in self.cells), default=-1) + 1


@dataclass(frozen=True)
class Section:
    section_id: str
    heading: str
    paragraphs: tuple[Paragraph, ...]
    tables: tuple[DocumentTable, ...] = ()


class ClaimKind(Enum):
    FACTUAL = "factual"
    PLAN_INPUT = "plan-input"


@dataclass(frozen=True)
class Claim:
    text: str
    evidence_ids: tuple[str, ...]
    kind: ClaimKind = ClaimKind.FACTUAL


@dataclass(frozen=True)
class DraftValidation:
    required_structure_percent: int
    checklist_score: int
    critical_omissions: tuple[str, ...]
    unsupported_numeric_claims: tuple[str, ...]
    status: str
    warnings: tuple[TemplateConflictWarning, ...] = ()
    page_count: int = 0
    table_dimensions_valid: bool = True


@dataclass(frozen=True)
class TemplateOverride:
    field: str
    value: str
    paragraph_preset: str = "body"


@dataclass(frozen=True)
class InstitutionTemplate:
    template_id: str
    institution: str
    overrides: tuple[TemplateOverride, ...]


@dataclass(frozen=True)
class CurrentOfficialRule:
    field: str
    required_value: str
    source: str


@dataclass(frozen=True)
class TemplateConflictWarning:
    field: str
    template_value: str
    required_value: str
    rule_source: str

    @property
    def message(self) -> str:
        return (
            f"{self.field}: 기관 템플릿 값과 {self.rule_source}의 현재 규칙이 충돌합니다. "
            f"템플릿={self.template_value!r}, 규칙={self.required_value!r}"
        )


class TemplateRegistry:
    def __init__(self, templates: tuple[InstitutionTemplate, ...] = ()) -> None:
        self._templates = {template.institution: template for template in templates}

    def register(self, template: InstitutionTemplate) -> None:
        self._templates[template.institution] = template

    def select(self, institution: str) -> InstitutionTemplate | None:
        return self._templates.get(institution)


class BetaDocumentGroup(Enum):
    POLICY_PLANNING = "policy-planning"
    SITUATION_INFORMATION = "situation-information"
    MEETING_MATERIALS_RESULTS = "meeting-materials-results"
    EVENT_PLAN_SPEECH = "event-plan-speech"


_BETA_GROUP_LABELS: Final = {
    BetaDocumentGroup.POLICY_PLANNING: "정책·기획",
    BetaDocumentGroup.SITUATION_INFORMATION: "상황·정보",
    BetaDocumentGroup.MEETING_MATERIALS_RESULTS: "회의자료·결과",
    BetaDocumentGroup.EVENT_PLAN_SPEECH: "행사계획·연설",
}


@dataclass(frozen=True)
class Draft:
    title: str
    issuing_organization: str
    audience: str
    sections: tuple[Section, ...]
    evidence: tuple[Evidence, ...]
    claims: tuple[Claim, ...]
    critical_omissions: tuple[str, ...]
    page_count: int
    beta_group: BetaDocumentGroup
    beta_label: str
    quality_notice: str
    warnings: tuple[TemplateConflictWarning, ...] = ()
    document_id: str = ""
    period: str = ""
    tables: tuple[DocumentTable, ...] = ()

    @property
    def validation(self) -> DraftValidation:
        from .draft_builder import validate_draft

        return validate_draft(self)


@dataclass(frozen=True)
class ManualDraftResult:
    draft: Draft
    output_path: Path
    draft_validation: DraftValidation
    hwpx_validation: HWPXValidation
    hwp_export: HWPExportOutcome
