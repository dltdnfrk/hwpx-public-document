from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
ENVELOPE = ROOT / "Resources" / "Templates" / "catalog-envelope.json"
ENTRIES = ROOT / "Resources" / "Templates" / "catalog-entries.json"
TOOLKIT = ROOT / "Resources" / "Templates" / "official-style-toolkit-1.0.0.json"
PUBLIC_KEY_HEX = "a3ca24b7a40d1be062659a9895287e7732e1cf8bbe7de0e3d23783076c67f2ce"
EXPECTED_TYPES = {
    "추진계획서",
    "기안문",
    "보고서",
    "결과보고서",
    "업무협조",
    "회의록",
}


def test_signed_catalog_has_six_document_types() -> None:
    envelope = json.loads(ENVELOPE.read_text(encoding="utf-8"))
    payload = base64.b64decode(envelope["payload"])
    signature = base64.b64decode(envelope["signature"])
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX)).verify(signature, payload)
    catalog = json.loads(payload.decode("utf-8"))
    types = {entry["documentType"] for entry in catalog["entries"]}
    assert catalog["version"] == "2026.08.2"
    assert len(catalog["entries"]) == 6
    assert types == EXPECTED_TYPES
    source = json.loads(ENTRIES.read_text(encoding="utf-8"))
    assert [entry["templateID"] for entry in source["entries"]] == [
        entry["templateID"] for entry in catalog["entries"]
    ]


def test_official_style_toolkit_locks_guidebook_1100_presets() -> None:
    toolkit = json.loads(TOOLKIT.read_text(encoding="utf-8"))
    assert toolkit["toolkitID"] == "beompeace-guidebook-1100-v1"
    assert toolkit["guidebook"]["filename"] == "범피스1100가이드북.pdf"
    assert toolkit["guidebook"]["pages"] == 91
    assert {
        name: {
            key: preset[key]
            for key in (
                "styleID",
                "hangulFont",
                "macFont",
                "docxStyleId",
                "pointSize",
                "bold",
                "align",
                "marker",
            )
            if key in preset
        }
        for name, preset in toolkit["presets"].items()
    } == {
        "title": {
            "styleID": "style-title",
            "hangulFont": "헤드라인",
            "macFont": "Apple SD Gothic Neo",
            "docxStyleId": "Title",
            "pointSize": 16,
            "bold": True,
            "align": "center",
        },
        "section-heading": {
            "styleID": "style-section-heading",
            "hangulFont": "헤드라인",
            "macFont": "Apple SD Gothic Neo",
            "docxStyleId": "Heading2",
            "pointSize": 16,
            "bold": True,
            "align": "left",
            "marker": "□ ",
        },
        "body": {
            "styleID": "style-body",
            "hangulFont": "휴먼명조",
            "macFont": "AppleMyungjo",
            "docxStyleId": "Normal",
            "pointSize": 15,
            "bold": False,
            "align": "left",
            "marker": "○",
        },
        "body-detail": {
            "styleID": "style-body-detail",
            "hangulFont": "휴먼명조",
            "macFont": "AppleMyungjo",
            "docxStyleId": "Normal",
            "pointSize": 15,
            "bold": False,
            "align": "left",
            "marker": "-",
        },
        "reference": {
            "styleID": "style-reference-note",
            "hangulFont": "맑은고딕",
            "macFont": "Apple SD Gothic Neo",
            "docxStyleId": "IntenseQuote",
            "pointSize": 12,
            "bold": False,
            "align": "left",
            "marker": "※",
        },
        "annotation": {
            "styleID": "style-annotation",
            "hangulFont": "맑은고딕",
            "macFont": "Apple SD Gothic Neo",
            "docxStyleId": "IntenseQuote",
            "pointSize": 12,
            "bold": False,
            "align": "left",
            "marker": "*",
        },
        "reference-box": {
            "styleID": "style-reference",
            "hangulFont": "맑은고딕",
            "macFont": "Apple SD Gothic Neo",
            "docxStyleId": "IntenseQuote",
            "pointSize": 12,
            "bold": False,
            "align": "left",
        },
    }
    assert toolkit["presets"]["title"]["guidebookSpecifiesType"] is False
    assert toolkit["listMarkers"] == ["□ ", "○", "-", "※", "*"]
    assert "ㆍ" not in toolkit["listMarkers"]
