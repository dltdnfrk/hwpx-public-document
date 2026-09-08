#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, List, Tuple
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from public_document_web.evidence_path import create_evidence_directory


TOOLKIT = ROOT / "Resources" / "Templates" / "official-style-toolkit-1.0.0.json"
TOKENS = ROOT / "Resources" / "Print" / "print-tokens-1.0.0.json"
PROFILE_JS = ROOT / "Resources" / "Studio" / "official-layout-profile.js"
PAGE_ENGINE = ROOT / "Resources" / "Studio" / "page-engine.js"
EASY_TOOLS = ROOT / "Resources" / "Studio" / "easy-tools.js"
BINARY = ROOT / ".build" / "debug" / "PublicDocumentApp"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path)
    parser.add_argument("--tokens", type=Path)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    if args.project is None and args.tokens is None:
        parser.error("--project or --tokens is required")
    return args


def run(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )


def write_transcript(
    destination: Path,
    rows: List[Tuple[List[str], subprocess.CompletedProcess[str]]],
    cleanup: str,
) -> None:
    lines = []
    for command, result in rows:
        lines.extend(
            [
                f"$ {' '.join(command)}",
                f"exit={result.returncode}",
                "stdout:",
                result.stdout.rstrip(),
                "stderr:",
                result.stderr.rstrip(),
                "",
            ]
        )
    lines.append(f"cleanup: {cleanup}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_binary(rows: List[Tuple[List[str], subprocess.CompletedProcess[str]]]) -> None:
    command = ["swift", "build", "--product", "PublicDocumentApp"]
    result = run(command)
    rows.append((command, result))
    if result.returncode != 0:
        raise RuntimeError("Swift build failed")


def probe_profile(
    tokens: Path,
    output: Path,
    rows: List[Tuple[List[str], subprocess.CompletedProcess[str]]],
) -> subprocess.CompletedProcess[str]:
    command = [
        str(BINARY),
        "--official-layout-profile-self-test",
        str(TOOLKIT),
        str(tokens),
        str(output),
    ]
    result = run(command)
    rows.append((command, result))
    return result


def javascript_profile() -> dict[str, Any]:
    probe = "1. 배경 ○ 첫 항목. ○ 둘째 함. 1. 표준지침 2. 교육 - 세부 하나 - 세부 둘"
    script = f"""
    const fs = require('fs');
    const vm = require('vm');
    const sandbox = {{ console }};
    sandbox.globalThis = sandbox;
    for (const path of {json.dumps([str(PROFILE_JS), str(PAGE_ENGINE), str(EASY_TOOLS)])}) {{
      vm.runInNewContext(fs.readFileSync(path, 'utf8'), sandbox);
    }}
    const profile = sandbox.PublicDocumentOfficialLayoutProfile;
    const probe = {json.dumps(probe)};
    process.stdout.write(JSON.stringify({{
      preview: profile.profileFingerprint,
      macro: profile.profileFingerprint,
      tokenID: sandbox.PublicDocumentPageEngine.PRINT_TOKENS.tokenID,
      margins: sandbox.PublicDocumentEasyTools.pageMargins('official'),
      macroLines: sandbox.PublicDocumentEasyTools.splitOfficialLines(probe),
      previewLines: sandbox.PublicDocumentPageEngine.splitOfficialLines(probe)
    }}));
    """
    result = run(["node", "--input-type=commonjs", "-e", script])
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def docx_fingerprint(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        root = ElementTree.fromstring(package.read("customXml/item1.xml"))
    value = root.attrib.get("layout-profile-sha")
    if not value:
        raise RuntimeError("DOCX layout-profile-sha is missing")
    return value


def hwpx_fingerprint(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        binding = json.loads(package.read("PublicDocument/style-binding.json"))
    value = binding.get("profile_sha256")
    if not value:
        raise RuntimeError("HWPX profile_sha256 is missing")
    return value


def malformed(
    args: argparse.Namespace,
    rows: List[Tuple[List[str], subprocess.CompletedProcess[str]]],
) -> int:
    probe_output = args.outdir / "profile.json"
    result = probe_profile(args.tokens, probe_output, rows)
    packages = sorted(
        str(path.relative_to(args.outdir))
        for path in args.outdir.rglob("*")
        if path.suffix.lower() in {".docx", ".hwpx", ".hwp"}
    )
    (args.outdir / "empty-output-inventory.json").write_text(
        json.dumps({"packages": packages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cleanup = "no live processes; no temporary directories"
    write_transcript(args.outdir / "transcript.txt", rows, cleanup)
    if result.returncode != 0 and "margin" in result.stderr.lower() and not probe_output.exists() and not packages:
        return 2
    return 1


def parity(
    args: argparse.Namespace,
    rows: List[Tuple[List[str], subprocess.CompletedProcess[str]]],
) -> int:
    native_output = args.outdir / "native-profile.json"
    native_result = probe_profile(TOKENS, native_output, rows)
    if native_result.returncode != 0:
        raise RuntimeError("native profile probe failed")
    native = json.loads(native_output.read_text(encoding="utf-8"))

    export_root = args.outdir / "export"
    export_root.mkdir()
    command = [
        str(BINARY),
        "--export-project",
        str(args.project),
        str(export_root),
        "--formats",
        "docx,hwpx",
        "--flattening-consent",
    ]
    exported = run(command)
    rows.append((command, exported))
    if exported.returncode != 0:
        raise RuntimeError("profile fixture export failed")
    receipt = json.loads(exported.stdout)
    docx = next(export_root.glob("*.docx"))
    hwpx = next(export_root.glob("*.hwpx"))
    javascript = javascript_profile()
    surfaces = {
        "native": native["sourceFingerprint"],
        "docx": docx_fingerprint(docx),
        "hwpx": hwpx_fingerprint(hwpx),
        "preview": javascript["preview"],
        "macro": javascript["macro"],
    }
    profile_sha = native["sourceFingerprint"]
    passed = (
        len(set(surfaces.values())) == 1
        and receipt.get("failedFormats") in (None, [])
        and set(receipt.get("publishedFormats") or []) == {"docx", "hwpx"}
        and javascript["tokenID"] == "print-tokens-1.0.0"
        and javascript["margins"] == {"top": 20, "right": 20, "bottom": 10, "left": 20}
        and native["typesetProbe"]["lines"] == javascript["macroLines"]
        and native["typesetProbe"]["lines"] == javascript["previewLines"]
    )
    cleanup = "no live processes; no temporary directories"
    result = {
        "status": "pass" if passed else "fail",
        "profileSHA256": profile_sha,
        "surfaces": surfaces,
        "publishedFormats": receipt.get("publishedFormats") or [],
        "tokenID": javascript["tokenID"],
        "margins": javascript["margins"],
        "typesetProbe": {
            "native": native["typesetProbe"]["lines"],
            "macro": javascript["macroLines"],
            "preview": javascript["previewLines"],
        },
        "cleanup": cleanup,
    }
    (args.outdir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_transcript(args.outdir / "transcript.txt", rows, cleanup)
    return 0 if passed else 1


def main() -> int:
    args = parse_args()
    args.outdir = create_evidence_directory(args.outdir)
    rows: List[Tuple[List[str], subprocess.CompletedProcess[str]]] = []
    try:
        ensure_binary(rows)
        if args.tokens is not None:
            return malformed(args, rows)
        return parity(args, rows)
    except Exception as error:
        write_transcript(
            args.outdir / "transcript.txt",
            rows,
            "no live processes; no temporary directories",
        )
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
