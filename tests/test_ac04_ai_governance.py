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
    ]
    for field in boolean_fields:
        assert _receipt_value(receipt, f".{field}") == "true", field
    assert _receipt_value(receipt, ".operationSpecificCommands") == (
        '{"evidenceClaimCheck":true,"missingDataMarking":true,"tableCellUpdate":true}'
    )

    source_paths = [
        "Sources/PublicDocumentApp/AIGovernance.swift",
        "Sources/PublicDocumentApp/AISettings.swift",
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


def test_studio_exposes_guided_free_form_consent_diff_and_review_controls() -> None:
    # Given: the shipped local Studio resources.
    html = (ROOT / "Resources/Studio/index.html").read_text(encoding="utf-8")
    script = (ROOT / "Resources/Studio/app.js").read_text(encoding="utf-8")
    host = (ROOT / "Sources/PublicDocumentApp/main.swift").read_text(encoding="utf-8")
    transport = (ROOT / "Sources/PublicDocumentApp/AIProviderTransport.swift").read_text(encoding="utf-8")

    # When/Then: both AI entry paths terminate in an explicit consent/review flow.
    assert 'data-ai-operation="source-grounded-draft"' in html
    assert 'data-ai-operation="evidence-claim-check"' in html
    assert "data-ai-free-form" in html
    assert "data-ai-consent" in html
    assert "data-ai-proposal-review" in html
    assert "data-ai-diff" in html
    assert "data-ai-approve-selected" in html
    assert "data-ai-reject" in html
    assert "requestAIProposal" in script
    assert "applyAIProposal" in script
    assert "projectBridge('applyAIProposal'" in script
    assert "projectBridge('rejectAIProposal'" in script
    assert "projectBridge('revokeAIConsent'" in script
    assert "projectBridge('configureAISettings'" in script
    assert "projectBridge('testAISettings'" in script
    assert "projectBridge('deleteAISettings'" in script
    assert "data-byok-secret" in html
    assert 'case "applyAIProposal"' in host
    assert 'case "rejectAIProposal"' in host
    assert 'case "revokeAIConsent"' in host
    assert "AIProviderTransport().request" in host
    assert "URLSessionConfiguration.ephemeral" in transport
    assert "AIKeychainCredentialStore" in transport
