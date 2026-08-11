# AC-03 Guided Workflow and Trusted Template Evidence

Date: 2026-08-10
Platform: macOS, Apple Silicon
Application: immutable unsigned arm64 `PublicDocumentApp` executable snapshot

## Acceptance result

The guided policy workflow derives required sections and checklist state from the document-pinned `templateBinding`. Missing or ungrounded content remains marked `[확인 필요]`. For the supported `title` field, the native host resolves the highest-precedence rule in the current signed catalog for the pinned template ID. A conflicting submitted title and its title element are replaced before open, save, autosave, single-export, batch-export, and retry snapshots cross their native boundary.

An enforced content change appends a parent-linked `official-rule-enforced:title` revision and history event while preserving the previous revision and the document's pinned template version. Reapplying the same rule is idempotent. The Studio receives the applied `requiredValue`, `precedence`, source, submitted value, and native warning; it opens the official-rule disclosure when a conflict occurs. A signed catalog containing an unsupported official field fails closed as an invalid envelope.

The native template catalog accepts only Curve25519-signed envelopes for the embedded trust key. A verified update can add entries or publish a newer template version without mutating the open document's pinned template version. Invalid updates leave the trusted offline catalog intact, and the previous trusted catalog can be restored explicitly.

## Bound automated receipt

Command:

```text
output/ac-03/final-freeze.6xdin7/bin/PublicDocumentApp \
  --template-catalog-self-test \
  output/ac-03/final-freeze.6xdin7/catalog-state
```

Receipt:

```json
{"authoritativeTitle":"기관 공식 제목을 사용하세요","bootstrappedCatalogVersion":"2026.08.1","conflictWarning":"공식 규칙 충돌: 제출 제목 '템플릿 제안 제목' 대신 공식 규칙(우선순위 100)의 필수 제목을 적용했습니다: '기관 공식 제목을 사용하세요'.","exportBoundProjectTitle":"# 기관 공식 제목을 사용하세요","exportSnapshotUsedRuleRevision":true,"failedUpdatePreservedLastTrusted":true,"highestAppliedPrecedence":100,"immutableRevisionCreated":true,"lowerPrecedenceCouldNotOverride":true,"officialRuleHistoryRecorded":true,"officialRuleTitleElementEnforced":true,"offlineReloadCatalogVersion":"2026.09.1","pinnedTemplateVersionAfterUpdate":"3.2","pinnedTemplateVersionBeforeUpdate":"3.2","repeatedEnforcementWasIdempotent":true,"rollbackCatalogVersion":"2026.08.1","signatureRejected":true,"unsupportedOfficialFieldRejected":true,"updatedCatalogEntryCount":2,"updatedCatalogVersion":"2026.09.1"}
```

The receipt is produced by an executable path, not a source-only assertion. It installs a signed catalog containing conflicting title rules at precedence 10 and 100, governs a pinned-v3.2 project against the current v3.3 catalog entry, repeats enforcement, writes a Markdown export, rejects an unsupported signed field and a tampered signature, reloads offline, and rolls back.

The evaluator-ready raw receipt is `output/ac-03/final-freeze.6xdin7/receipt.json`; `provenance/seed-evidence-sources.json` must bind `criteria.AC-03.templateCatalogReceipt` directly to that file. Its SHA-256 is `070e42494eddc7b19ee1664aed5cffbace8c102158a29af2ed2357491e8e94c6`.

## Final bound evidence root

The canonical AC-03 root is `output/ac-03/final-freeze.6xdin7`.

| Artifact | SHA-256 | Role |
| --- | --- | --- |
| `receipt.json` | `070e42494eddc7b19ee1664aed5cffbace8c102158a29af2ed2357491e8e94c6` | Raw materializer and evaluator input |
| `independent-validation.json` | `8e68e804817da8c9bb80159834fff6b8abc8e7a1f6ad094550203c84d92c8534` | Eleven independent checks, including final runtime/provenance freeze; verdict `pass` |
| `evaluator-result.json` | `bc7974463c8737a705d1bea4a64d68bd9b7ee965a92add010b925a7692dfae67` | Actual AC-03 criterion evaluator; all 14 checks passed |
| `bin/PublicDocumentApp` | `e55d46b24bb31afbe91e4f54adb6abe17b16554338673858efb38cb263c3d14a` | Immutable arm64 executable used to produce the receipt |
| `qa-verdict.json` | `998bcb1855372afeb7dc56658e876fd9c1eb77c425d00e298c6511169be127b7` | QA score `0.99`, verdict `pass` |
| `SHA256SUMS` | `3d0bdc81a6451f9c7978b191a36d20c577560af2c6225b5969cb66ca50f27927` | Complete evidence-root checksum index |

