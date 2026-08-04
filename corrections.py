from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Optional, Tuple

from public_document import (
    DocumentTable,
    DocumentTableCell,
    Draft,
    Paragraph,
    ParagraphStatus,
    Section,
)


class CorrectionKind(Enum):
    TITLE_REPLACEMENT = "title-replacement"
    PARAGRAPH_REPLACEMENT = "paragraph-replacement"
    PARAGRAPH_APPEND = "paragraph-append"
    PARAGRAPH_PRESET = "paragraph-preset"
    TABLE_CELL_REPLACEMENT = "table-cell-replacement"


class CorrectionStatus(Enum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    PARTIALLY_APPLIED = "partially-applied"
    REJECTED = "rejected"


_PRESETS = frozenset({"body", "heading", "bullet", "emphasis"})


@dataclass(frozen=True)
class Correction:
    kind: CorrectionKind
    target: str
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CorrectionKind):
            raise ValueError("correction kind must be an allowlisted correction kind")


TableCell = DocumentTableCell


@dataclass(frozen=True)
class CorrectionPreview:
    accepted: tuple[Correction, ...]
    rejected: tuple[Correction, ...]
    status: CorrectionStatus

    def remove(self, index: int) -> CorrectionPreview:
        if index < 0 or index >= len(self.accepted):
            raise IndexError("correction preview index out of range")
        accepted = self.accepted[:index] + self.accepted[index + 1 :]
        status = CorrectionStatus.PROPOSED if accepted else CorrectionStatus.REJECTED
        return CorrectionPreview(accepted, self.rejected, status)


@dataclass(frozen=True)
class CorrectionResult:
    status: CorrectionStatus
    accepted: tuple[Correction, ...]
    rejected: tuple[Correction, ...]
    revision: int


def _replace_paragraph(
    draft: Draft, target: str, update: str, *, append: bool = False, preset: str | None = None
) -> Draft | None:
    changed = False
    sections: list[Section] = []
    for section in draft.sections:
        paragraphs: list[Paragraph] = []
        for paragraph in section.paragraphs:
            if paragraph.paragraph_id != target:
                paragraphs.append(paragraph)
                continue
            changed = True
            text = paragraph.text if preset is not None else paragraph.text + update if append else update
            paragraphs.append(
                replace(
                    paragraph,
                    text=text,
                    preset=preset or paragraph.preset,
                    status=ParagraphStatus.REVIEW_REQUIRED
                    if "[확인 필요]" in text
                    else ParagraphStatus.CONFIRMED,
                )
            )
        sections.append(replace(section, paragraphs=tuple(paragraphs)))
    return replace(draft, sections=tuple(sections)) if changed else None


def _apply_title(
    draft: Draft, table_cells: tuple[TableCell, ...], correction: Correction
) -> tuple[Draft, tuple[TableCell, ...]] | None:
    if correction.target != "title" or not correction.value.strip():
        return None
    updated = _replace_paragraph(draft, "p-01", correction.value)
    return (replace(updated, title=correction.value), table_cells) if updated is not None else None


def _apply_paragraph(
    draft: Draft, table_cells: tuple[TableCell, ...], correction: Correction
) -> tuple[Draft, tuple[TableCell, ...]] | None:
    updated = _replace_paragraph(draft, correction.target, correction.value)
    return (updated, table_cells) if updated is not None else None


def _apply_append(
    draft: Draft, table_cells: tuple[TableCell, ...], correction: Correction
) -> tuple[Draft, tuple[TableCell, ...]] | None:
    if not correction.value:
        return None
    updated = _replace_paragraph(draft, correction.target, correction.value, append=True)
    return (updated, table_cells) if updated is not None else None


def _apply_preset(
    draft: Draft, table_cells: tuple[TableCell, ...], correction: Correction
) -> tuple[Draft, tuple[TableCell, ...]] | None:
    if correction.value not in _PRESETS:
        return None
    updated = _replace_paragraph(draft, correction.target, "", preset=correction.value)
    return (updated, table_cells) if updated is not None else None


