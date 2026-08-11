from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict

from tests.seed_criterion_contract_support import JSONValue


def write_json(root: Path, relative: str, value: JSONValue) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def evidence(root: Path, relative: str) -> Dict[str, str]:
    digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
    return {"path": relative, "sha256": f"sha256:{digest}"}


def write_ac04_fixture(root: Path) -> None:
    write_json(root, "runtime/ai.json", {"receipt": "independent-source"})
    source = [evidence(root, "runtime/ai.json")]
    write_json(
        root,
        "artifacts/privacy/provider-boundary-evidence.json",
        {
            "schemaVersion": 1,
            "approvedProviderKinds": ["anthropic", "gemini", "openai", "openai-compatible"],
            "offlineEditingAndExportAvailable": True,
            "localAdapterUnavailableWithoutFallback": True,
            "allConsentBindingsRequired": True,
            "forbiddenDataAbsentFromPersistence": True,
            "secureProviderTransportBehavior": True,
            "brandedEndpointAllowlistEnforced": True,
            "endpointValidationPrecedesPersistence": True,
            "consentRebindingRequired": True,
            "sourceEvidence": source,
        },
    )
    write_json(
        root,
        "artifacts/ai/proposal-lifecycle-evidence.json",
        {
            "schemaVersion": 1,
            "proposalDidNotMutateDocument": True,
            "diffsExposeStableTargets": True,
            "staleProposalRejected": True,
            "wholeApprovalAppliedAtomically": True,
            "partialApprovalAppliedAtomically": True,
            "rejectionPersisted": True,
            "undoRedoPersistedAcrossRestart": True,
            "revocationBlockedFutureRequest": True,
            "actualScopedTargetIDsEnforced": True,
            "operationSpecificCommands": {
                "missingDataMarking": True,
                "evidenceClaimCheck": True,
                "tableCellUpdate": True,
            },
            "exactTablePathFailClosed": True,
            "tableCellOnlyMutation": True,
            "fullDiffPersisted": True,
            "sourceEvidence": source,
        },
    )


def write_ac07_fixture(root: Path, *, structural_verdict: str) -> None:
    formats = ["hwpx", "hwp", "docx", "markdown"]
    fixture_hashes = {
        "basic-client-interoperability": "sha256:" + "1" * 64,
        "authoring-universe": "sha256:" + "2" * 64,
    }
    write_json(
        root,
        "artifacts/compatibility/corpus-manifest.json",
        {
            "manifestVersion": "1.0.0",
            "status": "frozen",
            "requiredFonts": ["Apple SD Gothic Neo Regular"],
            "visualTolerances": {
                "pageCountDelta": 0,
                "missingTextElements": 0,
                "unexpectedBlankPages": 0,
                "minimumTextBoundsCoverage": 0.95,
            },
            "fixtures": [
                {"id": fixture, "projectHash": digest, "formats": formats}
                for fixture, digest in fixture_hashes.items()
            ],
        },
    )
    artifacts = []
    for format_name in formats:
        relative = f"runtime/basic.{format_name}"
        (root / "runtime").mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(format_name, encoding="utf-8")
        artifacts.append(
            {
                "fixtureID": "basic-client-interoperability",
                "fixtureHash": fixture_hashes["basic-client-interoperability"],
                "format": format_name,
                "artifactHash": evidence(root, relative)["sha256"],
                "artifactEvidence": evidence(root, relative),
                "byteCount": len(format_name),
                "structuralValid": True,
                "semanticValid": True,
                "validation": {
                    "structuralValid": structural_verdict == "pass",
                    "semanticValid": True,
                    "evidenceSource": "artifact-derived",
                    "validator": "fixture artifact reopen",
                    "orderedElements": [
                        {
                            "elementID": "element-1",
                            "kind": "paragraph",
                            "order": 0,
                            "textHash": "sha256:" + "3" * 64,
                        }
                    ],
                },
            }
        )
    dispositions = [
        {
            "fixtureID": fixture,
            "fixtureHash": fixture_hashes[fixture],
            "format": format_name,
            "disposition": "artifact-validated" if fixture.startswith("basic") else "semantic-loss-blocked",
            "capabilityGaps": [] if fixture.startswith("basic") else ["unsupported-fixture-capability"],
        }
        for fixture in fixture_hashes
        for format_name in formats
    ]
    write_json(root, "runtime/compatibility.json", {"receipt": "source"})
    required_operations = {
        "hwpx": ["polaris-office-reopen", "hancom-official-reopen"],
        "hwp": ["polaris-office-reopen", "hancom-official-reopen"],
        "docx": ["microsoft-word-reopen", "genoffice-docs-reopen"],
        "markdown": ["commonmark-validate", "approved-rendering"],
    }
    external_blockers = [
        {"blockerID": f"client-{format_name}-{operation}", "verdictClass": "client", "fixtureID": "basic-client-interoperability", "reasonCode": "required-client-unavailable", "format": format_name, "operation": operation, "code": "required-client-unavailable", "status": "BLOCKED", "fixtureHash": fixture_hashes["basic-client-interoperability"], "artifactHash": next(entry["artifactHash"] for entry in artifacts if entry["format"] == format_name), "observedAt": "2026-08-10T00:00:00Z", "detail": "external observation unavailable", "evidence": [evidence(root, "runtime/compatibility.json")]}
        for format_name, operations in required_operations.items()
        for operation in operations
    ]
    external_blockers.extend(
        {
            "blockerID": f"visual-{artifact['format']}",
            "verdictClass": "visual",
            "fixtureID": artifact["fixtureID"],
            "reasonCode": "authority-approval-pending",
            "format": artifact["format"],
            "operation": "visual-inspection",
            "code": "authority-approval-pending",
            "status": "BLOCKED",
            "fixtureHash": artifact["fixtureHash"],
            "artifactHash": artifact["artifactHash"],
            "observedAt": "2026-08-10T00:00:00Z",
            "detail": "visual observation unavailable",
            "evidence": [evidence(root, "runtime/compatibility.json")],
        }
        for artifact in artifacts
    )
    write_json(
        root,
        "artifacts/compatibility/verdict-summary.json",
        {
            "manifestVersion": "1.0.0",
            "structuralVerdict": structural_verdict,
            "semanticVerdict": "pass",
            "visualVerdict": "pass",
            "clientVerdict": "pass",
            "overallVerdict": "pass",
            "artifacts": artifacts,
            "dispositions": dispositions,
            "visualObservations": [],
            "externalBlockers": external_blockers,
            "sourceEvidence": [evidence(root, "runtime/compatibility.json")],
        },
    )
    write_json(root, "artifacts/compatibility/observations.jsonl", [])