The source snapshot lists 20 bound files and remained byte-identical before and after the self-test. It includes the final Studio, GenOffice browser source, inline-identity source, browser bundle, runtime manifest, port manifest, and upstream lock. The combined focused run

```text
.venv/bin/python -m pytest -q \
  tests/test_ac03_guided_template_workflow.py \
  tests/test_ac04_ai_governance.py
```

exited `0`, wrote no stderr, and reported `.... [100%]`. The copied executable is included in the evidence root so later shared-worktree rebuilds cannot change the binary that produced this receipt.

## Bound implementation evidence

| Artifact | SHA-256 | Observation |
| --- | --- | --- |
| `Resources/Templates/catalog-envelope.json` | `6868f0b9d8ceb2949e3e94cb0ac8ab138288eabb5635d52b34fda73bc4eed6b0` | Bundled signed catalog used for offline bootstrap |
| `Sources/PublicDocumentApp/TemplateCatalog.swift` | `65275d0111573adac2e1ce9b6d06f3660e6085b2155e5cef9d42c6cc05801674` | Supported-field decoding, highest-precedence selection, conflict receipt, revision/history creation |
| `Sources/PublicDocumentApp/TemplateCatalogSelfTest.swift` | `df17753d98b844f02514745ebe34b9a6715d2ae8908683a30ae0d1e939c9b8a6` | Conflicting-rule, idempotence, unsupported-field, immutable-revision, and exported-title runtime fixture |
| `Resources/Studio/index.html` | `2c3de4829b1f617bb20d38997f6ae849b38d7965024613c28094c7878f632fcc` | Final GenOffice-based Studio template and rule controls |
| `Resources/Studio/app.js` | `baf94d4df0b25cef654fc1f7eadbaf8a27b880794deb44d3ecfc0bff1c735e42` | Final required-value, precedence, stable-identity, and visible conflict disclosure bridge |
| `Resources/Studio/styles.css` | `b905fba51298ac582eb2103dea6a0163d493cccc1f12613c662716f679c831d7` | Current owned Studio presentation |
| `GenOfficeFork/browser.tsx` | `d02b63666c6064e524a788609db8521469e1754bfc87eed74256a93d7d327673` | Final pinned Docs browser adapter source |
| `GenOfficeFork/project-inline-identity.ts` | `8049a3e3c80590ffa7f954ab393301187614826cf86d69a02c262694ae28de68` | Final stable inline-ID preservation boundary |
| `Resources/GenOffice/public-document-genoffice.js` | `0e171084942762e85ac30f134a82d3b6aa94904456656f156b7a07170765d33a` | Final shipped GenOffice browser bundle |
| `Resources/GenOffice/runtime-manifest.json` | `4b691934c27230ecb6a4c5defcc11b625f1f3f20a82ff21e6867e04641d19616` | Final runtime input/output identity manifest |
| `provenance/genoffice-docs-port.json` | `7e0d4bd4b3124944aa67bea50c206286fa5b7fc9d51ee20432ebfd9f707fc4dd` | Final pinned port boundary |
| `provenance/upstream-lock.json` | `6023b284651e8f7938f9153622f411922d4657210b8080cd86ad342135adf3bb` | Final upstream/runtime lock |
| `tests/test_ac03_guided_template_workflow.py` | `e54aa9e4e91616cbe61c20877fc3a64be089d8356e7caae56245c9c8250232ca` | Exact executable receipt and shipped-surface assertions |

The prior Studio screenshots remain useful for layout history but predate native conflict enforcement, so they are not cited as proof of this change.

## Trust and recovery files

- `trusted-catalog.json` is the last verified offline catalog.
- `previous-catalog.json` is the explicit rollback target.
- `update-history.json` records bootstrap, install, and rollback events.
- All three are app-support state; document projects retain their own immutable template binding and are not rewritten by catalog operations.
