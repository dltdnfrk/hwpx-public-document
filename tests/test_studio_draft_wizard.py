from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "Resources" / "Studio"


def _html() -> str:
    return (STUDIO / "index.html").read_text(encoding="utf-8")


def test_draft_wizard_dialog_and_home_button_are_present() -> None:
    html = _html()

    assert 'data-action="open-draft-wizard"' in html
    assert "절 채우기" in html
    assert 'class="project-inspector draft-wizard"' in html
    assert "data-wizard-fields" in html
    assert "data-wizard-note" in html
    assert "완성 공문을 자동 생성하지 않습니다" in html
    assert 'data-action="apply-draft-wizard"' in html
    assert 'src="draft-wizard.js"' in html
    assert html.index('src="draft-wizard.js"') < html.index('src="app.js"')
    assert html.index('src="template-panel.js"') < html.index('src="draft-wizard.js"')
    assert html.index('src="easy-library.js"') < html.index('src="draft-wizard.js"')
    assert html.index('src="title-lock.js"') < html.index('src="draft-wizard.js"')


def test_draft_wizard_fills_required_sections_without_unlocking_official_title() -> None:
    script = (STUDIO / "draft-wizard.js").read_text(encoding="utf-8")

    assert "openDraftWizard" in script
    assert "applyDraftWizard" in script
    assert "applyCatalogEntry" in script
    assert "requiredSections" in script
    assert "commitProjectElements" in script
    assert "hasOfficialTitleRule" in script
    assert "element-section-${index + 1}-body" in script
    assert "data-project-action" in script
    assert "law.go.kr" not in script
    assert "localStorage" not in script
    assert "온나라" not in script
    assert "문서24" not in script
    assert "행정안전부 표준" not in script
