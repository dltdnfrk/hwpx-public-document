#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from public_document_web.evidence_path import create_evidence_directory


BINARY = ROOT / ".build" / "debug" / "PublicDocumentApp"
CAPABILITIES = ROOT / "Resources" / "Capabilities" / "format-capabilities-1.0.0.json"
FORMATS = ["hwpx", "hwp", "docx", "markdown"]
EXTENSIONS = {"hwpx": "hwpx", "hwp": "hwp", "docx": "docx", "markdown": "md"}
STRUCTURAL_ONLY = {"table-row", "table-cell"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def element(raw: Dict[str, Any], element_id: str, order: int) -> Dict[str, Any]:
    return {
        "elementID": element_id,
        "kind": raw["kind"],
        "order": order,
        "text": raw["text"],
        "contentHTML": raw.get("contentHTML", raw["text"]),
        "inlineIDs": [],
        "styleID": raw.get("styleID", "style-body"),
        "evidenceIDs": [],
    }


def project(raw: Dict[str, Any], case_id: str) -> Dict[str, Any]:
    title = "형식 보존 검증"
    elements = [
        element(
            {
                "kind": "heading",
                "text": title,
                "contentHTML": title,
                "styleID": "style-title",
            },
            "element-title",
            0,
        ),
        element(raw, "element-feature", 1),
    ]
    revision_id = f"revision-{case_id}"
    return {
        "schemaVersion": 1,
        "documentID": f"document-{case_id}",
        "locale": "ko-KR",
        "title": title,
        "currentRevisionID": revision_id,
        "elements": elements,
        "assets": [],
        "styles": [],
        "templateBinding": {
            "templateID": "public-draft",
            "version": "1.0",
            "publishingAuthority": "기관 표준",
            "requiredSections": ["본문"],
            "checklistResults": {},
        },
        "evidenceLinks": [],
        "revisions": [
            {
                "revisionID": revision_id,
                "createdAt": "2026-08-28T15:00:00Z",
                "summary": case_id,
                "elementIDs": [item["elementID"] for item in elements],
            }
        ],
        "history": [],
        "aiProposalHistory": [],
        "providerConfigurations": [],
        "consentGrants": [],
        "redoRevisionIDs": [],
    }


def run_export(
    source: Path,
    destination: Path,
    formats: List[str],
) -> subprocess.CompletedProcess[str]:
    command = [
        str(BINARY),
        "--export-project",
        str(source),
        str(destination),
        "--formats",
        ",".join(formats),
        "--flattening-consent",
    ]
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def inspect_artifact(
    path: Path,
    format_name: str,
    expected_element: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    data = path.read_bytes()
    if format_name == "docx":
        if not data.startswith(b"PK"):
            return "DOCX signature"
        with zipfile.ZipFile(path) as package:
            required = {"word/document.xml", "word/styles.xml", "customXml/item1.xml"}
            if not required.issubset(package.namelist()):
                return "DOCX required parts"
            document = package.read("word/document.xml").decode("utf-8")
            if (
                expected_element
                and expected_element["kind"] == "formula"
                and (
                    '<m:t xml:space="preserve">'
                    + expected_element["text"]
                    + "</m:t>"
                )
                not in document
            ):
                return "DOCX formula whitespace preservation"
            if (
                expected_element
                and expected_element["kind"] == "table"
                and "비고" in expected_element["text"]
                and '<w:gridAfter w:val="1"/>' not in document
            ):
                return "DOCX ragged table gridAfter"
    elif format_name == "hwpx":
        if not data.startswith(b"PK"):
            return "HWPX signature"
        with zipfile.ZipFile(path) as package:
            required = {"mimetype", "Contents/header.xml", "Contents/section0.xml"}
            if not required.issubset(package.namelist()):
                return "HWPX required parts"
    elif format_name == "hwp":
        if not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return "HWP signature"
    elif format_name == "markdown":
        text = data.decode("utf-8")
        if "<!-- public-document" not in text:
            return "Markdown element markers"
    return None


def expected_disposition(
    capabilities: List[str],
    format_name: str,
    matrix: Dict[str, Dict[str, str]],
) -> Tuple[str, List[str]]:
    classes = []
    for capability in capabilities:
        if capability in STRUCTURAL_ONLY:
            continue
        if capability not in matrix:
            raise ValueError(f"fixture declares unknown capability: {capability}")
        classes.append(matrix[capability][format_name])
    if "semantic-loss" in classes:
        return "blocked", classes
    return "published", classes


def write_transcript(
    destination: Path,
    rows: List[Tuple[str, subprocess.CompletedProcess[str]]],
) -> None:
    lines = []
    for label, result in rows:
        lines.extend(
            [
                f"## {label}",
                f"exit={result.returncode}",
                "stdout:",
                result.stdout.rstrip(),
                "stderr:",
                result.stderr.rstrip(),
                "",
            ]
        )
    lines.append("cleanup: no live processes; no temporary directories")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def matrix_run(
    fixture: Dict[str, Any],
    outdir: Path,
    matrix: Dict[str, Dict[str, str]],
    build_result: subprocess.CompletedProcess[str],
) -> int:
    cases = []
    mismatches = []
    transcripts: List[Tuple[str, subprocess.CompletedProcess[str]]] = [
        ("swift build", build_result)
    ]
    for raw_case in fixture["cases"]:
        case_id = raw_case["id"]
        expected_capabilities = raw_case.get("expectedCapabilities")
        if (
            not isinstance(expected_capabilities, list)
            or not expected_capabilities
            or not all(isinstance(item, str) for item in expected_capabilities)
        ):
            raise ValueError(f"{case_id} must declare expectedCapabilities")
        for format_name in FORMATS:
            root = outdir / "artifacts" / case_id / format_name
            root.mkdir(parents=True)
            source = root / "project.json"
            source.write_text(
                json.dumps(project(raw_case["element"], case_id), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            destination = root / "export"
            destination.mkdir()
            result = run_export(source, destination, [format_name])
            transcripts.append((f"{case_id}/{format_name}", result))
            if result.returncode != 0:
                actual = "failed"
                receipt: Dict[str, Any] = {}
                observations: List[Dict[str, Any]] = []
                artifact_error = result.stderr.strip() or "export command failed"
            else:
                receipt = json.loads(result.stdout)
                observations = receipt.get("observedCapabilities") or []
                observed_capabilities = [
                    observation["capability"] for observation in observations
                ]
                expected, classes = expected_disposition(
                    expected_capabilities,
                    format_name,
                    matrix,
                )
                capability_error = (
                    None
                    if observed_capabilities == expected_capabilities
                    else "observed capability inventory differs from fixture"
                )
                actual = (
                    "published"
                    if format_name in (receipt.get("publishedFormats") or [])
                    else "blocked"
                    if format_name in (receipt.get("blockedFormats") or [])
                    else "failed"
                )
                artifact = destination / f"ac05-fixture.{EXTENSIONS[format_name]}"
                artifact_error = (
                    inspect_artifact(artifact, format_name, raw_case["element"])
                    if actual == "published" and artifact.is_file()
                    else None
                )
                if actual == "published" and not artifact.is_file():
                    artifact_error = "published artifact is missing"
                if actual == "blocked" and artifact.exists():
                    artifact_error = "blocked artifact was published"
                if actual != expected or artifact_error or capability_error:
                    mismatches.append(
                        {
                            "case": case_id,
                            "format": format_name,
                            "expected": expected,
                            "actual": actual,
                            "artifactError": artifact_error,
                            "capabilityError": capability_error,
                        }
                    )
                cases.append(
                    {
                        "case": case_id,
                        "format": format_name,
                        "expected": expected,
                        "actual": actual,
                        "classifications": classes,
                        "expectedCapabilities": expected_capabilities,
                        "observedCapabilities": observed_capabilities,
                        "status": "pass"
                        if actual == expected
                        and artifact_error is None
                        and capability_error is None
                        else "fail",
                    }
                )
                continue
            mismatches.append(
                {
                    "case": case_id,
                    "format": format_name,
                    "expected": "receipt",
                    "actual": actual,
                    "artifactError": artifact_error,
                }
            )
            cases.append(
                {
                    "case": case_id,
                    "format": format_name,
                    "expected": "receipt",
                    "actual": actual,
                    "classifications": [],
                    "observedCapabilities": [],
                    "status": "fail",
                }
            )
    output = {
        "status": "pass" if not mismatches else "fail",
        "formats": FORMATS,
        "caseCount": len(fixture["cases"]),
        "cases": cases,
        "mismatches": mismatches,
        "cleanup": "no live processes; no temporary directories",
    }
    (outdir / "matrix.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_transcript(outdir / "transcript.txt", transcripts)
    return 0 if not mismatches else 1


def adversarial_run(
    fixture: Dict[str, Any],
    outdir: Path,
    build_result: subprocess.CompletedProcess[str],
) -> int:
    source = outdir / "project.json"
    source.write_text(
        json.dumps(project(fixture["element"], "adversarial"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    destination = outdir / "export"
    destination.mkdir()
    before = {}
    for format_name in FORMATS:
        path = destination / f"ac05-fixture.{EXTENSIONS[format_name]}"
        path.write_bytes(f"user-owned-{format_name}".encode("utf-8"))
        before[format_name] = sha256(path)
    result = run_export(source, destination, FORMATS)
    write_transcript(
        outdir / "transcript.txt",
        [("swift build", build_result), ("adversarial", result)],
    )
    if result.returncode != 0:
        return 1
    receipt = json.loads(result.stdout)
    after = {
        format_name: sha256(destination / f"ac05-fixture.{EXTENSIONS[format_name]}")
        for format_name in FORMATS
    }
    changed = [name for name in FORMATS if before[name] != after[name]]
    semantic = sorted(
        {
            report["capability"]
            for report in receipt.get("lossReports") or []
            if report["classification"] == "semantic-loss"
        }
    )
    blocked = receipt.get("blockedFormats") or []
    passed = (
        blocked == FORMATS
        and not (receipt.get("publishedFormats") or [])
        and not (receipt.get("failedFormats") or [])
        and not changed
        and {"list-item", "unordered-list"}.issubset(set(semantic))
    )
    output = {
        "status": "pass" if passed else "fail",
        "blockedFormats": blocked,
        "publishedFormats": receipt.get("publishedFormats") or [],
        "failedFormats": receipt.get("failedFormats") or [],
        "semanticLossCapabilities": semantic,
        "changedDestinations": changed,
        "beforeHashes": before,
        "afterHashes": after,
        "cleanup": "no live processes; no temporary directories",
    }
    (outdir / "result.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if passed else 1


def main() -> int:
    args = parse_args()
    args.outdir = create_evidence_directory(args.outdir)
    build_result = subprocess.run(
        ["swift", "build", "--product", "PublicDocumentApp"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if build_result.returncode != 0:
        write_transcript(
            args.outdir / "transcript.txt",
            [("swift build", build_result)],
        )
        return 1
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    capability_resource = json.loads(CAPABILITIES.read_text(encoding="utf-8"))
    matrix = {row["capability"]: row for row in capability_resource["matrix"]}
    if fixture.get("mode") == "semantic-loss-overwrite":
        return adversarial_run(fixture, args.outdir, build_result)
    return matrix_run(fixture, args.outdir, matrix, build_result)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
