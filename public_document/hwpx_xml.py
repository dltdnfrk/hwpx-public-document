from __future__ import annotations

from typing import Final
from xml.etree import ElementTree

from .document_models import Draft, DocumentTable, _BETA_GROUP_LABELS


_HP: Final = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HC: Final = "http://www.hancom.co.kr/hwpml/2011/core"
_NS: Final = {"hp": _HP, "hc": _HC}
ElementTree.register_namespace("hp", _HP)
ElementTree.register_namespace("hc", _HC)


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
