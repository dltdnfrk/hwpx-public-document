# AC-04 AI governance and offline evidence

## Result

The app remains fully editable and exportable without an account, credential, or network. Cloud AI is optional and limited to OpenAI, Anthropic, Gemini, and user-configured OpenAI-compatible endpoints. The local adapter is absent from the approved provider set and cannot fall back to cloud.

Every external request is bound to the exact document, provider, endpoint identity, operation, and disclosed payload scope. Grants persist in the app-native project, matching revocation marks them inactive, and changing any binding dimension requires a new grant. Credentials are stored through macOS Security.framework generic-password APIs; the project contains only an opaque Keychain account reference.

The provider transport uses an ephemeral, cache-disabled URL session with bounded timeouts. Branded providers are restricted to `api.openai.com`, `api.anthropic.com`, and `generativelanguage.googleapis.com` over HTTPS. User-configured OpenAI-compatible endpoints may use arbitrary HTTPS hosts; plain HTTP is accepted only for `localhost`, `127.0.0.1`, or `::1`. The Studio validates that policy before writing a Keychain credential or provider configuration. Request bodies and secrets are not logged, cached, written to temporary files, or included in project persistence.

Provider output is parsed into operation-specific commands: missing-data marking requires `replace-text` with `[확인 필요]`, evidence checks require `evidence-check` on an evidence-linked element, and table changes require `table-cell-update` with the exact `table:<elementID>/row:<zero-based>/cell:<zero-based>` path. A command is rejected if its stable target ID is outside the actual disclosed scope. Table paths with the wrong element, negative/non-numeric indexes, or extra components fail closed; approval replaces only the requested `td`/`th` body and preserves neighboring cells and markup.

Proposals persist full, untruncated before/after diffs and target paths without changing document elements. Native approval rejects stale base revisions, validates every selected command before mutation, and applies whole or partial selections as one immutable revision. Rejection, undo, redo, and proposal history survive save and restart.

## Executable evidence

Current-source validation completed on 2026-08-10 in the recorded local Apple Silicon macOS environment:

- `swift build --product PublicDocumentApp`: passed.
- `.venv/bin/python -m pytest -q tests/test_ac03_guided_template_workflow.py tests/test_ac04_ai_governance.py`: exited `0`, emitted no stderr, and reached `.... [100%]` for all four focused tests.
- `output/ac-04/final-freeze.WpyoS4/bin/PublicDocumentApp --ai-governance-self-test output/ac-04/final-freeze.WpyoS4/project-state`: all receipt fields passed.

The executable was copied into the evidence root before the canonical self-test. Its SHA-256 and arm64 architecture are therefore preserved even if another shared-worktree task subsequently rebuilds `.build`.

The native receipt reported:

```json
{"actualScopedTargetIDsEnforced":true,"allConsentBindingsRequired":true,"approvedProviderKinds":["anthropic","gemini","openai","openai-compatible"],"brandedEndpointAllowlistEnforced":true,"consentRebindingRequired":true,"diffsExposeStableTargets":true,"endpointValidationPrecedesPersistence":true,"exactTablePathFailClosed":true,"forbiddenDataAbsentFromPersistence":true,"fullDiffPersisted":true,"implementationSourceSHA256":{"Sources/PublicDocumentApp/AIGovernance.swift":"sha256:8f3562fbc175355f03d829abb071655ba9e8ac643d34e1d08219cf650ba10010","Sources/PublicDocumentApp/AIGovernanceSelfTest.swift":"sha256:e84c1855ac7058e352c5256d20b21cb9e2a1b4e300c14b95c73be63b291c70d0","Sources/PublicDocumentApp/AIProviderTransport.swift":"sha256:5f4408748d526fdd9dca67d58c38417cea97e3d63857f6caeff11bfb2ebdc2e0","Sources/PublicDocumentApp/DocumentProject.swift":"sha256:46e22af4f00e9644b4ed7feae5a95bf19429ad00ae6fe3f790e81005606b7777","Sources/PublicDocumentApp/main.swift":"sha256:5007900b8077931cfe2ac62d2ca818c4013149ffb45a875dd6e939022817df3f"},"localAdapterUnavailableWithoutFallback":true,"offlineEditingAndExportAvailable":true,"operationSpecificCommands":{"evidenceClaimCheck":true,"missingDataMarking":true,"tableCellUpdate":true},"partialApprovalAppliedAtomically":true,"proposalDidNotMutateDocument":true,"rejectionPersisted":true,"revocationBlockedFutureRequest":true,"secureProviderTransportBehavior":true,"staleProposalRejected":true,"tableCellOnlyMutation":true,"undoRedoPersistedAcrossRestart":true,"wholeApprovalAppliedAtomically":true}
```

The new fields are independent executable checks rather than aliases, except `consentRebindingRequired`, which intentionally exposes the existing five-dimension `allConsentBindingsRequired` result under the criterion's explicit name. `fullDiffPersisted` reopens the project and compares the complete diff, including a replacement over 512 UTF-8 bytes. `endpointValidationPrecedesPersistence` binds the current `main.swift` ordering of endpoint policy validation, Keychain write, and project save, while `implementationSourceSHA256` binds the receipt to every native source involved in that path.

