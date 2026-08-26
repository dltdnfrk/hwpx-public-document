from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _app_binary() -> Path:
    _ = subprocess.run(
        ["swift", "build", "--product", "PublicDocumentApp"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return ROOT / ".build" / "debug" / "PublicDocumentApp"


def _receipt_value(receipt: str, query: str) -> str:
    completed = subprocess.run(
        ["jq", "-cr", query],
        cwd=ROOT,
        input=receipt,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_ai_governance_is_consent_bound_reviewed_atomic_and_restart_persistent(
    tmp_path: Path,
) -> None:
    # Given: an offline app-native project and the frozen approved provider set.
    completed = subprocess.run(
        [str(_app_binary()), "--ai-governance-self-test", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    # When: consent, proposal review, stale conflict, partial approval, undo, redo,
    # and restart recovery are exercised through the native executable.
    receipt = completed.stdout

    # Then: AI remains user-controlled and app-native history is authoritative.
    assert _receipt_value(receipt, ".approvedProviderKinds") == (
        '["anthropic","gemini","openai","openai-compatible"]'
    )
    boolean_fields = [
        "offlineEditingAndExportAvailable",
        "localAdapterUnavailableWithoutFallback",
        "allConsentBindingsRequired",
        "revocationBlockedFutureRequest",
        "proposalDidNotMutateDocument",
        "diffsExposeStableTargets",
        "staleProposalRejected",
        "partialApprovalAppliedAtomically",
        "wholeApprovalAppliedAtomically",
        "rejectionPersisted",
        "undoRedoPersistedAcrossRestart",
        "forbiddenDataAbsentFromPersistence",
        "secureProviderTransportBehavior",
        "brandedEndpointAllowlistEnforced",
        "endpointValidationPrecedesPersistence",
        "actualScopedTargetIDsEnforced",
        "exactTablePathFailClosed",
        "tableCellOnlyMutation",
        "fullDiffPersisted",
        "consentRebindingRequired",
        "sharedPayloadScopeRules",
    ]
    for field in boolean_fields:
        assert _receipt_value(receipt, f".{field}") == "true", field
    assert _receipt_value(receipt, ".operationSpecificCommands") == (
        '{"evidenceClaimCheck":true,"missingDataMarking":true,"tableCellUpdate":true}'
    )

    source_paths = [
        "Sources/PublicDocumentApp/AIGovernance.swift",
        "Sources/PublicDocumentApp/AIBridgeCLI.swift",
        "Sources/PublicDocumentApp/AIProviderCatalog.swift",
        "Sources/PublicDocumentApp/AISettingsModels.swift",
        "Sources/PublicDocumentApp/AISettingsStore.swift",
        "Sources/PublicDocumentApp/AISettingsSelfTest.swift",
        "Sources/PublicDocumentApp/AIProviderTransport.swift",
        "Sources/PublicDocumentApp/AIGovernanceSelfTest.swift",
        "Sources/PublicDocumentApp/DocumentProject.swift",
        "Sources/PublicDocumentApp/main.swift",
    ]
    expected_source_hashes = {
        relative_path: "sha256:"
        + hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        for relative_path in source_paths
    }
    source_hash_rows = _receipt_value(
        receipt,
        '.implementationSourceSHA256 | to_entries[] | "\\(.key)\\t\\(.value)"',
    ).splitlines()
    assert dict(row.split("\t", maxsplit=1) for row in source_hash_rows) == (
        expected_source_hashes
    )


def test_studio_exposes_machine_consumed_consent_and_review_controls() -> None:
    html = (ROOT / "Resources/Studio/index.html").read_text(encoding="utf-8")

    for marker in (
        'data-ai-operation="source-grounded-draft"',
        'data-ai-operation="evidence-claim-check"',
        "data-ai-free-form",
        "data-ai-consent",
        "data-ai-proposal-review",
        "data-ai-diff",
        "data-ai-approve-selected",
        "data-ai-reject",
        "data-byok-secret",
    ):
        assert marker in html