def _apply_table_cell(
    draft: Draft, table_cells: tuple[TableCell, ...], correction: Correction
) -> tuple[Draft, tuple[TableCell, ...]] | None:
    parts = correction.target.split(":")
    if len(parts) != 3 or not correction.value:
        return None
    table_id, row_text, column_text = parts
    try:
        row = int(row_text)
        column = int(column_text)
    except ValueError:
        return None
    if not any(
        cell.table_id == table_id and cell.row == row and cell.column == column
        for cell in table_cells
    ):
        return None
    updated_cells = tuple(
        replace(cell, text=correction.value)
        if cell.table_id == table_id and cell.row == row and cell.column == column
        else cell
        for cell in table_cells
    )
    updated_tables: list[DocumentTable] = []
    table_changed = False
    for table in draft.tables:
        if table.table_id != table_id:
            updated_tables.append(table)
            continue
        table_cells_updated = tuple(
            replace(cell, text=correction.value)
            if cell.row == row and cell.column == column
            else cell
            for cell in table.cells
        )
        if table_cells_updated != table.cells:
            table_changed = True
        updated_tables.append(replace(table, cells=table_cells_updated))
    updated_draft = replace(draft, tables=tuple(updated_tables)) if table_changed else draft
    return updated_draft, updated_cells


_CorrectionHandler = Callable[
    [Draft, Tuple[TableCell, ...], Correction], Optional[Tuple[Draft, Tuple[TableCell, ...]]]
]
_CORRECTION_HANDLERS: dict[CorrectionKind, _CorrectionHandler] = {
    CorrectionKind.TITLE_REPLACEMENT: _apply_title,
    CorrectionKind.PARAGRAPH_REPLACEMENT: _apply_paragraph,
    CorrectionKind.PARAGRAPH_APPEND: _apply_append,
    CorrectionKind.PARAGRAPH_PRESET: _apply_preset,
    CorrectionKind.TABLE_CELL_REPLACEMENT: _apply_table_cell,
}


def _apply_correction(
    draft: Draft, table_cells: tuple[TableCell, ...], correction: Correction
) -> tuple[Draft, tuple[TableCell, ...]] | None:
    handler = _CORRECTION_HANDLERS.get(correction.kind)
    return handler(draft, table_cells, correction) if handler is not None else None


class CorrectionSession:
    def __init__(self, draft: Draft, table_cells: tuple[TableCell, ...] = ()) -> None:
        if table_cells and not draft.tables:
            grouped: dict[str, list[TableCell]] = {}
            for cell in table_cells:
                grouped.setdefault(cell.table_id, []).append(cell)
            tables = tuple(
                DocumentTable(
                    table_id,
                    tuple(f"열 {index + 1}" for index in range(max(cell.column for cell in cells) + 1)),
                    tuple(cells),
                )
                for table_id, cells in grouped.items()
            )
            draft = replace(draft, tables=tables)
        self._draft = draft
        self._table_cells = table_cells
        self._revision = 0
        self._history: tuple[tuple[Draft, tuple[TableCell, ...]], ...] = ()

    @property
    def draft(self) -> Draft:
        return self._draft

    @property
    def table_cells(self) -> tuple[TableCell, ...]:
        return self._table_cells

    @property
    def revision(self) -> int:
        return self._revision

    def preview(self, corrections: tuple[Correction, ...]) -> CorrectionPreview:
        draft = self._draft
        table_cells = self._table_cells
        accepted: list[Correction] = []
        rejected: list[Correction] = []
        for correction in corrections:
            result = _apply_correction(draft, table_cells, correction)
            if result is None:
                rejected.append(correction)
                continue
            draft, table_cells = result
            accepted.append(correction)
        status = CorrectionStatus.PROPOSED if accepted else CorrectionStatus.REJECTED
        return CorrectionPreview(tuple(accepted), tuple(rejected), status)

    def apply(self, preview: CorrectionPreview) -> CorrectionResult:
        if not preview.accepted:
            return CorrectionResult(CorrectionStatus.REJECTED, (), preview.rejected, self._revision)
        before = (self._draft, self._table_cells)
        applied: list[Correction] = []
        for correction in preview.accepted:
            result = _apply_correction(self._draft, self._table_cells, correction)
            if result is None:
                continue
            self._draft, self._table_cells = result
            applied.append(correction)
        if not applied:
            return CorrectionResult(CorrectionStatus.REJECTED, (), preview.rejected, self._revision)
        self._history += (before,)
        self._revision += 1
        rejected = preview.rejected + tuple(
            correction for correction in preview.accepted if correction not in applied
        )
        status = CorrectionStatus.PARTIALLY_APPLIED if rejected else CorrectionStatus.APPLIED
        return CorrectionResult(status, tuple(applied), rejected, self._revision)

    def undo(self) -> bool:
        if not self._history:
            return False
        self._draft, self._table_cells = self._history[-1]
        self._history = self._history[:-1]
        self._revision -= 1
        return True
