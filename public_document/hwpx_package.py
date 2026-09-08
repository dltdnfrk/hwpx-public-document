from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from pathlib import Path
from threading import Lock

from .document_models import (
    CurrentOfficialRule,
    Draft,
    Evidence,
    GuidedAnswers,
    ManualDraftResult,
    TemplateRegistry,
)
from .draft_builder import build_policy_plan_draft, validate_draft
from .hwp_export import (
    BundledRhwpAdapter,
    DuplicateWriteError,
    HWPAdapter,
    HWPCompatibilityError,
    HWPExportError,
    HWPExportOutcome,
    HWPUnavailableError,
)
from .hwpx_xml import (
    _content_xml,
    _metadata_xml,
    _relationships_xml,
    _section_xml,
    _styles_xml,
)


_EXPORTS: dict[str, tuple[Path, bytes]] = {}
_EXPORT_LOCK = Lock()


def _snapshot_digest(parts: dict[str, bytes]) -> bytes:
    digest = hashlib.sha256()
    for name, content in sorted(parts.items()):
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.digest()


def _check_existing_export(destination: Path, parts: dict[str, bytes]) -> None:
    try:
        with zipfile.ZipFile(destination) as existing:
            members = existing.infolist()
            if len(members) == len(parts) and {item.filename for item in members} == parts.keys():
                if all(existing.read(item) == parts[item.filename] for item in members):
                    return
    except zipfile.BadZipFile as error:
        raise DuplicateWriteError("destination is not a valid HWPX export") from error
    raise DuplicateWriteError("destination already contains a different HWPX export")


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
    snapshot = _snapshot_digest(parts)
    # Keep the process-lifetime operation claim indivisible through publication.
    with _EXPORT_LOCK:
        previous = _EXPORTS.get(operation_id)
        if previous is not None and previous != (destination, snapshot):
            raise DuplicateWriteError("operation_id may write exactly one destination snapshot")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            _check_existing_export(destination, parts)
            _EXPORTS[operation_id] = (destination, snapshot)
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
            try:
                os.link(temporary, destination)
            except FileExistsError:
                _check_existing_export(destination, parts)
        finally:
            temporary.unlink(missing_ok=True)
        _EXPORTS[operation_id] = (destination, snapshot)
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
