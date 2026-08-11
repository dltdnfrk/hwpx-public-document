from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from enum import Enum
from typing import TYPE_CHECKING, Final, Protocol
from xml.etree import ElementTree

if TYPE_CHECKING:
    from hwpx import HWPXValidation


_HP: Final = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HC: Final = "http://www.hancom.co.kr/hwpml/2011/core"
_NS: Final = {"hp": _HP, "hc": _HC}
_BUNDLED_RHWP: Final = Path(__file__).resolve().parent / "Resources" / "Engines" / "rhwp"
_BUNDLED_RHWP_SHA256: Final = "a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b"
_HWP_CFB_SIGNATURE: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ElementTree.register_namespace("hp", _HP)
ElementTree.register_namespace("hc", _HC)


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


class HWPExportError(RuntimeError):
    pass


class HWPUnavailableError(HWPExportError):
    pass


class HWPCompatibilityError(HWPExportError):
    pass


class DuplicateWriteError(HWPExportError):
    pass


class PageLimitExceededError(HWPExportError):
    pass


class ProviderConsentRequiredError(RuntimeError):
    pass


class HWPAdapter(Protocol):
    def export(self, hwpx_path: Path, destination: Path) -> Path: ...


class BundledRhwpAdapter:
    def __init__(self, engine_path: Path = _BUNDLED_RHWP) -> None:
        self._engine_path: Path = engine_path.resolve()
        self._requires_pinned_hash = self._engine_path == _BUNDLED_RHWP.resolve()

    def export(self, hwpx_path: Path, destination: Path) -> Path:
        engine = self._engine_path
        if not engine.is_file() or not os.access(engine, os.X_OK):
            raise HWPUnavailableError(f"pinned rhwp engine is unavailable or not executable: {engine}")
        if self._requires_pinned_hash and hashlib.sha256(engine.read_bytes()).hexdigest() != _BUNDLED_RHWP_SHA256:
            raise HWPUnavailableError(f"pinned rhwp engine hash does not match the approved build: {engine}")
        destination = destination.resolve()
        if destination.exists():
            raise DuplicateWriteError(f"HWP destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".rhwp-", dir=destination.parent) as working_directory:
            staged_output = Path(working_directory) / destination.name
            try:
                completed = subprocess.run(
                    (
                        str(engine),
                        "convert",
                        str(hwpx_path.resolve()),
                        str(staged_output),
                        "--verify",
                        "--verify-pages",
                    ),
                    capture_output=True,
                    check=False,
                    text=True,
                )
            except OSError as error:
                raise HWPUnavailableError(f"pinned rhwp engine could not start at {engine}: {error}") from error
            if completed.returncode != 0:
                diagnostic = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
                raise HWPCompatibilityError(
                    f"pinned rhwp conversion failed with exit {completed.returncode}: {diagnostic}"
                )
            try:
                with staged_output.open("rb") as staged_file:
                    signature = staged_file.read(len(_HWP_CFB_SIGNATURE))
                    os.fsync(staged_file.fileno())
            except OSError as error:
                raise HWPCompatibilityError(f"pinned rhwp produced no readable HWP artifact: {error}") from error
            if signature != _HWP_CFB_SIGNATURE:
                raise HWPCompatibilityError("pinned rhwp output failed the HWP CFB signature check")
            try:
                os.link(staged_output, destination)
            except FileExistsError as error:
                raise DuplicateWriteError(f"HWP destination already exists: {destination}") from error
            except OSError as error:
                raise HWPExportError(f"validated HWP artifact could not be published atomically: {error}") from error
        return destination


@dataclass(frozen=True)
class HWPExportOutcome:
    available: bool
    output_path: Path | None
    warning: str | None
    diagnostic: str | None


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
        return validate_draft(self)


@dataclass(frozen=True)
class ManualDraftResult:
    draft: Draft
    output_path: Path
    draft_validation: DraftValidation
    hwpx_validation: HWPXValidation
    hwp_export: HWPExportOutcome


class ProviderKind(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI_COMPATIBLE = "openai-compatible"
    LOCAL = "local"


@dataclass(frozen=True)
class ProviderCapabilities:
    structured_commands: bool
    constrained_patches: bool
    local_execution: bool


@dataclass(frozen=True)
class ProviderRequest:
    instruction: str
    document_id: str = ""


@dataclass(frozen=True)
class DocumentCommand:
    name: str
    target: str
    value: str


@dataclass(frozen=True)
class ProviderResponse:
    commands: tuple[DocumentCommand, ...]


class ProviderUnavailableError(RuntimeError):
    pass


class ProviderAdapter(Protocol):
    @property
    def kind(self) -> ProviderKind: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def generate(self, request: ProviderRequest) -> ProviderResponse: ...


class ProviderTransport(Protocol):
    def generate(self, provider: ProviderKind, request: ProviderRequest) -> ProviderResponse: ...


class ConsentGateway(Protocol):
    def transmit(self, document_id: str, body: str, *, provider: ProviderKind) -> ProviderResponse: ...


class CloudProviderAdapter:
    def __init__(self, kind: ProviderKind, transport: ProviderTransport | None = None) -> None:
        if kind is ProviderKind.LOCAL:
            raise ValueError("cloud adapter requires a cloud provider kind")
        self._kind = kind
        self._transport = transport
        self._generate_calls = 0

    @property
    def kind(self) -> ProviderKind:
        return self._kind

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(True, True, False)

    @property
    def generate_calls(self) -> int:
        return self._generate_calls

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        if self._transport is None:
            raise ProviderUnavailableError(f"{self.kind.value} provider transport is not configured")
        self._generate_calls += 1
        return self._transport.generate(self.kind, request)


class LocalProviderAdapter:
    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.LOCAL

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(True, True, True)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise ProviderUnavailableError("local provider adapter is not implemented")


class ProviderRegistry:
    def __init__(
        self,
        adapters: tuple[ProviderAdapter, ...],
        *,
        consent_gateway: ConsentGateway | None = None,
    ) -> None:
        self._adapters = {adapter.kind: adapter for adapter in adapters}
        self._consent_gateway = consent_gateway

    def select(self, kind: ProviderKind) -> ProviderAdapter:
        try:
            return self._adapters[kind]
        except KeyError as error:
            raise ProviderUnavailableError(f"{kind.value} provider is not configured") from error

    def generate(self, request: ProviderRequest, *, preferred: ProviderKind) -> ProviderResponse:
        adapter = self.select(preferred)
        if preferred is ProviderKind.LOCAL:
            return adapter.generate(request)
        if self._consent_gateway is None or not request.document_id.strip():
            raise ProviderConsentRequiredError(
                f"external provider access requires consent gateway and document_id for {preferred.value}"
            )
        return self._consent_gateway.transmit(
            request.document_id,
            request.instruction,
            provider=preferred,
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


def _text(parent: ElementTree.Element, value: str) -> None:
    run = ElementTree.SubElement(parent, f"{{{_HP}}}run")
    ElementTree.SubElement(run, f"{{{_HP}}}t").text = value


def _section_xml(draft: Draft) -> bytes:
    root = ElementTree.Element(f"{{{_HP}}}sec")
    paragraph = ElementTree.SubElement(root, f"{{{_HP}}}p")
    _text(paragraph, f"[{draft.beta_label}] {_BETA_GROUP_LABELS[draft.beta_group]} 1차 검토 초안")
    paragraph = ElementTree.SubElement(root, f"{{{_HP}}}p")
    _text(paragraph, draft.quality_notice)
    for warning in draft.warnings:
        paragraph = ElementTree.SubElement(root, f"{{{_HP}}}p")
        _text(paragraph, f"[경고] {warning.message}")
    for section in draft.sections:
        paragraph = ElementTree.SubElement(root, f"{{{_HP}}}p")
        _text(paragraph, section.heading)
        for item in section.paragraphs:
            paragraph = ElementTree.SubElement(root, f"{{{_HP}}}p")
            paragraph.set("paragraph-id", item.paragraph_id)
            paragraph.set("preset", item.preset)
            paragraph.set("evidence-refs", ",".join(item.evidence_ids))
            paragraph.set("status", item.status.value)
            _text(paragraph, item.text)
        for table in section.tables:
            _table_xml(root, table)
    for table in draft.tables:
        _table_xml(root, table)
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _table_xml(root: ElementTree.Element, table: DocumentTable) -> None:
    table_element = ElementTree.SubElement(
        root,
        f"{{{_HP}}}tbl",
        {
            "table-id": table.table_id,
            "columns": str(len(table.columns)),
            "rows": str(table.row_count),
            "evidence-refs": ",".join(table.evidence_ids),
        },
    )
    for row in range(table.row_count):
        row_element = ElementTree.SubElement(table_element, f"{{{_HP}}}tr")
        for column in range(len(table.columns)):
            cell = next((item for item in table.cells if item.row == row and item.column == column), None)
            cell_element = ElementTree.SubElement(
                row_element,
                f"{{{_HP}}}tc",
                {"row": str(row), "column": str(column)},
            )
            _text(cell_element, "" if cell is None else cell.text)


def _content_xml(draft: Draft) -> bytes:
    root = ElementTree.Element("package", {"xmlns": _HC})
    ElementTree.SubElement(
        root,
        "document",
        {
            "id": "section0",
            "document-id": draft.document_id,
            "title": draft.title,
            "period": draft.period,
            "beta-label": draft.beta_label,
            "beta-group": draft.beta_group.value,
        },
    )
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _metadata_xml(draft: Draft, operation_id: str) -> bytes:
    root = ElementTree.Element(
        "metadata",
        {
            "operation-id": operation_id,
            "spec-id": "public-document-core",
            "spec-version": "1.0",
            "spec-content-hash": "sha256:332e8420abd4c3d2701f4f5b724903e10ad2826ea1b5ffb4cef8c1b9395d1574",
            "document-id": draft.document_id,
            "period": draft.period,
        },
    )
    for evidence in draft.evidence:
        ElementTree.SubElement(
            root,
            "evidence",
            {
                "id": evidence.evidence_id,
                "title": evidence.source_title,
                "locator": evidence.locator,
                "provenance-status": evidence.provenance_status.value,
            },
        )
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _styles_xml(draft: Draft) -> bytes:
    root = ElementTree.Element("hh:styles", {"xmlns:hh": "http://www.hancom.co.kr/hwpml/2011/head"})
    for preset in sorted({paragraph.preset for section in draft.sections for paragraph in section.paragraphs}):
        ElementTree.SubElement(root, "hh:style", {"id": preset})
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _relationships_xml() -> bytes:
    root = ElementTree.Element(
        "Relationships",
        {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"},
    )
    ElementTree.SubElement(root, "Relationship", {"Id": "rIdMetadata", "Type": "metadata", "Target": "../metadata.xml"})
    ElementTree.SubElement(root, "Relationship", {"Id": "rIdStyles", "Type": "styles", "Target": "../styles.xml"})
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


_EXPORTS: dict[str, tuple[Path, dict[str, bytes]]] = {}


def export_hwpx(draft: Draft, destination: Path, *, operation_id: str) -> Path:
    if not operation_id.strip():
        raise ValueError("operation_id must be non-empty")
    validation = validate_draft(draft)
    if validation.required_structure_percent != 100 or not validation.table_dimensions_valid:
        raise HWPExportError("draft failed the HWPX export validation profile")
    parts = {
        "mimetype": b"application/hwp+zip",
        "version.xml": b'<?xml version="1.0" encoding="UTF-8"?><version app="public-document" version="1.0"/>',
        "Contents/content.hpf": _content_xml(draft),
        "Contents/header.xml": b'<?xml version="1.0" encoding="UTF-8"?><hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"/>',
        "Contents/section0.xml": _section_xml(draft),
        "Contents/styles.xml": _styles_xml(draft),
        "Contents/metadata.xml": _metadata_xml(draft, operation_id),
        "Contents/_rels/section0.xml.rels": _relationships_xml(),
    }
    destination = destination.resolve()
    previous = _EXPORTS.get(operation_id)
    if previous is not None and (previous[0] != destination or previous[1] != parts):
        raise DuplicateWriteError("operation_id may write exactly one destination snapshot")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        with zipfile.ZipFile(destination) as existing:
            existing_parts = {name: existing.read(name) for name in existing.namelist()}
        if existing_parts != parts:
            raise DuplicateWriteError("destination already contains a different HWPX export")
        _EXPORTS[operation_id] = (destination, parts)
        return destination
    fd, temporary_name = tempfile.mkstemp(prefix=".hwpx-", dir=str(destination.parent))
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for name, content in parts.items():
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
                package.writestr(info, content)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    _EXPORTS[operation_id] = (destination, parts)
    return destination


def complete_manual_draft(
    answers: GuidedAnswers,
    evidence: tuple[Evidence, ...],
    destination: Path,
    *,
    operation_id: str,
    template_registry: TemplateRegistry | None = None,
    current_rules: tuple[CurrentOfficialRule, ...] = (),
    hwp_adapter: HWPAdapter | None = None,
    hwp_destination: Path | None = None,
) -> ManualDraftResult:
    """Complete the local drafting path without consulting an AI provider."""
    draft = build_policy_plan_draft(
        answers,
        evidence,
        template_registry=template_registry,
        current_rules=current_rules,
    )
    output_path = export_hwpx(draft, destination, operation_id=operation_id)
    from hwpx import validate_hwpx

    adapter = hwp_adapter if hwp_adapter is not None else BundledRhwpAdapter()
    target = hwp_destination if hwp_destination is not None else output_path.with_suffix(".hwp")
    try:
        hwp_export = HWPExportOutcome(
            True,
            adapter.export(output_path, target),
            None,
            None,
        )
    except (HWPUnavailableError, HWPCompatibilityError) as error:
        hwp_export = HWPExportOutcome(
            False,
            None,
            "HWP 내보내기가 차단되었습니다.",
            str(error),
        )
    return ManualDraftResult(
        draft,
        output_path,
        validate_draft(draft),
        validate_hwpx(output_path, draft),
        hwp_export,
    )


def __getattr__(name: str):
    if name in {"HWPXValidation", "hwpx_content_hash", "validate_hwpx"}:
        from hwpx import HWPXValidation, hwpx_content_hash, validate_hwpx

        return {"HWPXValidation": HWPXValidation, "hwpx_content_hash": hwpx_content_hash, "validate_hwpx": validate_hwpx}[name]
    if name in {
        "ConsentRequiredError",
        "CredentialStoreUnavailableError",
        "ExternalTransmissionGateway",
        "InMemoryConsentStore",
        "KeychainCredentialStore",
        "SensitiveInformationDetector",
        "SensitiveMatch",
        "SensitiveScan",
        "TransmissionEvent",
    }:
        from privacy import (
            ConsentRequiredError,
            CredentialStoreUnavailableError,
            ExternalTransmissionGateway,
            InMemoryConsentStore,
            KeychainCredentialStore,
            SensitiveInformationDetector,
            SensitiveMatch,
            SensitiveScan,
            TransmissionEvent,
        )
        return {
            "ConsentRequiredError": ConsentRequiredError,
            "CredentialStoreUnavailableError": CredentialStoreUnavailableError,
            "ExternalTransmissionGateway": ExternalTransmissionGateway,
            "InMemoryConsentStore": InMemoryConsentStore,
            "KeychainCredentialStore": KeychainCredentialStore,
            "SensitiveInformationDetector": SensitiveInformationDetector,
            "SensitiveMatch": SensitiveMatch,
            "SensitiveScan": SensitiveScan,
            "TransmissionEvent": TransmissionEvent,
        }[name]
    raise AttributeError(name)
