from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import os
import subprocess

import pytest
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


def test_catalog_envelope_security_contract_and_installed_hash() -> None:
    raw_envelope = ENVELOPE.read_bytes()
    assert 0 < len(raw_envelope) <= 262_144
    envelope = json.loads(raw_envelope.decode("utf-8"))
    assert set(envelope) == {"keyID", "payload", "signature"}
    assert envelope["keyID"] == "studio-template-root-2026"

    payload = base64.b64decode(envelope["payload"], validate=True)
    signature = base64.b64decode(envelope["signature"], validate=True)
    assert 0 < len(payload) <= 131_072
    assert base64.b64encode(payload).decode("ascii") == envelope["payload"]
    assert base64.b64encode(signature).decode("ascii") == envelope["signature"]
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX)).verify(signature, payload)

    catalog = json.loads(payload.decode("utf-8"))
    assert payload == json.dumps(
        catalog, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    assert set(catalog) == {"catalogID", "version", "publishedAt", "entries"}
    assert catalog["catalogID"] == "public-document-templates"
    assert len(catalog["entries"]) == 6
    assert {entry["documentType"] for entry in catalog["entries"]} == EXPECTED_TYPES
    assert len({entry["templateID"] for entry in catalog["entries"]}) == 6
    entry_keys = {
        "templateID",
        "version",
        "effectiveDate",
        "publishingAuthority",
        "source",
        "documentType",
        "requiredSections",
        "checklist",
        "officialRules",
        "contentHash",
    }
    rule_keys = {"field", "precedence", "requiredValue", "source"}
    for entry in catalog["entries"]:
        assert set(entry) == entry_keys
        assert all(isinstance(entry[key], str) for key in entry_keys - {
            "requiredSections", "checklist", "officialRules"
        })
        assert all(isinstance(value, str) for value in entry["requiredSections"])
        assert all(isinstance(value, str) for value in entry["checklist"])
        for rule in entry["officialRules"]:
            assert set(rule) == rule_keys
            assert isinstance(rule["field"], str)
            assert isinstance(rule["precedence"], int) and not isinstance(rule["precedence"], bool)
            assert isinstance(rule["requiredValue"], str)
            assert isinstance(rule["source"], str)

    subprocess.run(
        ["swift", "build", "--product", "PublicDocumentApp"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            str(ROOT / ".build" / "debug" / "PublicDocumentApp"),
            "--verify-template-catalog-envelope",
            str(ENVELOPE),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == catalog

    installed_envelope = (
        Path.home()
        / "Applications/PublicDocument.app/Contents/Resources/Templates/catalog-envelope.json"
    )
    if os.environ.get("PUBLIC_DOCUMENT_CHECK_INSTALLED_APP"):
        assert installed_envelope.is_file()
        assert hashlib.sha256(installed_envelope.read_bytes()).digest() == hashlib.sha256(
            raw_envelope
        ).digest()


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
    assert toolkit["guidebookList"] == toolkit["listMarkers"]
    assert toolkit["statutoryList"] == ["1. ", "가. ", "1) ", "가) ", "(1) ", "(가) ", "① ", "㉮ "]
    assert "ㆍ" not in toolkit["listMarkers"]
    installed_toolkit = (
        Path.home()
        / "Applications/PublicDocument.app/Contents/Resources/Templates/official-style-toolkit-1.0.0.json"
    )
    if os.environ.get("PUBLIC_DOCUMENT_CHECK_INSTALLED_APP"):
        assert installed_toolkit.is_file()
        assert hashlib.sha256(installed_toolkit.read_bytes()).digest() == hashlib.sha256(
            TOOLKIT.read_bytes()
        ).digest()


def test_studio_creates_title_heading_and_body_markers() -> None:
    app = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ROOT / "Resources" / "Studio").glob("*.js")))
    css = (ROOT / "Resources/Studio/styles.css").read_text(encoding="utf-8")
    assert "styleID: 'style-title'" in app
    assert "`□ ${section}`" in app
    assert "styleID: 'style-section-heading'" in app
    assert "`○ ${section}`" in app
    assert "styleID: 'style-body'" in app
    assert 'font-size: 16px' in css
    assert 'text-align: center' in css
    assert 'AppleMyungjo' in css
    installed_app = (
        Path.home()
        / "Applications/PublicDocument.app/Contents/Resources/Studio/app.js"
    )
    if os.environ.get("PUBLIC_DOCUMENT_CHECK_INSTALLED_APP"):
        assert installed_app.is_file()
        installed = installed_app.read_text(encoding="utf-8")
        assert "`□ ${section}`" in installed
        assert "`○ ${section}`" in installed


def test_catalog_envelope_rejects_malformed_inputs(tmp_path: Path) -> None:
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    if not binary.is_file():
        subprocess.run(
            ["swift", "build", "--product", "PublicDocumentApp"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    valid = json.loads(ENVELOPE.read_text(encoding="utf-8"))
    cases = {
        "empty": b"",
        "oversized": b"{" + (b"a" * 262_145),
        "extra-key": json.dumps({**valid, "extra": True}).encode("utf-8"),
        "invalid-base64": json.dumps({**valid, "payload": "@@@"}).encode("utf-8"),
        "invalid-signature": json.dumps({
            **valid,
            "signature": ("A" if valid["signature"][0] != "A" else "B") + valid["signature"][1:],
        }).encode("utf-8"),
        "truncated-json": ENVELOPE.read_bytes()[:20],
        "invalid-utf8": b"\xff\xfe{" ,
    }
    for name, payload in cases.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(payload)
        result = subprocess.run(
            [str(binary), "--verify-template-catalog-envelope", str(path)],
            cwd=ROOT,
            capture_output=True,
        )
        assert result.returncode != 0, name


@pytest.mark.skipif(
    not os.environ.get("PUBLIC_DOCUMENT_CHECK_INSTALLED_APP"),
    reason="workspace catalog may differ from ~/Applications/PublicDocument.app",
)
def test_installed_bundle_matches_package_manifest() -> None:
    manifest = ROOT / "dist" / "PublicDocument.app.manifest"
    installed = Path.home() / "Applications/PublicDocument.app"
    assert manifest.is_file()
    assert installed.is_dir()
    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "sourceRevision " + subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    assert lines[1] == "toolkitSha256 " + hashlib.sha256(TOOLKIT.read_bytes()).hexdigest()
    assert lines[2] == "envelopeSha256 " + hashlib.sha256(ENVELOPE.read_bytes()).hexdigest()
    expected = {}
    for line in lines[3:]:
        digest, relative = line.split("  ", 1)
        expected[relative] = digest
    actual = {}
    for path in installed.rglob("*"):
        if path.is_file() and not path.is_symlink():
            actual[path.relative_to(installed).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == expected
