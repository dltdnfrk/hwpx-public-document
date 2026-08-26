from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "Resources" / "Studio"
ICONS = STUDIO / "icons"

REQUIRED = (
    "icon.svg",
    "icon-16.png",
    "icon-32.png",
    "icon-180.png",
    "icon-192.png",
    "icon-512.png",
    "icon-1024.png",
    "apple-touch-icon.png",
    "favicon.ico",
    "site.webmanifest",
)

PNG_SIZES = {
    "icon-16.png": 16,
    "icon-32.png": 32,
    "icon-180.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
    "icon-1024.png": 1024,
    "apple-touch-icon.png": 180,
}


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_studio_webapp_icon_bundle_files_exist() -> None:
    missing = [name for name in REQUIRED if not (ICONS / name).is_file() or (ICONS / name).stat().st_size == 0]
    assert missing == []


def test_studio_webapp_icon_png_sizes() -> None:
    for name, expected in PNG_SIZES.items():
        width, height = _png_size(ICONS / name)
        assert (width, height) == (expected, expected), name


def test_studio_icon_svg_says_문서작성기() -> None:
    svg = (ICONS / "icon.svg").read_text(encoding="utf-8")
    assert ">문서<" in svg
    assert ">작성기<" in svg


def test_studio_html_wires_the_icon_bundle() -> None:
    html = (STUDIO / "index.html").read_text(encoding="utf-8")
    assert 'rel="icon" href="icons/favicon.ico"' in html
    assert 'type="image/svg+xml" href="icons/icon.svg"' in html
    assert 'rel="apple-touch-icon" href="icons/apple-touch-icon.png"' in html
    assert 'rel="manifest" href="icons/site.webmanifest"' in html
    assert 'name="theme-color" content="#006879"' in html
    assert "manifest-src 'self'" in html


def test_local_webapp_serves_icon_mime_types() -> None:
    import public_document_web as webapp

    assert webapp.MIME_TYPES[".ico"] == "image/vnd.microsoft.icon"
    assert webapp.MIME_TYPES[".webmanifest"] == "application/manifest+json"
