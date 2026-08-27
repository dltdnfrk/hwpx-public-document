from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "Resources" / "Studio"


def _html() -> str:
    return (STUDIO / "index.html").read_text(encoding="utf-8")


def _button(html: str, label: str) -> str:
    match = re.search(r"<button\b[^>]*>\s*" + re.escape(label) + r"\s*</button>", html)
    assert match is not None
    return match.group(0)


def _block(html: str, start_token: str, end_token: str) -> str:
    assert start_token in html
    start = html.index(start_token)
    end = html.index(end_token, start)
    return html[start:end]


def test_view_tab_is_enabled_and_hosts_zoom_outline_and_honest_preview() -> None:
    html = _html()
    view = _button(html, "보기")

    assert "disabled" not in view
    assert "aria-disabled" not in view
    assert 'data-tab="view"' in view
    assert 'aria-controls="view-tools"' in view
    assert 'id="view-tools"' in html

    panel = _block(html, 'id="view-tools"', 'class="workspace"')
    assert 'data-view-action="zoom-out"' in panel
    assert 'data-view-action="zoom-in"' in panel
    assert 'data-view-action="zoom-100"' in panel
    assert 'data-view-action="zoom-fit-width"' in panel
    assert 'data-view-action="zoom-fit-page"' in panel
    assert 'data-view-action="toggle-outline"' in panel
    assert "data-view-page-note" in panel
    assert "쪽 나누기 엔진은 없습니다" in panel
    assert "1쪽 / 1쪽" not in html


def test_view_tab_script_owns_zoom_and_preview_sheet_count() -> None:
    html = _html()
    script = (STUDIO / "view-tab.js").read_text(encoding="utf-8")
    commands = (STUDIO / "editor-commands.js").read_text(encoding="utf-8")

    assert 'src="view-tab.js"' in html
    assert html.index('src="view-tab.js"') < html.index('src="app.js"')
    assert "setZoom" in script
    assert "updatePreviewSheets" in script
    assert "previewSheetCount" in script
    assert "미리보기" in script
    assert "1쪽 / 1쪽" not in script
    assert "law.go.kr" not in script
    assert "localStorage" not in script
    assert "editor.style.zoom" not in commands


def test_status_bar_keeps_preview_sheet_copy() -> None:
    html = _html()

    assert "data-page-status" in html
    assert "미리보기 1장" in html
    assert "1쪽 / 1쪽" not in html
    assert "보기 배율" in html
