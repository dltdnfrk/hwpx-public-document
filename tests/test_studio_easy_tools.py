from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_studio_exposes_easy_hangul_tools_on_enabled_ribbon_tabs() -> None:
    studio = ROOT / "Resources" / "Studio"
    html = (studio / "index.html").read_text(encoding="utf-8")
    script = (studio / "app.js").read_text(encoding="utf-8")
    css = (studio / "styles.css").read_text(encoding="utf-8")

    assert 'src="easy-tools.js"' in html
    assert 'src="app.js"' in html
    assert html.index('src="easy-tools.js"') < html.index('src="app.js"')
    assert 'data-tab="insert"' in html
    assert 'data-tab="table"' in html
    assert 'data-tab="layout"' in html
    assert 'id="insert-tools"' in html
    assert 'id="table-tools"' in html
    assert 'id="layout-tools"' in html
    assert 'data-easy-action="insert-date"' in html
    assert 'data-easy-action="insert-date-range"' in html
    assert 'data-easy-action="insert-currency"' in html
    assert 'data-easy-action="normalize-markers"' in html
    assert 'data-easy-action="insert-my-form"' in html
    assert 'data-easy-action="save-my-form"' in html
    assert 'data-easy-action="insert-table"' in html
    assert 'data-easy-action="add-table-row"' in html
    assert 'data-easy-action="clean-table"' in html
    assert 'data-easy-action="set-table-borders"' in html
    assert 'data-easy-action="set-table-fill"' in html
    assert 'data-easy-action="page-margins"' in html
    assert 'data-easy-action="hanging-indent"' in html
    assert 'data-easy="autosave-interval"' in html
    assert 'toggle-favorite' in script
    assert 'data-easy-action' in script
    assert 'data-easy-action="save-library"' in html
    assert 'data-easy-action="merge-library"' in html
    assert 'aria-labelledby="easy-tool-title"' in html
    assert 'PublicDocumentEasyTools' in script
    assert "saveStudioPrefs" in script
    assert "saveLibraryDocument" in script
    assert "loadLibraryDocument" in script
    assert "localISODate" in script
    assert "revisionTimestamp" in script
    assert "insertTargetIndex" in script
    assert "elementsFromTemplate(plan" in script
    assert "libraryEntries = [" in script
    assert "libraryProjects[project.documentID] = project" in script
    assert "libraryProjects[documentID]" in script
    assert "input.selectedIndex = 0" in script
    assert "value: libraryEntries[0].documentID" in script
    assert "const fields = readEasyFields()" in script
    assert script.index("const fields = readEasyFields()") < script.index("closeDialog(easyToolDialog)")
    assert "종료일은 시작일 이후여야 합니다" in script
    assert "숫자 금액을 입력하세요" in script
    assert "data-easy-table" in script
    assert "isStaleBridgeProject" in script
    assert "revisionAncestors" in script
    assert "applyBridgeProject" in script
    assert "hangingIndentTargetIndex" in script
    assert "element-section-${index + 1}-body" in script
    assert "text: tablePlainText(html)" in script
    assert ".trim() || '표'" not in script
    assert "tablePlainText" in script
    assert "preserveTableMarkup" in script
    assert "tables.length === 1" in script
    assert ".ribbon[hidden]" in css
    assert "--easy-page-pad-top" in css
    assert "disabled aria-disabled=\"true\"" in html
    assert html.count("disabled aria-disabled=\"true\"") == 2
