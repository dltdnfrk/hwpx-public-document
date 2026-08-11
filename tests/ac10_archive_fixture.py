from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import TypedDict


ROOT = Path(__file__).resolve().parents[1]
PRECEDING_CRITERIA = tuple(f"AC-{number:02}" for number in range(1, 10))
EVIDENCE_DOCUMENTS = (
    "ac-01-foundation-evidence.md",
    "ac-02-project-lifecycle-evidence.md",
    "ac-03-guided-template-evidence.md",
    "ac-04-ai-governance-evidence.md",
    "ac-05-format-export-evidence.md",
    "ac-06-batch-export-evidence.md",
    "ac-07-compatibility-evidence.md",
    "ac-08-accessibility-evidence.md",
    "ac-09-performance-evidence.md",
)


class CriterionRow(TypedDict):
    criterion: str
    verdict: str
    evidence: str


class ReleaseManifest(TypedDict):
    schemaVersion: int
    releaseType: str
    formats: list[str]
    criteria: list[CriterionRow]
    functionalSeedVerdict: str
    distributionVerdict: str
    compatibilityBoundary: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory_rows(bundle_root: Path, internal_inventory: Path) -> list[str]:
    artifacts = sorted(
        path
        for root_name in ("PublicDocument.app", "Evidence")
        for path in (bundle_root / root_name).rglob("*")
        if path.is_file() and path != internal_inventory
    )
    return [
        f"{_sha256(path)}  {path.relative_to(bundle_root)}\n" for path in artifacts
    ]


def write_archive_evidence(bundle_root: Path) -> Path:
    evidence = bundle_root / "Evidence"
    acceptance = evidence / "AcceptanceCriteria"
    canonical = evidence / "CanonicalSources"
    provenance = evidence / "Provenance"
    runtime = evidence / "Runtime/ac-10-packaged-app"
    for directory in (acceptance, canonical, provenance, runtime):
        directory.mkdir(parents=True, exist_ok=True)

    criteria: list[CriterionRow] = []
    for criterion, document_name in zip(PRECEDING_CRITERIA, EVIDENCE_DOCUMENTS):
        verdict = "blocked" if criterion == "AC-07" else "pass"
        criteria.append(
            {
                "criterion": criterion,
                "verdict": verdict,
                "evidence": f"Evidence/AcceptanceCriteria/{document_name}",
            }
        )
        _ = shutil.copyfile(
            ROOT / "docs" / document_name, acceptance / document_name
        )
    criteria.append(
        {
            "criterion": "AC-10",
            "verdict": "blocked",
            "evidence": "Evidence/Runtime/ac-10-packaged-app/"
            + "final-publication-verification.json",
        }
    )
    manifest: ReleaseManifest = {
        "schemaVersion": 1,
        "releaseType": "unsigned-local-functional",
        "formats": ["hwpx", "hwp", "docx", "markdown"],
        "criteria": criteria,
        "functionalSeedVerdict": "external-verification-blocked",
        "distributionVerdict": "deferred",
        "compatibilityBoundary": "AC-07 and AC-10 remain blocked.",
    }
    _ = (evidence / "release-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _ = (canonical / "preceding-source.json").write_text(
        '{"criterionRange":"AC-01..AC-09"}\n', encoding="utf-8"
    )
    for name in (
        "upstream-lock.json",
        "sbom.spdx.json",
        "genoffice-docs-port.json",
        "rhwp-dependency-lock.json",
    ):
        _ = shutil.copyfile(ROOT / "provenance" / name, provenance / name)
    _ = (runtime / "final-publication-verification.json").write_text(
        '{"schemaVersion":2,"codesignVerification":"pass",'
        + '"architecture":"arm64"}\n',
        encoding="utf-8",
    )
    internal_inventory = evidence / "SHA256SUMS"
    _ = internal_inventory.write_text(
        "".join(_inventory_rows(bundle_root, internal_inventory)), encoding="utf-8"
    )
    return evidence


def assert_inventory_matches(extraction: Path, inventory: Path) -> None:
    for row in inventory.read_text(encoding="utf-8").splitlines():
        expected, relative_path = row.split("  ", 1)
        artifact = extraction / relative_path
        assert _sha256(artifact) == expected


def assert_manifest_links_and_verdicts(extraction: Path) -> None:
    manifest = extraction / "Evidence/release-manifest.json"
    result = subprocess.run(
        [
            "jq",
            "-r",
            ".criteria[] | [.criterion,.verdict,.evidence] | @tsv",
            str(manifest),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    verdicts: dict[str, str] = {}
    for row in result.stdout.splitlines():
        criterion, verdict, evidence_path = row.split("\t")
        assert evidence_path.startswith("Evidence/")
        assert (extraction / evidence_path).is_file()
        verdicts[criterion] = verdict
    assert verdicts == {
        **{criterion: "pass" for criterion in PRECEDING_CRITERIA},
        "AC-07": "blocked",
        "AC-08": "pass",
        "AC-10": "blocked",
    }
