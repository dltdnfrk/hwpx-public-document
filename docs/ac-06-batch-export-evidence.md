# AC-06 Batch Export Evidence

## Outcome

Public Document Studio exports multiple app-authored projects to multiple selected formats through one durable document-by-format manifest. Validated siblings survive a failure or cancellation, existing destination bytes are refused rather than overwritten, unpublished staging is removed, and crash or disk-full recovery retains retry lineage.

The current native evidence contains exactly eight unique operation manifests produced by six invocations of the release binary. The approved AC-06 evaluator returns `pass` with all seven machine checks passing, including eight evidence-identity checks.

## Native integrity attestation

The existing-destination self-test now records an optional `destinationIntegrity` object only for that evidence scenario. It independently reads the exact destination bytes before and after the native refusal path and records byte counts, SHA-256 values, filename, and `existingBytesPreserved`. The result is computed from byte equality; it is not a hard-coded success flag.

Focused regression coverage proves both directions:

- unchanged user-owned bytes produce matching counts and hashes with `existingBytesPreserved: true`;
- an evidence-only mutation hook changes the hash and produces `existingBytesPreserved: false`.

Production batch manifests continue to omit this optional evidence field.

## Verification

The current workspace completed these checks:

```text
swift build -c release
Build complete

.venv/bin/python -m pytest tests/test_ac06_batch_export.py -q
....... [100%]

isolated approved-criterion evaluator
AC-06 pass; 7/7 checks passed; 8 evidence identities verified

shasum -a 256 -c output/ac-06/final-evaluator.WZ1m2O/SHA256SUMS
38/38 files OK
```

The release binary used for every native scenario is `.build/release/PublicDocumentApp`, size 2,714,144 bytes, SHA-256 `3b076294e69f3986f1755b235ffe65c9f2cc02a5038a9d2f0a75e56ff4480790`.

## Canonical runtime evidence

Root: `output/ac-06/final-evaluator.WZ1m2O/`

| Operation | Native state | Raw manifest |
| --- | --- | --- |
| `batch-ac06-partial` | `completed-with-errors` | `partial-failure/.public-document-studio-exports/batch-ac06-partial/manifest.json` |
| `batch-ac06-cancelled` | `cancelled` | `cancel-after-first/.public-document-studio-exports/batch-ac06-cancelled/manifest.json` |
| `batch-ac06-cancel-before-publication` | `cancelled` | `cancel-before-publication/.public-document-studio-exports/batch-ac06-cancel-before-publication/manifest.json` |
| `batch-ac06-existing` | `completed-with-errors` | `existing-destination/.public-document-studio-exports/batch-ac06-existing/manifest.json` |
| `batch-ac06-crashed` | `interrupted` | `crash-and-retry/.public-document-studio-exports/batch-ac06-crashed/manifest.json` |
| `batch-ac06-retry-after-crash` | `completed` | `crash-and-retry/.public-document-studio-exports/batch-ac06-retry-after-crash/manifest.json` |
| `batch-ac06-disk-full` | `interrupted` | `disk-full-and-retry/.public-document-studio-exports/batch-ac06-disk-full/manifest.json` |
| `batch-ac06-retry-after-disk-full` | `completed` | `disk-full-and-retry/.public-document-studio-exports/batch-ac06-retry-after-disk-full/manifest.json` |

The evaluator-ready final manifest is the raw `batch-ac06-partial` manifest. `source-map-fragment.json` lists the exact eight project-relative manifest paths and that final-manifest path without relying on a glob or ephemeral external location.

## Bound receipts

- `receipt.json` recomputes 14 assertions from the raw manifests and published files; SHA-256 `ce60ce11c72aa3fd38a2fc4ab5c4f4ca8287fc87361f032a920313556a0baa00`.
- `evaluator-result.json` records the approved AC-06 evaluator projection; SHA-256 `ef466aa0a106d7dd0a3d923b4efcfb56726af946e768924d3d397fc526fbffd4`.
- `source-map-fragment.json` binds the exact materializer inputs; SHA-256 `f20f7b742e0a3bdf56bc31159f2322133297377c0e87e15e629c72e8029c91a9`.
- `SHA256SUMS` covers all 38 evidence files; SHA-256 `5b378a5dfd954d353c7905abb1e4dd98a2e5c197c6fd3e0f8488d28f9ca35136`.

The final receipt proves all cleanup states are `clean`, no `.tmp` output remains, every published artifact exists and matches its manifest hash, failed and cancelled items have no artifact hash, progress fields are bounded, partial failure preserves three siblings, cancellation preserves only the already-published sibling, cancellation before publication publishes nothing, existing bytes remain exact, both recovery paths use new operation IDs with correct lineage and filenames, and both retries reset `flatteningConsent` to an empty array so prior consent is not silently reused.

## UI and compatibility boundary

The earlier AC-06 browser screenshots predate the final GenOffice Studio source and are not used by this regenerated native receipt. Current browser, accessibility, and VoiceOver evidence is regenerated and governed by AC-08.

AC-06 validates batch lifecycle, publication safety, cancellation, recovery, non-overwrite, progress data, and retry consent reset. Required Polaris Office, Hancom, Microsoft Word, GenOffice, and Markdown client reopen observations remain governed by AC-07.
