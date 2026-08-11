from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _studio_source() -> tuple[str, str, str]:
    studio = ROOT / "Resources" / "Studio"
    return (
        (studio / "index.html").read_text(encoding="utf-8"),
        (studio / "styles.css").read_text(encoding="utf-8"),
        (studio / "app.js").read_text(encoding="utf-8"),
    )


def test_studio_exposes_screen_reader_and_keyboard_semantics() -> None:
    html, css, script = _studio_source()

    assert '<html lang="ko">' in html
    assert "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'" in html
    assert '<h1 data-element-id="element-title"' in html
    assert 'role="tablist" aria-label="편집 리본 탭"' in html
    assert 'role="tabpanel" aria-label="홈 도구"' in html
    assert 'class="canvas" aria-label="문서 편집 영역" tabindex="0"' in html
    assert 'id="canvas-keyboard-help"' in html
    assert 'aria-live="polite"' in html
    dialog_tags = re.findall(r"<dialog [^>]+>", html)
    assert dialog_tags
    assert all("aria-describedby=" in tag for tag in dialog_tags)
    assert "button:focus-visible" in css
    assert "[contenteditable]:focus-visible" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "prefers-reduced-transparency: reduce" in css
    assert "const openDialog" in script
    assert "const closeDialog" in script
    assert "opener.focus()" in script
    assert "const focusEditorElement" in script
    assert "editor.focusElement(elementID)" in script


def test_studio_uses_the_visible_genoffice_editor_as_the_project_surface() -> None:
    html, css, script = _studio_source()

    assert 'src="../GenOffice/public-document-genoffice.js"' in html
    assert '<public-document-genoffice-editor' in html
    assert 'public-document-genoffice-ready' in script
    assert 'public-document-genoffice-change' in script
    assert '.setProject(project)' in script
    assert '.getElements()' in script
    assert '.command(command, value)' in script
    assert 'structureMatches' in script
    assert 'element.contentHTML ?? previous.contentHTML ?? element.text' in script
    assert '저장하거나 내보낼 수 없습니다.' in script
    assert 'document.execCommand' not in script
    assert '.genoffice-editor' in css


def test_every_ac08_journey_has_named_native_controls_and_announcements() -> None:
    html, _, script = _studio_source()

    required_controls = (
        'data-action="check"',
        'data-action="marker"',
        'data-template-action="update-template"',
        'data-ai-consent',
        'data-ai-proposal-review',
        'data-ai-approve-selected',
        'data-export-consent',
        'name="export-format"',
        'data-batch-export',
        'data-action="cancel-batch-export"',
    )
    assert all(control in html for control in required_controls)
    assert html.count('role="status"') >= 3
    assert 'role="progressbar" aria-label="작성 점검"' in html
    assert 'aria-label="문서별 형식 내보내기 진행률"' in html
    assert "showAIProposal" in script
    assert "showExportResult" in script
    assert "showBatchExportProgress" in script
    assert "announce('선택한 AI 제안을 하나의 새 리비전으로 적용했습니다.')" in script


def test_owned_tokens_and_pinned_docs_fidelity_contract_remain_bound() -> None:
    _, css, _ = _studio_source()
    design = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
    lock = json.loads((ROOT / "provenance" / "upstream-lock.json").read_text(encoding="utf-8"))

    commits = {entry["name"]: entry["commit"] for entry in lock["upstreams"]}
    assert commits["genoffice"] == "d8305ff2dc152593a1ec5639d77e6860c6a512bd"
    assert lock["review"]["status"] == "approved"
    assert "pinned GenOffice Docs editor" in design
    assert "Target WCAG 2.2 and KWCAG AA" in design

    declared_colors = {
        value.lower()
        for value in re.findall(r"#[0-9A-Fa-f]{6}", design)
    }
    css_root = css.partition("}")[0]
    css_colors = {
        value.lower()
        for value in re.findall(r"#[0-9A-Fa-f]{6}", css_root)
    }
    assert css_colors <= declared_colors
