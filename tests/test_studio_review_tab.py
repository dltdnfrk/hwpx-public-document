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


def test_review_tab_button_is_enabled_and_controls_review_tools() -> None:
    html = _html()
    review = _button(html, "검토")
    view = _button(html, "보기")

    assert "disabled" not in review
    assert "aria-disabled" not in review
    assert 'data-tab="review"' in review
    assert 'aria-controls="review-tools"' in review
    assert "disabled" not in view
    assert "aria-disabled" not in view
    assert 'data-tab="view"' in view
    assert 'aria-controls="view-tools"' in view


def test_outline_panel_keeps_template_trust_without_review_widgets() -> None:
    html = _html()
    outline = _block(html, '<aside class="outline-panel"', "</aside>")

    assert "template-governance" in outline
    assert "outline-list" in outline
    assert "class=\"checklist\"" not in outline
    assert "official-rules" not in outline
    assert 'data-action="check"' not in outline


def test_status_bar_uses_preview_page_copy_instead_of_pager_counts() -> None:
    html = _html()

    assert "1쪽 / 1쪽" not in html
    assert "미리보기 1장" in html
    assert "data-page-status" in html


def test_review_tools_panel_hosts_official_rules_check_checklist_and_statutes() -> None:
    html = _html()
    assert 'id="review-tools"' in html
    panel = _block(html, 'id="review-tools"', 'class="workspace"')

    assert "official-rules" in panel
    assert 'data-action="check"' in panel
    assert "data-checklist-consent" in panel
    assert "행정안전부 표준이 아닙니다" in panel
    assert "data-statute-warnings" in panel
    assert "law.go.kr" not in html


def test_home_font_options_use_myungjo_and_gothic_faces() -> None:
    html = _html()
    font = _block(html, 'data-format="fontName"', "</select>")

    assert "AppleMyungjo" in font
    assert ">명조<" in font
    assert "Apple SD Gothic Neo" in font
    assert ">고딕<" in font
    assert "본고딕" not in html
    assert ">바탕<" not in html


def test_check_announce_reads_live_checklist_results() -> None:
    script = (STUDIO / "editor-commands.js").read_text(encoding="utf-8")

    assert "checklistResults" in script
    assert "필수항목 6개 중 4개" not in script


def test_review_and_title_lock_scripts_load_before_app() -> None:
    html = _html()

    assert 'src="review-tab.js"' in html
    assert 'src="title-lock.js"' in html
    assert html.index('src="review-tab.js"') < html.index('src="app.js"')
    assert html.index('src="title-lock.js"') < html.index('src="app.js"')
    assert (STUDIO / "review-tab.js").is_file()
    assert (STUDIO / "title-lock.js").is_file()
    review_tab = (STUDIO / "review-tab.js").read_text(encoding="utf-8")
    title_lock = (STUDIO / "title-lock.js").read_text(encoding="utf-8")
    assert "reviewStatuteCitations" in review_tab
    assert "law.go.kr" not in review_tab
    assert "readOnly" in title_lock
    assert "public-draft" in title_lock


def test_title_lock_applies_after_initial_project_assignment() -> None:
    app = (STUDIO / "app.js").read_text(encoding="utf-8")
    title_lock = (STUDIO / "title-lock.js").read_text(encoding="utf-8")

    assert "store.currentProject = initialProject()" in app
    assert "applyTitleLock" in app
    assert app.index("store.currentProject = initialProject()") < app.index("applyTitleLock")
    assert "public-plan" in title_lock
    assert "public-draft" in title_lock
    assert "readOnly" in title_lock


def test_local_web_policy_labels_are_present_for_blocked_controls() -> None:
    html = _html()
    update = _block(html, 'data-template-action="update-template"', "</div>")
    batch = _block(html, "data-batch-export", "</label>")

    assert "로컬 앱에서만" in update
    assert "로컬 앱에서만" in batch
    assert "로컬 앱에서만" in html
