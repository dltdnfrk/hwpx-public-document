from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "Resources" / "Studio"
ENGINE = STUDIO / "page-engine.js"
PROFILE = STUDIO / "official-layout-profile.js"
TOKENS = ROOT / "Resources" / "Print" / "print-tokens-1.0.0.json"


def _eval(expression: str):
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const sandbox = {{ console, PublicDocumentPageEngine: undefined }};
    sandbox.globalThis = sandbox;
    vm.runInNewContext(fs.readFileSync({json.dumps(str(PROFILE))}, 'utf8'), sandbox);
    vm.runInNewContext(fs.readFileSync({json.dumps(str(ENGINE))}, 'utf8'), sandbox);
    const engine = sandbox.PublicDocumentPageEngine;
    const value = {expression};
    process.stdout.write(JSON.stringify(value));
    """
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _html() -> str:
    return (STUDIO / "index.html").read_text(encoding="utf-8")


def test_page_engine_binds_print_tokens_and_does_not_replace_hwpx() -> None:
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))
    bound = _eval("engine.PRINT_TOKENS")
    metrics = _eval("engine.pageMetrics()")

    assert bound["tokenID"] == tokens["tokenID"] == "print-tokens-1.0.0"
    assert bound["page"]["paper"] == "a4"
    assert bound["page"]["marginMm"] == tokens["page"]["marginMm"]
    assert metrics["paper"] == "a4"
    assert metrics["contentHeightPx"] < metrics["heightPx"]
    assert "HWPX" in tokens["note"]
    assert "한컴 쪽 나누기를 대체하지 않습니다" in _eval("engine.previewCopy(2)")
    assert _eval("engine.statusCopy(2)") == "미리보기 2장"
    assert "1쪽 / 1쪽" not in _eval("engine.previewCopy(1) + engine.statusCopy(1)")


def test_page_engine_paginates_authoring_blocks_instead_of_canvas_height() -> None:
    short = _eval(
        "engine.paginateBlocks(["
        "{id:'t',kind:'heading',text:'제목',styleID:'style-title'},"
        "{id:'h',kind:'heading',text:'1. 개요',styleID:'style-section-heading'},"
        "{id:'p',kind:'paragraph',text:'한 줄 본문',styleID:'style-body'}"
        "])"
    )
    long_text = "공공문서 쪽 나누기 검증용 문장입니다. " * 80
    long = _eval(
        "engine.paginateBlocks(["
        "{id:'t',kind:'heading',text:'제목',styleID:'style-title'},"
        f"{{id:'p',kind:'paragraph',text:{json.dumps(long_text)},styleID:'style-body'}}"
        "])"
    )

    assert short["pageCount"] == 1
    assert short["tokenID"] == "print-tokens-1.0.0"
    assert [block["id"] for block in short["pages"][0]["blocks"]] == ["t", "h", "p"]
    assert long["pageCount"] >= 2
    assert all(page["blocks"] for page in long["pages"])


def test_page_engine_keeps_heading_with_following_body_when_both_fit() -> None:
    filler = "본문을 채워 첫 장을 거의 다 씁니다. " * 40
    layout = _eval(
        "engine.paginateBlocks(["
        f"{{id:'lead',kind:'paragraph',text:{json.dumps(filler)},styleID:'style-body'}},"
        "{id:'h',kind:'heading',text:'2. 추진 배경',styleID:'style-section-heading'},"
        "{id:'b',kind:'paragraph',text:'짧은 배경',styleID:'style-body'}"
        "])"
    )

    heading_pages = [
        index
        for index, page in enumerate(layout["pages"])
        if any(block["id"] == "h" for block in page["blocks"])
    ]
    body_pages = [
        index
        for index, page in enumerate(layout["pages"])
        if any(block["id"] == "b" for block in page["blocks"])
    ]
    assert heading_pages == body_pages
    assert heading_pages


def test_page_engine_uses_project_margins_and_table_rows() -> None:
    layout = _eval(
        "engine.paginateProject({"
        "title:'표 문서',"
        "pageMargins:{top:15,right:15,bottom:15,left:15},"
        "elements:["
        "{elementID:'t',kind:'heading',order:0,text:'제목',styleID:'style-title'},"
        "{elementID:'table',kind:'table',order:1,text:'기간 2026',contentHTML:'<table><tr><th>기간</th><td>2026</td></tr><tr><th>부서</th><td>기획</td></tr></table>',styleID:'style-table'}"
        "]})"
    )
    table = next(block for block in layout["pages"][0]["blocks"] if block["id"] == "table")
    assert layout["metrics"]["marginMm"] == {"top": 15, "right": 15, "bottom": 15, "left": 15}
    assert table["rows"] == 2
    assert layout["pageCount"] == 1


def test_studio_wires_page_engine_before_view_tab() -> None:
    html = _html()
    view_tab = (STUDIO / "view-tab.js").read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    styles = (STUDIO / "styles.css").read_text(encoding="utf-8")

    assert ENGINE.is_file()
    assert 'src="page-engine.js"' in html
    assert html.index('src="page-engine.js"') < html.index('src="view-tab.js"')
    assert html.index('src="view-tab.js"') < html.index('src="app.js"')
    assert "data-page-engine-overlay" in html
    assert "한컴 쪽 나누기를 대체하지 않습니다" in html
    assert "쪽 나누기 엔진은 없습니다" not in html
    assert "1쪽 / 1쪽" not in html
    assert "pageCountForProject" in view_tab
    assert "PublicDocumentPageEngine" in view_tab
    assert "쪽 나누기 엔진은 없습니다" not in view_tab
    assert "canvas 높이 기준" not in view_tab
    assert "localStorage" not in engine
    assert "law.go.kr" not in engine
    assert "1쪽 / 1쪽" not in engine
    assert "page-engine-overlay" in styles
    assert "page-engine-break" in styles



def test_page_engine_builds_a4_preview_sheets_without_mutating_body() -> None:
    long_text = "공공문서 쪽 미리보기 검증용 문장입니다. " * 80
    sheets = _eval(
        "engine.previewSheets(engine.paginateBlocks(["
        "{id:'t',kind:'heading',text:'제목',styleID:'style-title'},"
        f"{{id:'p',kind:'paragraph',text:{json.dumps(long_text)},styleID:'style-body'}}"
        "]))"
    )
    markup = _eval(
        "engine.previewMarkup(engine.paginateBlocks(["
        "{id:'t',kind:'heading',text:'제목',styleID:'style-title'},"
        "{id:'h',kind:'heading',text:'1. 개요',styleID:'style-section-heading'},"
        "{id:'p',kind:'paragraph',text:'한 줄 본문',styleID:'style-body'}"
        "]))"
    )

    assert len(sheets) >= 2
    assert sheets[0]["page"] == 1
    assert "t" in sheets[0]["blockIDs"]
    assert any("제목" in sheet["texts"] for sheet in sheets)
    assert markup.count('class="page-preview-sheet"') >= 1
    assert "제목" in markup
    assert "한 줄 본문" in markup
    assert "page-break" not in markup
    assert "1쪽 / 1쪽" not in markup


def test_studio_hosts_toggleable_page_preview() -> None:
    html = _html()
    view_tab = (STUDIO / "view-tab.js").read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    styles = (STUDIO / "styles.css").read_text(encoding="utf-8")
    panel_start = html.index('id="view-tools"')
    panel = html[panel_start:html.index('class="workspace"', panel_start)]

    assert 'data-view-action="toggle-page-preview"' in panel
    assert "쪽 미리보기" in panel
    assert "data-page-preview" in html
    assert "page-preview-sheet" in styles
    assert "previewSheets" in engine
    assert "previewMarkup" in engine
    assert "togglePagePreview" in view_tab
    assert "data-page-preview" in view_tab
    assert "localStorage" not in engine
    assert "law.go.kr" not in view_tab


def test_page_engine_typesets_official_lines_and_table_cells() -> None:
    markup = _eval(
        "engine.previewMarkup(engine.paginateProject({"
        "title:'조판',"
        "elements:["
        "{elementID:'t',kind:'heading',order:0,text:'조판',styleID:'style-title'},"
        "{elementID:'p',kind:'paragraph',order:1,text:'○ 첫 항목. ○ 둘째 - 세부',styleID:'style-body'},"
        "{elementID:'table',kind:'table',order:2,text:'기간 2026',contentHTML:'<table><tr><th>기간</th><td>2026</td></tr><tr><th>부서</th><td>기획</td></tr></table>',styleID:'style-table'}"
        "]}))"
    )
    assert 'class="official-line hang"' in markup
    assert 'class="official-line detail"' in markup
    assert "<th>기간</th>" in markup
    assert "<td>기획</td>" in markup
    assert "<caption>" not in markup


def test_table_preview_decodes_entities_and_preserves_cell_line_breaks() -> None:
    content_html = (
        "<table><tr><th>구분</th><th>내용</th></tr>"
        "<tr><td>&lt;법령&gt;</td><td>첫째<br>둘째 &amp; 셋째</td></tr></table>"
    )
    markup = _eval(
        "engine.previewMarkup(engine.paginateProject({"
        "title:'표 미리보기',"
        "elements:["
        "{elementID:'t',kind:'heading',order:0,text:'표 미리보기',styleID:'style-title'},"
        "{elementID:'table',kind:'table',order:1,text:'구분 내용',"
        f"contentHTML:{json.dumps(content_html)},styleID:'style-table'}}"
        "]}))"
    )

    assert "<td>&lt;법령&gt;</td>" in markup
    assert "<td>첫째<br>둘째 &amp; 셋째</td>" in markup
    assert "&amp;lt;법령&amp;gt;" not in markup


def test_oversized_table_rows_render_once_across_preview_pages() -> None:
    rows = "".join(f"<tr><td>row-{index}</td></tr>" for index in range(100))
    expression = (
        "engine.paginateProject({"
        "title:'긴 표',"
        "elements:[{"
        "elementID:'table',kind:'table',order:0,text:'긴 표',"
        f"contentHTML:{json.dumps(f'<table>{rows}</table>')},"
        "rows:100,styleID:'style-table'"
        "}]})"
    )
    layout = _eval(expression)
    markup = _eval(f"engine.previewMarkup({json.dumps(layout)})")

    assert layout["pageCount"] >= 2
    assert markup.count("<tr>") == 100
    assert markup.count("row-0") == 1
    assert markup.count("row-99") == 1
    block_ids = [
        page["blocks"][0]["id"]
        for page in layout["pages"]
    ]
    assert len(block_ids) == len(set(block_ids))


def test_heading_stays_with_first_oversized_table_chunk() -> None:
    rows = "".join(f"<tr><td>row-{index}</td></tr>" for index in range(100))
    layout = _eval(
        "engine.paginateBlocks(["
        "{id:'h',kind:'heading',text:'2. 표 결과',styleID:'style-section-heading'},"
        "{id:'table',kind:'table',text:'긴 표',"
        f"contentHTML:{json.dumps(f'<table>{rows}</table>')},"
        "rows:100,styleID:'style-table'}"
        "])"
    )

    heading_page = next(
        page for page in layout["pages"]
        if any(block["id"] == "h" for block in page["blocks"])
    )
    assert [block["id"] for block in heading_page["blocks"]][:2] == ["h", "table"]
