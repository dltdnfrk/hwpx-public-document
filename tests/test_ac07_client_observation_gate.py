from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.test_ac07_compatibility_evidence import (
    _run_compatibility,
    _verify_compatibility,
)


def test_client_observation_gate_does_not_reuse_another_format(
    tmp_path: Path,
) -> None:
    # Given: every client operation passes except both HWP-specific observations.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact_by_format = {artifact["format"]: artifact for artifact in receipt["artifacts"]}
    client_by_operation = {
        "genoffice-docs-reopen": "genoffice-docs",
        "microsoft-word-reopen": "microsoft-word",
        "hancom-official-reopen": "hancom-official",
        "polaris-office-reopen": "polaris-office",
        "approved-rendering": "public-document-rendering-authority",
        "commonmark-validate": "commonmark-validator",
    }
    observations = []
    for format_name, operations in receipt["requiredClientOperations"].items():
        if format_name == "hwp":
            continue
        artifact = artifact_by_format[format_name]
        evidence = tmp_path / f"{format_name}-client-evidence.txt"
        evidence.write_text(f"opened-{format_name}", encoding="utf-8")
        evidence_hash = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
        for operation in operations:
            observations.append(
                {
                    "observationID": f"observation-{format_name}-{operation}",
                    "clientID": client_by_operation[operation],
                    "clientName": client_by_operation[operation],
                    "clientVersion": "test-1",
                    "clientBuild": "test-build-1",
                    "osVersion": "test-macOS",
                    "osBuild": "test-os-build",
                    "fonts": ["Apple SD Gothic Neo Regular"],
                    "timestamp": "2026-08-09T12:00:00+09:00",
                    "fixtureID": artifact["fixtureID"],
                    "fixtureHash": artifact["fixtureHash"],
                    "format": format_name,
                    "artifactHash": artifact["artifactHash"],
                    "operation": operation,
                    "opened": True,
                    "extensionWarningCount": 0,
                    "expectedTextCount": 3,
                    "observedTextCount": 3,
                    "expectedPageCount": 1,
                    "observedPageCount": 1,
                    "unexpectedBlankPageCount": 0,
                    "evidencePath": evidence.name,
                    "evidenceHash": evidence_hash,
                }
            )
    observation_path = tmp_path / "observations.json"
    observation_path.write_text(json.dumps(observations), encoding="utf-8")

    # When: the complete-looking observation set is merged.
    result = _verify_compatibility(receipt_path, observation_path, check=True)

    # Then: HWP stays independently blocked despite HWPX using the same clients.
    assert json.loads(result.stdout)["clientVerdict"] == "blocked"


def test_legacy_self_authored_pass_verdicts_remain_blocked(tmp_path: Path) -> None:
    # Given: every required operation has only the legacy diagnostics and verdict fields.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact_by_format = {artifact["format"]: artifact for artifact in receipt["artifacts"]}
    client_by_operation = {
        "genoffice-docs-reopen": "genoffice-docs",
        "microsoft-word-reopen": "microsoft-word",
        "hancom-official-reopen": "hancom-official",
        "polaris-office-reopen": "polaris-office",
        "approved-rendering": "public-document-rendering-authority",
        "commonmark-validate": "commonmark-validator",
    }
    observations = []
    for format_name, operations in receipt["requiredClientOperations"].items():
        artifact = artifact_by_format[format_name]
        for operation in operations:
            observations.append(
                {
                    "observationID": f"legacy-{format_name}-{operation}",
                    "clientID": client_by_operation[operation],
                    "clientName": client_by_operation[operation],
                    "clientVersion": "legacy-1",
                    "clientBuild": "legacy-build",
                    "osVersion": "test-macOS",
                    "osBuild": "test-build",
                    "fonts": ["Apple SD Gothic Neo Regular"],
                    "timestamp": "2026-08-09T12:00:00+09:00",
                    "fixtureID": artifact["fixtureID"],
                    "fixtureHash": artifact["fixtureHash"],
                    "format": format_name,
                    "artifactHash": artifact["artifactHash"],
                    "operation": operation,
                    "diagnostics": "legacy producer-authored claim",
                    "verdict": "pass",
                }
            )
    observation_path = tmp_path / "legacy-observations.json"
    observation_path.write_text(json.dumps(observations), encoding="utf-8")

    # When: the legacy array is evaluated without raw assertions or evidence hashes.
    result = _verify_compatibility(receipt_path, observation_path, check=True)

    # Then: self-authored pass labels cannot promote the client gate.
    assert json.loads(result.stdout)["clientVerdict"] == "blocked"


