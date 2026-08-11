from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "output" / "ac-07" / "final-release-bound.rNZOkU"


def test_final_root_binds_frozen_runtime_and_only_external_blockers() -> None:
    # Given: the canonical AC-07 root was generated after the GenOffice runtime freeze.
    runtime_binding = json.loads((EVIDENCE_ROOT / "runtime-binding.json").read_text())
    observed = json.loads((EVIDENCE_ROOT / "observed-receipt.json").read_text())

    # When: runtime identity and recomputed compatibility verdicts are inspected.
    verdicts = {
        field: observed[field]
        for field in (
            "structuralVerdict",
            "semanticVerdict",
            "visualVerdict",
            "clientVerdict",
            "overallVerdict",
        )
    }

    # Then: all locally reproducible gates pass and only external facts block completion.
    assert runtime_binding["allExpectedHashesMatch"] is True
    assert verdicts == {
        "structuralVerdict": "pass",
        "semanticVerdict": "pass",
        "visualVerdict": "pass",
        "clientVerdict": "blocked",
        "overallVerdict": "blocked",
    }
    assert len(observed["externalBlockers"]) == 6
    assert {blocker["code"] for blocker in observed["externalBlockers"]} == {
        "authority-approval-pending",
        "console-locked",
        "required-client-unavailable",
    }


def test_final_commonmark_receipt_projects_to_raw_client_pass() -> None:
    # Given: the copied Pandoc receipt records a complete exact-hash CommonMark pass.
    markdown_receipt_path = EVIDENCE_ROOT / "evidence" / "markdown" / "receipt.json"
    markdown_receipt = json.loads(markdown_receipt_path.read_text())
    observed = json.loads((EVIDENCE_ROOT / "observed-receipt.json").read_text())
    source = markdown_receipt["commonMarkObservation"]

    # When: the canonical observed receipt is inspected by required operation.
    client_observations = [
        entry
        for entry in observed["observations"]
        if entry["operation"] == "commonmark-validate"
    ]
    blockers = [
        entry
        for entry in observed["externalBlockers"]
        if entry["operation"] == "commonmark-validate"
    ]

    # Then: raw facts and evidence identity produce a pass without an authority blocker.
    assert markdown_receipt["localVerdict"] == "pass"
    assert source["opened"] is True
    assert source["extensionWarningCount"] == 0
    assert source["expectedTextCount"] == source["observedTextCount"] == 3
    assert len(client_observations) == 1
    observation = client_observations[0]
    assert observation["verdict"] == "pass"
    assert observation["artifactHash"] == markdown_receipt["inputs"]["artifact"][
        "pristineAfterSha256"
    ]
    assert observation["evidenceHash"] == "sha256:" + hashlib.sha256(
        markdown_receipt_path.read_bytes()
    ).hexdigest()
    assert blockers == []
