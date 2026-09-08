#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from public_document_web.evidence_path import create_evidence_directory


BINARY = ROOT / ".build" / "debug" / "PublicDocumentApp"
FIXTURE_BUILDER = ROOT / "tests" / "fireblight_trial_build.py"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["docx"], default="docx")
    parser.add_argument("--outdir", type=Path, required=True)
    return parser.parse_args()


def load_elements() -> List[Dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("fireblight_trial_build", FIXTURE_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("fireblight fixture builder is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    elements = module.elements()
    for order, element in enumerate(elements):
        element["order"] = order
        element.setdefault("inlineIDs", [])
    return elements


def project() -> Dict[str, Any]:
    elements = load_elements()
    revision_id = "revision-fireblight-layout-1"
    return {
        "schemaVersion": 1,
        "documentID": "document-fireblight-policy",
        "locale": "ko-KR",
        "title": "과수화상병 예방체계 고도화를 위한 과원 위생관리 정책 제언",
        "currentRevisionID": revision_id,
        "elements": elements,
        "assets": [],
        "styles": [],
        "templateBinding": {
            "templateID": "public-draft",
            "version": "1.0",
            "publishingAuthority": "기관 표준",
            "requiredSections": ["수신·제목", "본문", "끝·붙임", "발신명의"],
            "checklistResults": {},
        },
        "evidenceLinks": [],
        "revisions": [
            {
                "revisionID": revision_id,
                "createdAt": "2026-08-28T15:00:00Z",
                "summary": "fireblight-layout-regression",
                "elementIDs": [element["elementID"] for element in elements],
            }
        ],
        "history": [],
        "aiProposalHistory": [],
        "providerConfigurations": [],
        "consentGrants": [],
        "redoRevisionIDs": [],
    }


def profile_fingerprint() -> str:
    toolkit_path = ROOT / "Resources/Templates/official-style-toolkit-1.0.0.json"
    tokens_path = ROOT / "Resources/Print/print-tokens-1.0.0.json"
    toolkit_data = toolkit_path.read_bytes()
    tokens_data = tokens_path.read_bytes()
    toolkit = json.loads(toolkit_data)
    tokens = json.loads(tokens_data)
    payload = (
        toolkit["toolkitID"].encode()
        + b"\0"
        + toolkit_data
        + b"\0"
        + tokens["tokenID"].encode()
        + b"\0"
        + tokens_data
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def inspect_docx(path: Path, expected_elements: List[Dict[str, Any]]) -> Dict[str, Any]:
    with zipfile.ZipFile(path) as package:
        document = ElementTree.fromstring(package.read("word/document.xml"))
        manifest = ElementTree.fromstring(package.read("customXml/item1.xml"))
    margin = document.find(".//w:sectPr/w:pgMar", NS)
    if margin is None:
        raise RuntimeError("DOCX page margins are missing")
    namespaced = lambda name: margin.attrib.get(f"{{{W}}}{name}")
    margins = {name: int(namespaced(name) or 0) for name in ("top", "right", "bottom", "left")}
    paragraphs = document.findall(".//w:p", NS)
    texts = [
        "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
        for paragraph in paragraphs
    ]
    marker_paragraphs = [
        text for text in texts if text.startswith(("□ ", "○", "- ", "※", "가. ", "1. "))
    ]
    table_rows = document.findall(".//w:tbl/w:tr", NS)
    expected = {
        "top": 1134,
        "right": 1134,
        "bottom": 567,
        "left": 1134,
    }
    searchable = " ".join(" ".join(text.split()) for text in texts)
    cursor = 0
    missing_or_reordered = []
    for element in sorted(expected_elements, key=lambda item: item["order"]):
        if element["kind"] == "table":
            table = ElementTree.fromstring(f"<root>{element['contentHTML']}</root>")
            expected_chunks = [
                " ".join("".join(cell.itertext()).split())
                for cell in table.iter()
                if cell.tag in {"th", "td"}
            ]
        else:
            expected_chunks = [" ".join(element["text"].split())]
        for expected_text in expected_chunks:
            found = searchable.find(expected_text, cursor)
            if found < 0:
                missing_or_reordered.append(element["elementID"])
                break
            cursor = found + len(expected_text)
    observed_profile = manifest.attrib.get("layout-profile-sha")
    expected_profile = profile_fingerprint()
    content_order_valid = not missing_or_reordered
    return {
        "status": "pass"
        if (
            margins == expected
            and len(table_rows) == 12
            and len(marker_paragraphs) >= 20
            and content_order_valid
            and observed_profile == expected_profile
        )
        else "fail",
        "margins": margins,
        "expectedMargins": expected,
        "paragraphCount": len(paragraphs),
        "markerParagraphCount": len(marker_paragraphs),
        "tableRowCount": len(table_rows),
        "contentOrderValid": content_order_valid,
        "missingOrReorderedElementIDs": missing_or_reordered,
        "layoutProfileSHA256": observed_profile,
        "expectedLayoutProfileSHA256": expected_profile,
        "cleanup": "no live processes; no temporary directories",
    }


def main() -> int:
    args = parse_args()
    args.outdir = create_evidence_directory(args.outdir)
    build_command = ["swift", "build", "--product", "PublicDocumentApp"]
    build_result = subprocess.run(
        build_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    build_transcript = [
        f"$ {' '.join(build_command)}",
        f"exit={build_result.returncode}",
        "stdout:",
        build_result.stdout.rstrip(),
        "stderr:",
        build_result.stderr.rstrip(),
        "",
    ]
    if build_result.returncode != 0:
        (args.outdir / "transcript.txt").write_text(
            "\n".join(build_transcript) + "\n",
            encoding="utf-8",
        )
        return 1
    source = args.outdir / "project.json"
    project_value = project()
    source.write_text(json.dumps(project_value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destination = args.outdir / "export"
    destination.mkdir()
    command = [
        str(BINARY),
        "--export-project",
        str(source),
        str(destination),
        "--formats",
        args.format,
        "--flattening-consent",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    transcript = build_transcript + [
        f"$ {' '.join(command)}",
        f"exit={result.returncode}",
        "stdout:",
        result.stdout.rstrip(),
        "stderr:",
        result.stderr.rstrip(),
        "cleanup: no live processes; no temporary directories",
    ]
    (args.outdir / "transcript.txt").write_text("\n".join(transcript) + "\n", encoding="utf-8")
    if result.returncode != 0:
        return 1
    receipt = json.loads(result.stdout)
    (args.outdir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    files = list(destination.glob("*.docx"))
    if len(files) != 1:
        return 1
    inspection = inspect_docx(files[0], project_value["elements"])
    (args.outdir / "package-inspection.json").write_text(
        json.dumps(inspection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    passed = (
        inspection["status"] == "pass"
        and inspection["layoutProfileSHA256"]
        and receipt.get("failedFormats") in (None, [])
        and receipt.get("publishedFormats") == ["docx"]
    )
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
