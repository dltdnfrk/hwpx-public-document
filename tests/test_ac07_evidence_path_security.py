from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.test_ac07_compatibility_evidence import (
    _run_compatibility,
    _verify_compatibility,
)


def test_observation_evidence_symlink_outside_root_is_rejected(
    tmp_path: Path,
) -> None:
    # Given: an otherwise complete client observation names an in-root symlink to outside bytes.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact = receipt["artifacts"][0]
    observation_root = tmp_path / "observations"
    observation_root.mkdir()
    outside = tmp_path / "outside-observation-evidence.txt"
    outside.write_text("outside evidence", encoding="utf-8")
    (observation_root / "linked-evidence.txt").symlink_to(outside)
    observation = {
        "observationID": "symlink-out-observation",
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
        "evidencePath": "linked-evidence.txt",
        "evidenceHash": "sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    observation_path = observation_root / "observations.json"
    observation_path.write_text(
        json.dumps({"clientObservations": [observation]}), encoding="utf-8"
    )

    # When: the verifier resolves the evidence path before reading it.
    result = _verify_compatibility(receipt_path, observation_path)

    # Then: the symlink escape is rejected even though its target hash is accurate.
    assert result.returncode != 0
    assert "evidence path escapes root" in result.stderr


def test_artifact_symlink_outside_receipt_root_is_rejected(tmp_path: Path) -> None:
    # Given: a receipt artifact path is replaced by a symlink to identical outside bytes.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    artifact_path = evidence_root / receipt["artifacts"][0]["relativePath"]
    outside = tmp_path / "outside-artifact"
    artifact_path.replace(outside)
    artifact_path.symlink_to(outside)
    observation_path = tmp_path / "empty-observations.json"
    observation_path.write_text("{}", encoding="utf-8")

    # When: local structural and semantic evidence is recalculated.
    result = _verify_compatibility(receipt_path, observation_path)

    # Then: artifact identity cannot be satisfied through an out-of-root symlink.
    assert result.returncode != 0
    assert "evidence path escapes root" in result.stderr
