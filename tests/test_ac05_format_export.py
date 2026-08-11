from __future__ import annotations

import json
import subprocess
import zipfile
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CFB_SECTOR_SIZE, CFB_FREESECT, CFB_ENDOFCHAIN = 512, 0xFFFFFFFF, 0xFFFFFFFE


def _u32le(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def _cfb_conformance_violations(data: bytes) -> list[str]:
    violations: list[str] = []
    sector_count = len(data) // CFB_SECTOR_SIZE - 1
    fat_sector = _u32le(data, 76)
    fat_offset = CFB_SECTOR_SIZE + fat_sector * CFB_SECTOR_SIZE
    fat = tuple(
        _u32le(data, fat_offset + index * 4)
        for index in range(CFB_SECTOR_SIZE // 4)
    )
    if any(entry != CFB_FREESECT for entry in fat[sector_count:]):
        violations.append("FAT entries past EOF are not FREESECT")

    directory_sector = _u32le(data, 48)
    root_offset = CFB_SECTOR_SIZE + directory_sector * CFB_SECTOR_SIZE
    mini_stream_size = _u32le(data, root_offset + 120)
    mini_fat_sector = _u32le(data, 60)
    mini_fat_offset = CFB_SECTOR_SIZE + mini_fat_sector * CFB_SECTOR_SIZE
    occupied_mini_sectors = (mini_stream_size + 63) // 64
    mini_fat_tail = (
        _u32le(data, mini_fat_offset + index * 4)
        for index in range(occupied_mini_sectors, CFB_SECTOR_SIZE // 4)
    )
    if any(entry != CFB_FREESECT for entry in mini_fat_tail):
        violations.append("unused MiniFAT entries are not FREESECT")

    current_directory_sector = directory_sector
    while current_directory_sector != CFB_ENDOFCHAIN:
        directory_offset = CFB_SECTOR_SIZE + current_directory_sector * CFB_SECTOR_SIZE
        for entry_index in range(CFB_SECTOR_SIZE // 128):
            entry_offset = directory_offset + entry_index * 128
            if data[entry_offset + 66] == 0 and data[entry_offset + 68 : entry_offset + 80] != b"\xff" * 12:
                violations.append("unused directory entry lacks NOSTREAM pointers")
        current_directory_sector = fat[current_directory_sector]

    if data[root_offset + 100 : root_offset + 108] != b"\x00" * 8:
        violations.append("root creation time is not zero")
    summary_name = "\u0005HwpSummaryInformation".encode("utf-16le")
    if summary_name not in data:
        violations.append("HwpSummaryInformation lacks its property-set prefix")
    return violations


@lru_cache(maxsize=1)
def _app_binary() -> Path:
    subprocess.run(
        ["swift", "build"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    assert binary.is_file()
    return binary


def test_selected_formats_export_from_one_immutable_snapshot(tmp_path: Path) -> None:
    # Given: the frozen nested authoring fixture and all four selected formats.
    export_root = tmp_path / "selected-formats"

    # When: the native app runs the same export path used by the studio bridge.
    result = subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "all-consented"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(result.stdout)

    # Then: every item is bound to one snapshot and has structural/semantic evidence.
    assert receipt["selectedFormats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert receipt["snapshotRevisionID"] == "revision-ac05-001"
    assert receipt["allAuthoredElementIDsPreserved"] is True
    assert receipt["flatteningConsentRecorded"] is True
    assert receipt["publishedFormats"] == ["docx", "markdown"]
    assert receipt["blockedFormats"] == ["hwpx", "hwp"]
    assert receipt["rhwpCommit"] == "2dced7bfe10c6597cead634264c7c1781c01f1e7"

    artifacts = {item["format"]: export_root / item["fileName"] for item in receipt["results"]}
    assert artifacts["docx"].read_bytes().startswith(b"PK")
    markdown = artifacts["markdown"].read_text(encoding="utf-8")
    assert "# 2026년 생활안전 추진계획" in markdown
    assert "<table>" in markdown and "<th>추진 기간</th>" in markdown
    with zipfile.ZipFile(artifacts["docx"]) as package:
        assert "word/document.xml" in package.namelist()


def test_pinned_rhwp_exports_editable_text_without_silent_empty_page(tmp_path: Path) -> None:
    # Given: a text-only fixture within the pinned public-document adapter capability.
    export_root = tmp_path / "hwp-family"

    # When: HWPX and HWP are exported through rhwp and verified by extracted text.
    result = subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "basic-hwp-family"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(result.stdout)

    # Then: both editable artifacts publish, and neither can pass with an empty page.
    assert receipt["publishedFormats"] == ["hwpx", "hwp"]
    assert receipt["blockedFormats"] == []
    hwpx = export_root / "ac05-fixture.hwpx"
    hwp = export_root / "ac05-fixture.hwp"
    assert hwpx.read_bytes().startswith(b"PK")
    assert hwp.read_bytes().startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    with zipfile.ZipFile(hwpx) as package:
        assert package.read("mimetype") == b"application/hwp+zip"
    engine = ROOT / "Resources" / "Engines" / "rhwp"
    for artifact in (hwpx, hwp):
        extracted = subprocess.run(
            [str(engine), "export-text", str(artifact), "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        pages = json.loads(extracted.stdout)["pages"]
        assert "2026년 생활안전 추진계획" in "\n".join(page["text"] for page in pages)


def test_pinned_rhwp_hwp_has_strict_cfb_metadata(tmp_path: Path) -> None:
    # Given: the text-only HWP fixture exported through the pinned engine.
    export_root = tmp_path / "strict-cfb"
    subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "basic-hwp-family"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # When: normative allocator and property-set metadata are inspected.
    violations = _cfb_conformance_violations((export_root / "ac05-fixture.hwp").read_bytes())

    # Then: the generated compound file contains no strict-client rejection trigger.
    assert violations == []


def test_pinned_rhwp_materializes_native_page_border_slots(tmp_path: Path) -> None:
    # Given: an HWPX fixture whose section declares only the BOTH page-border slot.
    export_root = tmp_path / "page-border-slots"
    subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "basic-hwp-family"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # When: the generated HWP record inventory is inspected.
    inventory = subprocess.run(
        [
            str(ROOT / "Resources/Engines/rhwp"),
            "hwp5-inventory",
            str(export_root / "ac05-fixture.hwp"),
            "--format",
            "jsonl",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    records = [json.loads(line) for line in inventory.stdout.splitlines()]

    # Then: the positional BOTH, EVEN, and ODD records all exist.
    assert sum(record["tag_name"] == "PAGE_BORDER_FILL" for record in records) == 3


def test_pinned_rhwp_uses_hwp_51_section_def_envelope(tmp_path: Path) -> None:
    # Given: the HWP 5.1 text fixture exported through the patched converter.
    export_root = tmp_path / "section-def-envelope"
    subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "basic-hwp-family"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # When: the generated HWP record inventory is inspected.
    inventory = subprocess.run(
        [
            str(ROOT / "Resources" / "Engines" / "rhwp"),
            "hwp5-inventory",
            str(export_root / "ac05-fixture.hwp"),
            "--format",
            "jsonl",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    records = [json.loads(line) for line in inventory.stdout.splitlines()]
    section_defs = [
        record
        for record in records
        if record["tag_name"] == "CTRL_HEADER"
        and record.get("control_name") == "SectionDef"
    ]

    # Then: every SectionDef uses the native HWP 5.1 47-byte envelope.
    assert section_defs
    assert {record["size"] for record in section_defs} == {47}


def test_visual_flattening_is_blocked_until_this_export_is_consented(tmp_path: Path) -> None:
    # Given: Markdown is selected for a fixture with an inline keep-together feature.
    export_root = tmp_path / "consent-required"

    # When: the user has not consented to this export's visual flattening.
    result = subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "markdown-unconsented"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(result.stdout)

    # Then: no artifact is published and the loss report names the exact element path.
    assert receipt["publishedFormats"] == []
    assert receipt["blockedFormats"] == ["markdown"]
    assert receipt["lossReports"] == [
        {
            "capability": "keep-together", "classification": "visual-only-flattening",
            "elementID": "element-summary-body",
            "elementPath": "elements/3/inlines/inline-summary-keep",
            "evidenceSource": "preflight-policy",
            "fallback": "문구 묶음 배치는 생략하고 텍스트와 강조를 편집 가능하게 보존합니다.",
            "format": "markdown",
            "requiresConsent": True,
        }
    ]
    assert list(export_root.glob("*.md")) == []


def test_semantic_loss_blocks_only_the_affected_format(tmp_path: Path) -> None:
    # Given: a frozen fixture containing an unsupported future semantic element.
    export_root = tmp_path / "semantic-block"

    # When: DOCX and Markdown are requested together.
    result = subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "mixed-semantic-block"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(result.stdout)

    # Then: DOCX remains publishable while Markdown receives a precise blocking report.
    assert (receipt["publishedFormats"], receipt["blockedFormats"]) == (["docx"], ["markdown"])
    assert receipt["lossReports"][0]["capability"] == "formula"
    assert receipt["lossReports"][0]["classification"] == "semantic-loss"
    assert receipt["lossReports"][0]["elementID"] == "element-formula-001"
    assert receipt["lossReports"][0]["elementPath"] == "elements/14"
    assert (export_root / "ac05-fixture.docx").is_file()
    assert not (export_root / "ac05-fixture.md").exists()


def test_bound_authoring_universe_reports_every_frozen_loss_capability(
    tmp_path: Path,
) -> None:
    # Given: the executable fixture that contains the frozen atomic and nested universe.
    export_root = tmp_path / "authoring-universe"

    # When: all formats are preflighted with per-export visual flattening consent.
    result = subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "authoring-universe"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(result.stdout)
    reports = receipt["lossReports"]
    observed_capabilities = {report["capability"] for report in reports}

    # Then: semantic blockers are explicit, and every non-lossless frozen capability has
    # a concrete source element/path instead of being inferred from the static matrix.
    assert receipt["selectedFormats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert receipt["publishedFormats"] == []
    assert receipt["blockedFormats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert receipt["failedFormats"] == []
    assert receipt["fixtureHash"] == receipt["snapshotHash"]
    assert receipt["flatteningConsentFormats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert receipt["observedFrozenCombinations"] == [
        "paragraph+strong+emphasis+underline",
        "paragraph+keep-together",
        "unordered-list+list-item+strong",
        "table+table-row+table-cell+strong",
        "approval-grid+table-row+table-cell",
        "review-marker+strong",
    ]
    observed = {
        (entry["capability"], entry["elementID"], entry["elementPath"])
        for entry in receipt["observedCapabilities"]
    }
    assert (
        "font-face",
        "element-rich-paragraph",
        "elements/2/inlines/inline-paragraph-font",
    ) in observed
    assert (
        "unordered-list",
        "element-unordered-list",
        "elements/4/lists/0",
    ) in observed
    assert {
        "metadata", "heading", "table", "review-marker", "approval-grid", "formula",
        "strong", "emphasis", "underline", "font-face", "font-size", "keep-together",
        "list-item", "unordered-list", "rich-inline", "table+rich-inline",
    } <= observed_capabilities
    assert all(
        report["elementID"]
        and report["elementPath"].startswith("elements/")
        and report["capability"]
        for report in reports
    )


def test_visual_only_unconsented_fixture_blocks_every_selected_format(
    tmp_path: Path,
) -> None:
    # Given: a visual-only fixture selected for every format without export consent.
    export_root = tmp_path / "visual-unconsented"

    # When: the bound executable preflight evaluates the request.
    result = subprocess.run(
        [str(_app_binary()), "--export-self-test", str(export_root), "visual-unconsented"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    receipt = json.loads(result.stdout)

    # Then: every format is blocked only by explicit visual-loss consent policy.
    assert receipt["selectedFormats"] == ["hwpx", "hwp", "docx", "markdown"]
    assert receipt["publishedFormats"] == []
    assert receipt["blockedFormats"] == receipt["selectedFormats"]
    assert receipt["failedFormats"] == []
    assert receipt["flatteningConsentRecorded"] is False
    assert receipt["flatteningConsentFormats"] == []
    assert receipt["lossReports"]
    assert {report["format"] for report in receipt["lossReports"]} == {
        "hwpx", "hwp", "docx", "markdown",
    }
    assert all(
        report["classification"] == "visual-only-flattening"
        and report["requiresConsent"] is True
        for report in receipt["lossReports"]
    )
    assert list(export_root.glob("ac05-fixture.*")) == []


def test_studio_exposes_selected_format_and_loss_consent_controls() -> None:
    # Given: the shipped editor and native bridge sources.
    html = (ROOT / "Resources" / "Studio" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "Resources" / "Studio" / "app.js").read_text(encoding="utf-8")
    host = (ROOT / "Sources" / "PublicDocumentApp" / "main.swift").read_text(encoding="utf-8")

    # When/Then: selection and consent are explicit and export crosses the native bridge.
    for format_name in ("hwpx", "hwp", "docx", "markdown"):
        assert f'value="{format_name}"' in html
    assert "내보내기별 시각 변환 동의" in html
    assert "projectBridge('export'" in script
    assert 'case "export":' in host


def test_frozen_manifest_and_matrix_cover_every_authorable_combination() -> None:
    # Given: the app-versioned authoring manifest and matching format matrix.
    capability_root = ROOT / "Resources" / "Capabilities"
    authoring = json.loads((capability_root / "authoring-capabilities-1.0.0.json").read_text())
    matrix = json.loads((capability_root / "format-capabilities-1.0.0.json").read_text())

    # When: every atomic and nested authoring capability is projected to each format.
    matrix_by_capability = {row["capability"]: row for row in matrix["matrix"]}
    required = {element["id"] for element in authoring["elements"] if element["id"] != "unordered-list"}
    required.update({"rich-inline", "unordered-list", "table+rich-inline"})

    # Then: the matrix is exhaustive and uses only the three governed loss classes.
    assert authoring["manifestVersion"] == matrix["manifestVersion"] == "1.0.0"
    assert required <= matrix_by_capability.keys()
    allowed = set(matrix["classifications"])
    for row in matrix_by_capability.values():
        assert {row[format_name] for format_name in ("hwpx", "hwp", "docx", "markdown")} <= allowed
    assert authoring["frozenCombinations"]
