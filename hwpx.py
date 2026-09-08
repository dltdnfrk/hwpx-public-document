from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from public_document.document_models import Draft, HWPXValidation as HWPXValidation


def hwpx_content_hash(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        digest = hashlib.sha256()
        for name in sorted(package.namelist()):
            encoded_name = name.encode("utf-8")
            content = package.read(name)
            digest.update(len(encoded_name).to_bytes(4, "big"))
            digest.update(encoded_name)
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def validate_hwpx(path: Path, draft: Draft) -> HWPXValidation:
    required = {
        "mimetype",
        "version.xml",
        "Contents/content.hpf",
        "Contents/header.xml",
        "Contents/section0.xml",
        "Contents/styles.xml",
        "Contents/metadata.xml",
        "Contents/_rels/section0.xml.rels",
    }
    errors: list[str] = []
    try:
        with zipfile.ZipFile(path) as package:
            members = package.namelist()
            names = set(members)
            if len(members) != len(names):
                return HWPXValidation(False, False, False, False, "", ("duplicate package member names",))
            package_valid = required <= names and package.read("mimetype") == b"application/hwp+zip"
            if not package_valid:
                errors.append("required package parts or mimetype missing")
            parsed = {name: ElementTree.fromstring(package.read(name)) for name in required - {"mimetype"}}
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        return HWPXValidation(False, False, False, False, "", (str(error),))

    content = parsed["Contents/content.hpf"]
    section = parsed["Contents/section0.xml"]
    styles = parsed["Contents/styles.xml"]
    metadata = parsed["Contents/metadata.xml"]
    relationships = parsed["Contents/_rels/section0.xml.rels"]
    profile_presets = {style.attrib["id"] for style in styles if style.attrib.get("id")}
    used_presets = {
        paragraph.attrib.get("preset", "")
        for paragraph in section.iter()
        if paragraph.tag.endswith("}p") and paragraph.attrib.get("paragraph-id")
    }
    document = next((item for item in content if item.tag.endswith("}document")), None)
    schema_profile_valid = content.tag.endswith("}package") and document is not None
    schema_profile_valid = schema_profile_valid and used_presets <= profile_presets
    paragraph_by_id = {
        paragraph.attrib["paragraph-id"]: paragraph
        for paragraph in section.iter()
        if paragraph.tag.endswith("}p") and paragraph.attrib.get("paragraph-id")
    }
    draft_paragraphs = {
        paragraph.paragraph_id: paragraph
        for item in draft.sections
        for paragraph in item.paragraphs
    }
    if set(paragraph_by_id) != set(draft_paragraphs):
        schema_profile_valid = False
    else:
        for paragraph_id, serialized in paragraph_by_id.items():
            expected = draft_paragraphs[paragraph_id]
            serialized_text = "".join(serialized.itertext())
            if serialized_text != expected.text or serialized.attrib.get("status") != expected.status.value:
                schema_profile_valid = False
    if not schema_profile_valid:
        errors.append("schema profile does not declare all paragraph presets")

    evidence_ids = {item.evidence_id for item in draft.evidence}
    serialized_ids = {item.attrib.get("id") for item in metadata.findall("evidence")}
    internal_references_valid = serialized_ids == evidence_ids
    relationship_targets = {
        item.attrib.get("Target")
        for item in relationships
        if item.attrib.get("Target")
    }
    internal_references_valid = internal_references_valid and relationship_targets >= {
        "../metadata.xml",
        "../styles.xml",
    }
    for paragraph in section.iter():
        refs = tuple(filter(None, paragraph.attrib.get("evidence-refs", "").split(",")))
        if any(reference not in evidence_ids for reference in refs):
            internal_references_valid = False
    if not internal_references_valid:
        errors.append("evidence references or package relationships do not resolve")

    serialized_tables = {
        table.attrib.get("table-id"): (
            int(table.attrib.get("rows", "-1")),
            int(table.attrib.get("columns", "-1")),
        )
        for table in section.iter()
        if table.tag.endswith("}tbl") and table.attrib.get("table-id")
    }
    expected_tables = {
        table.table_id: (table.row_count, len(table.columns))
        for table in draft.tables
    }
    if serialized_tables != expected_tables:
        schema_profile_valid = False
        errors.append("serialized table dimensions do not match the semantic model")

    metadata_valid = (
        metadata.attrib.get("spec-id") == "public-document-core"
        and metadata.attrib.get("spec-version") == "1.0"
        and bool(metadata.attrib.get("operation-id", "").strip())
        and document is not None
        and document.attrib.get("document-id") == draft.document_id
        and document.attrib.get("title") == draft.title
        and document.attrib.get("period") == draft.period
        and document.attrib.get("beta-group") == draft.beta_group.value
        and metadata.attrib.get("document-id") == draft.document_id
        and metadata.attrib.get("period") == draft.period
    )
    if not metadata_valid:
        errors.append("metadata does not match the approved document revision")
    return HWPXValidation(
        package_valid,
        schema_profile_valid,
        internal_references_valid,
        metadata_valid,
        hwpx_content_hash(path),
        tuple(errors),
    )
