from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.test_ac07_compatibility_evidence import (
    _run_compatibility,
    _verify_compatibility,
)


def test_complete_raw_visual_and_client_observations_promote_overall_pass(
    tmp_path: Path,
) -> None:
    # Given: every locally validated artifact has complete visual and client raw evidence.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    client_by_operation = {
        "genoffice-docs-reopen": "genoffice-docs",
        "microsoft-word-reopen": "microsoft-word",
        "hancom-official-reopen": "hancom-official",
        "polaris-office-reopen": "polaris-office",
        "approved-rendering": "public-document-rendering-authority",
        "commonmark-validate": "commonmark-validator",
    }
    visual_observations = []
    client_observations = []
    for artifact in receipt["artifacts"]:
        evidence = tmp_path / f"{artifact['format']}.txt"
        evidence.write_text(f"evidence-{artifact['format']}", encoding="utf-8")
        evidence_hash = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
        environment = {
            "clientName": "Synthetic Compatibility Client",
            "clientVersion": "1.0",
            "clientBuild": "build-1",
            "osVersion": "test-macOS",
            "osBuild": "test-build",
            "fonts": ["Apple SD Gothic Neo Regular"],
            "timestamp": "2026-08-10T00:00:00+09:00",
            "fixtureID": artifact["fixtureID"],
            "fixtureHash": artifact["fixtureHash"],
            "format": artifact["format"],
            "artifactHash": artifact["artifactHash"],
            "expectedPageCount": 1,
            "observedPageCount": 1,
            "evidencePath": evidence.name,
            "evidenceHash": evidence_hash,
        }
        visual_observations.append(
            {
                **environment,
                "observationID": f"visual-{artifact['format']}",
                "toolID": "synthetic-visual-checker",
                "missingAuthoredElementIDs": [],
                "unexpectedBlankPageNumbers": [],
                "textBoundsCoverage": 1.0,
            }
        )
        for operation in receipt["requiredClientOperations"][artifact["format"]]:
            client_observations.append(
                {
                    **environment,
                    "observationID": f"client-{artifact['format']}-{operation}",
                    "clientID": client_by_operation[operation],
                    "operation": operation,
                    "opened": True,
                    "extensionWarningCount": 0,
                    "expectedTextCount": 3,
                    "observedTextCount": 3,
                    "unexpectedBlankPageCount": 0,
                }
            )
    observation_path = tmp_path / "observations.json"
    observation_path.write_text(
        json.dumps(
            {
                "visualObservations": visual_observations,
                "clientObservations": client_observations,
                "externalBlockers": [],
            }
        ),
        encoding="utf-8",
    )

    # When: the raw evidence envelope is evaluated against the frozen corpus.
    result = _verify_compatibility(receipt_path, observation_path, check=True)

    # Then: every independently recomputed verdict is a pass.
    merged = json.loads(result.stdout)
    assert merged["visualVerdict"] == "pass"
    assert merged["clientVerdict"] == "pass"
    assert merged["overallVerdict"] == "pass"


def test_visual_failure_wins_over_a_structured_client_blocker(tmp_path: Path) -> None:
    # Given: one visual raw assertion fails while a client operation is externally blocked.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact = receipt["artifacts"][0]
    evidence = tmp_path / "visual-failure.txt"
    evidence.write_text("coverage=0.5", encoding="utf-8")
    evidence_hash = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
    visual = {
        "observationID": "visual-failure-observation",
        "toolID": "synthetic-visual-checker",
        "clientName": "Synthetic Compatibility Client",
        "clientVersion": "1.0",
        "clientBuild": "build-1",
        "osVersion": "test-macOS",
        "osBuild": "test-build",
        "fonts": ["Apple SD Gothic Neo Regular"],
        "timestamp": "2026-08-10T00:00:00+09:00",
        "fixtureID": artifact["fixtureID"],
        "fixtureHash": artifact["fixtureHash"],
        "format": artifact["format"],
        "artifactHash": artifact["artifactHash"],
        "expectedPageCount": 1,
        "observedPageCount": 1,
        "missingAuthoredElementIDs": [],
        "unexpectedBlankPageNumbers": [],
        "textBoundsCoverage": 0.5,
        "evidencePath": evidence.name,
        "evidenceHash": evidence_hash,
    }
    operation = receipt["requiredClientOperations"][artifact["format"]][0]
    blocker = {
        "blockerID": "client-environment-unavailable",
        "verdictClass": "client",
        "fixtureID": artifact["fixtureID"],
        "fixtureHash": artifact["fixtureHash"],
        "format": artifact["format"],
        "artifactHash": artifact["artifactHash"],
        "operation": operation,
        "code": "console-locked",
        "status": "BLOCKED",
        "observedAt": "2026-08-10T00:00:00Z",
        "detail": "synthetic external blocker",
        "evidence": [{"path": evidence.name, "sha256": evidence_hash}],
    }
    observation_path = tmp_path / "visual-failure.json"
    observation_path.write_text(
        json.dumps(
            {
                "visualObservations": [visual],
                "clientObservations": [],
                "externalBlockers": [blocker],
            }
        ),
        encoding="utf-8",
    )

    # When: failure and blocker states are aggregated independently.
    result = _verify_compatibility(receipt_path, observation_path, check=True)

    # Then: FAIL outranks BLOCKED and the blocker remains a separate structured record.
    merged = json.loads(result.stdout)
    assert merged["visualVerdict"] == "fail"
    assert merged["clientVerdict"] == "blocked"
    assert merged["overallVerdict"] == "fail"
    assert merged["externalBlockers"] == [blocker]


def test_structured_blocker_requires_artifact_and_evidence_bindings(
    tmp_path: Path,
) -> None:
    # Given: a required client operation has a current raw blocker bound to exact evidence.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact = receipt["artifacts"][0]
    blocker_evidence = tmp_path / "client-unavailable.json"
    blocker_evidence.write_text('{"available":false}', encoding="utf-8")
    blocker = {
        "blockerID": "hancom-hwpx-unavailable",
        "verdictClass": "client",
        "fixtureID": artifact["fixtureID"],
        "fixtureHash": artifact["fixtureHash"],
        "format": artifact["format"],
        "artifactHash": artifact["artifactHash"],
        "operation": "hancom-official-reopen",
        "code": "required-client-unavailable",
        "status": "BLOCKED",
        "observedAt": "2026-08-10T00:00:00Z",
        "detail": "Official Hancom client is not installed.",
        "evidence": [
            {
                "path": blocker_evidence.name,
                "sha256": "sha256:"
                + hashlib.sha256(blocker_evidence.read_bytes()).hexdigest(),
            }
        ],
    }
    observation_path = tmp_path / "structured-blocker.json"
    observation_path.write_text(
        json.dumps({"externalBlockers": [blocker]}), encoding="utf-8"
    )

    # When: the blocker is evaluated with no self-authored verdict shortcut.
    result = _verify_compatibility(receipt_path, observation_path, check=True)

    # Then: it remains structured, hash-bound, and produces a blocked client verdict.
    merged = json.loads(result.stdout)
    assert merged["clientVerdict"] == "blocked"
    assert merged["overallVerdict"] == "blocked"
    assert merged["externalBlockers"] == [blocker]