def test_required_client_failure_fails_client_and_overall_verdicts(
    tmp_path: Path,
) -> None:
    # Given: a bound HWP observation records an actual required-client failure.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact = next(item for item in receipt["artifacts"] if item["format"] == "hwp")
    evidence = tmp_path / "polaris-hwp-failure.txt"
    evidence.write_text("opened=false", encoding="utf-8")
    observation = {
        "observationID": "observation-test-polaris-hwp-failure",
        "clientID": "polaris-office",
        "clientName": "Polaris Office",
        "clientVersion": "test-1",
        "clientBuild": "test-build-1",
        "osVersion": "test-macOS",
        "osBuild": "test-os-build",
        "fonts": ["Apple SD Gothic Neo Regular"],
        "timestamp": "2026-08-09T12:00:00+09:00",
        "fixtureID": artifact["fixtureID"],
        "fixtureHash": artifact["fixtureHash"],
        "format": "hwp",
        "artifactHash": artifact["artifactHash"],
        "operation": "polaris-office-reopen",
        "opened": False,
        "extensionWarningCount": 0,
        "expectedTextCount": 3,
        "observedTextCount": 0,
        "expectedPageCount": 1,
        "observedPageCount": 0,
        "unexpectedBlankPageCount": 0,
        "evidencePath": evidence.name,
        "evidenceHash": "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }
    observation_path = tmp_path / "failure.json"
    observation_path.write_text(json.dumps([observation]), encoding="utf-8")

    # When: the failed observation is merged.
    result = _verify_compatibility(receipt_path, observation_path, check=True)
    merged = json.loads(result.stdout)

    # Then: neither the client nor overall verdict is softened to blocked.
    assert merged["clientVerdict"] == "fail"
    assert merged["overallVerdict"] == "fail"


def test_stale_external_evidence_hash_is_rejected(tmp_path: Path) -> None:
    # Given: a raw client observation points at evidence whose claimed hash is stale.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact = receipt["artifacts"][0]
    evidence = tmp_path / "stale-evidence.txt"
    evidence.write_text("current evidence bytes", encoding="utf-8")
    observation = {
        "observationID": "stale-evidence-observation",
        "clientID": "polaris-office",
        "clientName": "Polaris Office",
        "clientVersion": "test-1",
        "clientBuild": "test-build-1",
        "osVersion": "test-macOS",
        "osBuild": "test-os-build",
        "fonts": ["Apple SD Gothic Neo Regular"],
        "timestamp": "2026-08-10T00:00:00+09:00",
        "fixtureID": artifact["fixtureID"],
        "fixtureHash": artifact["fixtureHash"],
        "format": artifact["format"],
        "artifactHash": artifact["artifactHash"],
        "operation": "polaris-office-reopen",
        "opened": True,
        "extensionWarningCount": 0,
        "expectedTextCount": 3,
        "observedTextCount": 3,
        "expectedPageCount": 1,
        "observedPageCount": 1,
        "unexpectedBlankPageCount": 0,
        "evidencePath": evidence.name,
        "evidenceHash": "sha256:" + "0" * 64,
    }
    observation_path = tmp_path / "stale-evidence-observation.json"
    observation_path.write_text(
        json.dumps(
            {
                "visualObservations": [],
                "clientObservations": [observation],
                "externalBlockers": [],
            }
        ),
        encoding="utf-8",
    )

    # When: the bound evidence bytes are hashed by the verifier.
    result = _verify_compatibility(receipt_path, observation_path)

    # Then: the stale evidence is rejected before it can influence a verdict.
    assert result.returncode != 0
    assert "evidenceHash" in result.stderr
