from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
TYPES = ["추진계획서", "기안문", "보고서", "결과보고서", "업무협조", "회의록"]
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
PRESET_IDS = [
    "style-title",
    "style-section-heading",
    "style-body",
    "style-body-detail",
    "style-reference-note",
    "style-annotation",
    "style-reference",
]
MARKERS = ["□ ", "○", "-", "※", "*"]


def _binary() -> Path:
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    if not binary.is_file():
        subprocess.run(
            ["swift", "build", "--product", "PublicDocumentApp"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    return binary


def _export_samples(tmp_path: Path) -> Path:
    out = tmp_path / "official-samples"
    subprocess.run(
        [str(_binary()), "--export-official-samples", str(out)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return out


def _style_fonts(styles: ElementTree.Element) -> dict[str, tuple[str, str, bool]]:
    found = {}
    for style in styles.findall("w:style", NS):
        style_id = style.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}styleId")
        if style_id not in {"Title", "Heading2", "Normal", "IntenseQuote"}:
            continue
        fonts = style.find("w:rPr/w:rFonts", NS)
        size = style.find("w:rPr/w:sz", NS)
        bold = style.find("w:rPr/w:b", NS) is not None
        ascii_font = fonts.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii") if fonts is not None else ""
        if style_id == "Normal" and (fonts is None or size is None):
            defaults = styles.find("w:docDefaults/w:rPrDefault/w:rPr", NS)
            if defaults is not None:
                fonts = fonts if fonts is not None else defaults.find("w:rFonts", NS)
                size = size if size is not None else defaults.find("w:sz", NS)
                ascii_font = fonts.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii") if fonts is not None else ascii_font
        sz = size.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") if size is not None else ""
        found[style_id] = (ascii_font, sz, bold)
    return found


def test_pdf_sidecar_is_written_beside_official_samples(tmp_path: Path) -> None:
    samples = _export_samples(tmp_path)
    typ = samples / "기안문" / "document.typ"
    assert typ.is_file()
    text = typ.read_text(encoding="utf-8")
    assert "기안문" in text
    assert "HWPX 대체" in text


def test_docx_exports_lock_guidebook_type_and_markers(tmp_path: Path) -> None:
    samples = _export_samples(tmp_path)
    for document_type in TYPES:
        docx = samples / document_type / "ac05-fixture.docx"
        assert docx.is_file(), document_type
        with zipfile.ZipFile(docx) as archive:
            styles = ElementTree.fromstring(archive.read("word/styles.xml"))
            document = ElementTree.fromstring(archive.read("word/document.xml"))
        fonts = _style_fonts(styles)
        assert fonts["Title"] == ("Apple SD Gothic Neo", "32", True)
        assert fonts["Heading2"] == ("Apple SD Gothic Neo", "32", True)
        assert fonts["Normal"][0] == "Apple Myungjo"
        assert fonts["Normal"][1] == "30"
        assert fonts["Normal"][2] is False
        assert fonts["IntenseQuote"] == ("Apple SD Gothic Neo", "24", False)
        paragraphs = []
        for paragraph in document.findall(".//w:p", NS):
            style = paragraph.find("w:pPr/w:pStyle", NS)
            style_id = style.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") if style is not None else ""
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
            paragraphs.append((style_id, text))
        assert any(style_id == "Title" for style_id, _ in paragraphs)
        if document_type == "기안문":
            assert any(style_id == "Heading2" and text[:3].endswith(". ") for style_id, text in paragraphs)
            assert any(style_id == "Normal" and text.startswith("가.") for style_id, text in paragraphs)
        else:
            assert any(style_id == "Heading2" and text.startswith("□ ") for style_id, text in paragraphs)
            assert any(style_id == "Normal" and text.startswith("○") for style_id, text in paragraphs)


def test_hwpx_exports_bind_presets_and_markers(tmp_path: Path) -> None:
    samples = _export_samples(tmp_path)
    for document_type in TYPES:
        hwpx = samples / document_type / "ac05-fixture.hwpx"
        assert hwpx.is_file(), document_type
        assert hwpx.read_bytes()[:4] == b"PK\x03\x04"
        with zipfile.ZipFile(hwpx) as archive:
            names = archive.namelist()
            assert "PublicDocument/style-binding.json" in names
            binding = json.loads(archive.read("PublicDocument/style-binding.json"))
            header = archive.read("Contents/header.xml").decode("utf-8")
            section = archive.read("Contents/section0.xml").decode("utf-8")
        assert binding["default_font"] == "AppleMyungjo"
        assert binding["preset_ids"] == PRESET_IDS
        assert binding["markers"] == MARKERS
        assert binding["statutory_list"] == ["1. ", "가. ", "1) ", "가) ", "(1) ", "(가) ", "① ", "㉮ "]
        assert binding["guidebook_list"] == MARKERS
        assert "헤드라인" in header
        assert "휴먼명조" in header
        assert 'engName="Title"' in header
        engine = ROOT / "Resources" / "Engines" / "rhwp"
        extracted = subprocess.run(
            [str(engine), "export-text", str(hwpx), "--json"],
            check=True,
            capture_output=True,
        )
        receipt = json.loads(extracted.stdout)
        text = "\n".join(page["text"] for page in receipt["pages"])
        if document_type == "기안문":
            assert "1. " in text
            assert "가. " in text
        else:
            assert "□ " in text
            assert "○" in text
