from __future__ import annotations

import json
from pathlib import Path

from tests.test_ac07_compatibility_evidence import (
    _run_compatibility,
    _verify_compatibility,
)


def test_local_verdicts_are_recomputed_instead_of_trusting_receipt_flags(
    tmp_path: Path,
) -> None:
    # Given: a valid local receipt whose producer-authored verdict flags are contradictory.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt.update(
        {
            "structuralVerdict": "fail",
            "semanticVerdict": "fail",
            "visualVerdict": "pass",
            "clientVerdict": "pass",
            "overallVerdict": "pass",
        }
    )
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    observation_path = tmp_path / "empty-observations.json"
    observation_path.write_text(
        json.dumps(
            {
                "visualObservations": [],
                "clientObservations": [],
                "externalBlockers": [],
            }
        ),
        encoding="utf-8",
    )

    # When: the verifier reopens every artifact and re-evaluates every disposition.
    result = _verify_compatibility(receipt_path, observation_path, check=True)

    # Then: local results are restored from evidence while missing external evidence blocks.
    merged = json.loads(result.stdout)
    assert merged["structuralVerdict"] == "pass"
    assert merged["semanticVerdict"] == "pass"
    assert merged["visualVerdict"] == "blocked"
    assert merged["clientVerdict"] == "blocked"
    assert merged["overallVerdict"] == "blocked"


def test_tampered_artifact_validation_receipt_is_rejected(tmp_path: Path) -> None:
    # Given: artifact bytes are intact but the producer validation receipt is altered.
    evidence_root = tmp_path / "compatibility"
    _run_compatibility(evidence_root)
    receipt_path = evidence_root / "compatibility-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["artifacts"][0]["validation"]["validator"] = "self-authored pass"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    observation_path = tmp_path / "empty-observations.json"
    observation_path.write_text("{}", encoding="utf-8")

    # When: the verifier derives a fresh validation receipt from the artifact.
    result = _verify_compatibility(receipt_path, observation_path)

    # Then: the disagreement is rejected rather than preserving the producer verdict.
    assert result.returncode != 0
    assert "artifact validation receipt" in result.stderr
