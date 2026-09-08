from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "Resources" / "Studio"
TOOLKIT = ROOT / "Resources" / "Templates" / "official-style-toolkit-1.0.0.json"
TOKENS = ROOT / "Resources" / "Print" / "print-tokens-1.0.0.json"
PROFILE = STUDIO / "official-layout-profile.js"


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _eval(expression: str):
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const sandbox = {{ console }};
    sandbox.globalThis = sandbox;
    for (const path of {json.dumps([
        str(PROFILE),
        str(STUDIO / "page-engine.js"),
        str(STUDIO / "easy-tools.js"),
    ])}) {{
      vm.runInNewContext(fs.readFileSync(path, 'utf8'), sandbox);
    }}
    process.stdout.write(JSON.stringify({expression}));
    """
    result = subprocess.run(
        ["node", "--input-type=commonjs", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_studio_profile_is_hash_bound_to_canonical_json_sources() -> None:
    assert PROFILE.is_file()
    profile = _eval("sandbox.PublicDocumentOfficialLayoutProfile")
    toolkit = json.loads(TOOLKIT.read_text(encoding="utf-8"))
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))

    assert profile["schemaVersion"] == 1
    assert profile["profileID"] == "official-layout-profile-1.0.0"
    assert profile["profileFingerprint"].startswith("sha256:")
    assert profile["sources"] == {
        "toolkit": {"id": toolkit["toolkitID"], "sha256": _sha256(TOOLKIT)},
        "printTokens": {"id": tokens["tokenID"], "sha256": _sha256(TOKENS)},
    }
    assert profile["page"] == tokens["page"]
    assert profile["presets"] == toolkit["presets"]
    assert profile["letterSpacing"] == toolkit["operations"]["word-keep"]["letterSpacing"]


def test_preview_and_macros_consume_the_generated_profile() -> None:
    bound = _eval(
        "({"
        "profile: sandbox.PublicDocumentOfficialLayoutProfile,"
        "tokens: sandbox.PublicDocumentPageEngine.PRINT_TOKENS,"
        "margins: sandbox.PublicDocumentEasyTools.pageMargins('official')"
        "})"
    )
    assert bound["tokens"]["tokenID"] == bound["profile"]["sources"]["printTokens"]["id"]
    assert bound["tokens"]["page"] == bound["profile"]["page"]
    assert bound["tokens"]["fonts"] == bound["profile"]["fonts"]
    assert bound["tokens"]["sizesPt"] == bound["profile"]["sizesPt"]
    assert bound["margins"] == bound["profile"]["page"]["marginMm"]


def test_swift_and_hwpx_paths_require_the_canonical_profile() -> None:
    engine = (
        ROOT / "Sources" / "PublicDocumentApp" / "OfficialLayoutEngine.swift"
    ).read_text(encoding="utf-8")
    hwpx = (
        ROOT / "Sources" / "PublicDocumentApp" / "RhwpStyleCompile.swift"
    ).read_text(encoding="utf-8")
    serializers = (
        ROOT / "Sources" / "PublicDocumentApp" / "ExportSerializers.swift"
    ).read_text(encoding="utf-8")

    assert "static func load() throws -> OfficialDocumentProfile" in engine
    assert "static let bundled" not in engine
    assert "sourceFingerprint" in engine
    assert "profile.presets" in hwpx
    assert "private static let stylesXML" not in serializers
    assert "static func docxElement" not in serializers


def test_native_profile_probe_rejects_malformed_tokens_without_output(tmp_path: Path) -> None:
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    output = tmp_path / "profile.json"
    result = subprocess.run(
        [
            str(binary),
            "--official-layout-profile-self-test",
            str(TOOLKIT),
            str(ROOT / "tests" / "fixtures" / "malformed-official-tokens.json"),
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "margin" in result.stderr.lower()
    assert not output.exists()


def test_native_profile_probe_rejects_margins_without_content_area(
    tmp_path: Path,
) -> None:
    binary = ROOT / ".build" / "debug" / "PublicDocumentApp"
    oversized = json.loads(TOKENS.read_text(encoding="utf-8"))
    oversized["page"]["marginMm"] = {
        "top": 200,
        "right": 200,
        "bottom": 200,
        "left": 200,
    }
    tokens = tmp_path / "oversized-margins.json"
    tokens.write_text(json.dumps(oversized), encoding="utf-8")
    output = tmp_path / "profile.json"

    result = subprocess.run(
        [
            str(binary),
            "--official-layout-profile-self-test",
            str(TOOLKIT),
            str(tokens),
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "positive page content area" in result.stderr
    assert not output.exists()
