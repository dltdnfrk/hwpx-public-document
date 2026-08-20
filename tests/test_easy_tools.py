from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Resources" / "Studio" / "easy-tools.js"


def _eval(expression: str):
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const sandbox = {{ console, PublicDocumentEasyTools: undefined }};
    sandbox.globalThis = sandbox;
    vm.runInNewContext(fs.readFileSync({json.dumps(str(TOOLS))}, 'utf8'), sandbox);
    const tools = sandbox.PublicDocumentEasyTools;
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


def test_normalize_official_markers_promotes_draft_bullets() -> None:
    text = "ㅁ 개요\nㅇ 대상\nㆍ세부\n- 이미 공식\n□ 소제목"
    assert _eval(f"tools.normalizeOfficialMarkers({json.dumps(text)})") == (
        "□ 개요\n○ 대상\n- 세부\n- 이미 공식\n□ 소제목"
    )


def test_format_official_date_and_range() -> None:
    assert _eval("tools.formatOfficialDate(new Date('2026-08-20T00:00:00'))") == "2026. 8. 20."
    assert _eval(
        "tools.formatOfficialDateRange(new Date('2026-08-20T00:00:00'), new Date('2026-12-31T00:00:00'))"
    ) == "2026. 8. 20. ~ 2026. 12. 31."


def test_local_iso_date_keeps_calendar_day_in_korea() -> None:
    assert _eval("tools.localISODate(new Date(2026, 7, 1, 0, 0, 0))") == "2026-08-01"
    assert _eval("tools.localISODate(new Date(2026, 7, 20, 9, 0, 0))") == "2026-08-20"


def test_format_official_date_range_rejects_reversed_bounds() -> None:
    assert _eval(
        "tools.formatOfficialDateRange(new Date('2026-12-31T00:00:00'), new Date('2026-01-01T00:00:00'))"
    ) == ""


def test_number_to_korean_currency_matches_official_reading() -> None:
    assert _eval("tools.numberToKoreanCurrency(12500000)") == "12,500,000원(금일천이백오십만원정)"
    assert _eval("tools.numberToKoreanCurrency(1)") == "1원(금일원정)"
    assert _eval("tools.numberToKoreanCurrency('12,500,000원')") == "12,500,000원(금일천이백오십만원정)"


def test_number_to_korean_currency_rejects_non_numeric_input() -> None:
    assert _eval("tools.numberToKoreanCurrency('abc')") == ""
    assert _eval("tools.numberToKoreanCurrency('')") == ""


def test_clean_pasted_table_trims_cells_and_keeps_alignment() -> None:
    dirty = "<table><tr><th>  기간  </th><td>  2026. 9.  </td></tr><tr><td>  부서\\u00a0팀  </td><td>  안전기획  </td></tr></table>"
    cleaned = _eval(f"tools.cleanPastedTable({json.dumps(dirty)})")
    assert "<th>기간</th>" in cleaned
    assert "<td>2026. 9.</td>" in cleaned
    assert "\u00a0" not in cleaned


def test_table_builders_add_rows_borders_and_fill() -> None:
    table = _eval("tools.createTableHTML(2, 3)")
    assert table.count("<tr>") == 2
    assert table.count("<td>") == 6
    taller = _eval(f"tools.addTableRow({json.dumps(table)})")
    assert taller.count("<tr>") == 3
    bordered = _eval(f"tools.setTableBorders({json.dumps(table)}, 'all')")
    assert "border:1px solid #1d1d1f" in bordered
    filled = _eval(f"tools.setTableCellFill({json.dumps(table)}, 0, 0, '#fff4cc')")
    assert "background:#fff4cc" in filled


def test_table_helpers_accept_genoffice_tbody_markup() -> None:
    tbody = "<tbody><tr><td></td><td></td><td></td></tr></tbody>"
    wrapped = _eval(f"tools.parseTable({json.dumps(tbody)})")
    assert wrapped.startswith("<table")
    assert 'data-easy-table="true"' in wrapped
    taller = _eval(f"tools.addTableRow({json.dumps(tbody)})")
    assert taller.count("<tr>") == 2
    bordered = _eval(f"tools.setTableBorders({json.dumps(tbody)}, 'all')")
    assert "border:1px solid #1d1d1f" in bordered


def test_empty_easy_table_plain_text_matches_docx_cell_binding() -> None:
    bordered = _eval("tools.setTableBorders(tools.createTableHTML(2, 3), 'all')")
    assert _eval(f"tools.tablePlainText({json.dumps(bordered)})") == ""
    filled = _eval(
        "tools.tablePlainText(tools.setTableCellFill("
        "tools.setTableBorders(tools.createTableHTML(1, 2), 'all'), 0, 0, '#fff4cc'))"
    )
    assert filled == ""
    labeled = _eval(
        "tools.tablePlainText('<table data-easy-table=\"true\"><tr><td>기간</td><td>2026. 9.</td></tr></table>')"
    )
    assert labeled == "기간 2026. 9."


def test_hanging_indent_and_page_margins() -> None:
    assert _eval("tools.hangingIndent('둘째 줄부터 맞춰 씁니다.')").startswith("둘째 줄부터")
    assert _eval("tools.hangingIndent('둘째 줄부터 맞춰 씁니다.')").count("\n") == 1
    margins = _eval("tools.pageMargins('narrow')")
    assert margins == {"top": 15, "right": 15, "bottom": 15, "left": 15}
    assert _eval("tools.pageMargins('wide')")["left"] == 30


def test_merge_document_elements_appends_source_sections() -> None:
    current = [
        {"elementID": "element-title", "kind": "heading", "order": 0, "text": "본문"},
        {"elementID": "element-section-1-body", "kind": "paragraph", "order": 1, "text": "○ 유지"},
    ]
    incoming = [
        {"elementID": "element-title", "kind": "heading", "order": 0, "text": "취합원"},
        {"elementID": "element-section-1-heading", "kind": "heading", "order": 1, "text": "□ 경과"},
        {"elementID": "element-section-1-body", "kind": "paragraph", "order": 2, "text": "○ 결과"},
    ]
    merged = _eval(
        f"tools.mergeDocumentElements({json.dumps(current)}, {json.dumps(incoming)}, '취합')"
    )
    assert [item["text"] for item in merged] == ["본문", "○ 유지", "□ 취합", "○ 결과"]
    assert merged[-1]["elementID"].startswith("element-merge-")
