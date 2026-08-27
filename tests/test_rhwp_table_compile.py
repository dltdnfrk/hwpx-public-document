from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "Sources" / "PublicDocumentApp"


def test_rhwp_export_compiles_simple_tables_into_owpml() -> None:
    compile_source = (SOURCES / "RhwpTableCompile.swift").read_text(encoding="utf-8")
    export_source = (SOURCES / "RhwpExport.swift").read_text(encoding="utf-8")
    matrix = json.loads(
        (ROOT / "Resources" / "Capabilities" / "format-capabilities-1.0.0.json").read_text(
            encoding="utf-8"
        )
    )
    table = next(row for row in matrix["matrix"] if row["capability"] == "table")

    assert "enum RhwpTableCompile" in compile_source
    assert "hp:tbl" in compile_source
    assert "hp:tc" in compile_source
    assert "ExportSerializers.tableRows" in compile_source
    assert "approval-grid" in compile_source
    assert "borderFillIDRef=" in compile_source
    assert 'borderFillIDRef=\\"2\\"' in compile_source
    assert "RhwpTableCompile.apply" in export_source
    assert export_source.index("RhwpStyleCompile.apply") < export_source.index("RhwpTableCompile.apply")
    assert "tableRows" in export_source
    assert "law.go.kr" not in compile_source
    assert table["hwpx"] == "semantic-loss"