`secureProviderTransportBehavior` behaviorally verifies remote HTTP rejection, HTTPS request construction, bearer credential placement, scoped document payload inclusion, and structured response parsing for all four approved provider kinds. No real provider credential or live SaaS request was used, so this evidence does not claim external provider availability.

## Final bound evidence root

The canonical AC-04 root is `output/ac-04/final-freeze.WpyoS4`. The evaluator-ready raw receipt is `output/ac-04/final-freeze.WpyoS4/receipt.json`; `provenance/seed-evidence-sources.json` must bind `criteria.AC-04.aiGovernanceReceipt` directly to that file.

| Artifact | SHA-256 | Role |
| --- | --- | --- |
| `receipt.json` | `9236df6600dfe81920bd627dda9d226f8dfcdd1e352346c693a1e0dda0250021` | Raw materializer and evaluator input |
| `independent-validation.json` | `b1be0cea3cc293d24f0a34b59b36e88e8f9307dab5770b1773746d295b5e54f7` | Fifteen independent checks, including final runtime/provenance freeze; verdict `pass` |
| `evaluator-result.json` | `1447984d10a16670af9298d69d37092c1c597e2e01891b5aaa96e43709134e8c` | Actual AC-04 criterion evaluator; all 25 checks passed |
| `project-state/governed.publicdocument/project.json` | `28717f80703e69b7bd22090280dc0598e3eea81fe3c7c7fa5e34ba2e70d05b03` | Reopened authoritative project proving persisted full diffs and review history |
| `bin/PublicDocumentApp` | `e55d46b24bb31afbe91e4f54adb6abe17b16554338673858efb38cb263c3d14a` | Immutable arm64 executable used to produce the receipt |
| `qa-verdict.json` | `c2f7d9072a38599d14f6ae5afe251d2fa4c3b67b54ff65370d97ded7f089bc8e` | QA score `0.99`, verdict `pass` |
| `SHA256SUMS` | `e575b572395cf908167b75329df61a971ae8fb06c903a2cd340b8a04c86d894a` | Complete evidence-root checksum index |

The source snapshot binds 20 final-freeze files and remained byte-identical before and after the canonical self-test. It includes the final Studio, GenOffice browser source, inline-identity source, browser bundle, runtime manifest, port manifest, and upstream lock. Independent validation separately compares those exact freeze hashes, the four-provider allowlist, source-order positions for endpoint validation, Keychain write, and project save, the complete persisted diff over 512 UTF-8 bytes, stable target IDs, proposal states, opaque Keychain references, forbidden persisted bytes, receipt source hashes, and the immutable executable hash.

## Manual and visual QA

The prior 2026-08-09 Chromium captures remain historical evidence, but they are not claimed as current-source-bound because the Studio source has changed since those captures. Current browser, accessibility, and visual observations are tracked by the AC-08 final evidence refresh; this AC-04 receipt covers the native governance behavior and source binding only.

## Bound implementation hashes

| Artifact | SHA-256 |
|---|---|
| `AIGovernance.swift` | `8f3562fbc175355f03d829abb071655ba9e8ac643d34e1d08219cf650ba10010` |
| `AIProviderTransport.swift` | `5f4408748d526fdd9dca67d58c38417cea97e3d63857f6caeff11bfb2ebdc2e0` |
| `AIGovernanceSelfTest.swift` | `e84c1855ac7058e352c5256d20b21cb9e2a1b4e300c14b95c73be63b291c70d0` |
| `DocumentProject.swift` | `46e22af4f00e9644b4ed7feae5a95bf19429ad00ae6fe3f790e81005606b7777` |
| `main.swift` | `5007900b8077931cfe2ac62d2ca818c4013149ffb45a875dd6e939022817df3f` |
| `Resources/Studio/index.html` | `2c3de4829b1f617bb20d38997f6ae849b38d7965024613c28094c7878f632fcc` |
| `Resources/Studio/app.js` | `baf94d4df0b25cef654fc1f7eadbaf8a27b880794deb44d3ecfc0bff1c735e42` |
| `Resources/Studio/styles.css` | `b905fba51298ac582eb2103dea6a0163d493cccc1f12613c662716f679c831d7` |
| `GenOfficeFork/browser.tsx` | `d02b63666c6064e524a788609db8521469e1754bfc87eed74256a93d7d327673` |
| `GenOfficeFork/project-inline-identity.ts` | `8049a3e3c80590ffa7f954ab393301187614826cf86d69a02c262694ae28de68` |
| `Resources/GenOffice/public-document-genoffice.js` | `0e171084942762e85ac30f134a82d3b6aa94904456656f156b7a07170765d33a` |
| `Resources/GenOffice/runtime-manifest.json` | `4b691934c27230ecb6a4c5defcc11b625f1f3f20a82ff21e6867e04641d19616` |
| `provenance/genoffice-docs-port.json` | `7e0d4bd4b3124944aa67bea50c206286fa5b7fc9d51ee20432ebfd9f707fc4dd` |
| `provenance/upstream-lock.json` | `6023b284651e8f7938f9153622f411922d4657210b8080cd86ad342135adf3bb` |
| `tests/test_ac04_ai_governance.py` | `e22871933475f4f8e7321eb6c9927f212c0150dd685d150dcb7dc6518477eaae` |
