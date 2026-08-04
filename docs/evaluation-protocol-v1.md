---
protocol_id: public-document-evaluation
version: "1.0"
status: approved-for-local-evaluation
approver: "Public Document Product Authority"
approved_at: "2026-08-04T09:00:00+09:00"
---

# Evaluation Protocol v1

## Scope

This protocol evaluates the local implementation from the canonical project root. It does not treat an agent report as evidence. Every command and result must be captured by the evaluator that ran it.

## Required gates

1. `python3 -m pytest -q` must pass.
2. A guided-answer fixture must produce a stable `document_id`, explicit `period`, paragraph status, evidence provenance, and a HWPX artifact.
3. Every numeric, date, currency, count, percentage, or comparison claim in grounded factual fields must either resolve to verified evidence or remain `[확인 필요]` with `evidence_blocked` status.
4. A repeated export with one `operation_id` must be idempotent at one destination and must reject a second destination.
5. Title and existing-table-cell corrections must be visible in the semantic model and serialized HWPX.
6. External provider access must pass through a consent gateway. Local drafting must remain available when providers or consent are unavailable.
7. HWPX export must reject page counts over five and validate required parts, relationships, XML, styles, metadata, paragraph status, and table dimensions.
8. On Apple Silicon macOS, `swift build -c release` must compile the SwiftUI app target. A signed Developer ID DMG requires codesign, notarization, stapling, and Gatekeeper assessment.

## Verdict semantics

`PASS` means the evaluator observed the required behavior. `BLOCKED_PENDING_APPROVAL` is used when a release credential, notarization profile, official institution template, or real HWP adapter is unavailable; it is not converted into a pass by an agent assertion. `FAIL` means the observed behavior violates a required gate.

## Evidence record

The evaluator records the full command, exit status, artifact path, and a SHA-256 hash for each produced HWPX or release artifact. Sensitive bodies, credentials, and PII are excluded from the record.
