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
    assert toolkit["presets"]["title"]["guidebookSpecifiesType"] is False
    assert toolkit["presets"]["section-heading"]["hangulFont"] == "헤드라인"
    assert toolkit["presets"]["section-heading"]["pointSize"] == 16
    assert toolkit["presets"]["section-heading"]["marker"] == "□"
    assert toolkit["presets"]["body"]["hangulFont"] == "휴먼명조"
    assert toolkit["presets"]["body"]["pointSize"] == 15
    assert toolkit["presets"]["body-detail"]["marker"] == "-"
    assert toolkit["presets"]["reference"]["hangulFont"] == "맑은고딕"
    assert toolkit["presets"]["reference"]["pointSize"] == 12
    assert toolkit["presets"]["annotation"]["marker"] == "*"
    assert toolkit["listMarkers"] == ["□", "○", "-", "※", "*"]
    assert "ㆍ" not in toolkit["listMarkers"]
