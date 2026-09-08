# Release and recovery

## Release boundary

This repository produces a workspace-contained, ad-hoc-signed local functional
release. It is not Developer ID signed, notarized, or approved for Gatekeeper
distribution. AC-07 client interoperability and therefore AC-10 distribution
remain explicitly blocked in the bundled release manifest.

Never build into or modify `~/Applications/PublicDocument.app`. Desktop QA
records a recursive content, metadata, and extended-attribute snapshot of that
path before and after each run.

## Desktop QA

Run with an unlocked console:

```sh
caffeinate -dimsu python3 scripts/qa/macos-app-qa.py \
  --build --scenario happy \
  --evidence-dir .omo/evidence/manual/app-happy

caffeinate -dimsu python3 scripts/qa/macos-app-qa.py \
  --scenario invalid-project \
  --evidence-dir .omo/evidence/manual/app-invalid
```

The happy scenario packages `.build/macos-app-qa/PublicDocument.app`, waits for
the native Studio readiness event, captures its real window, exports HWPX, HWP,
DOCX, and Markdown, and records a batch receipt. The invalid scenario requires
the existing workspace app, displays the malformed-project diagnostic, and
proves that a protected destination is unchanged.

Every evidence directory is write-once. Use a new path for a rerun.

## Functional release and archive

```sh
caffeinate -dimsu scripts/build-ac10-functional-release.sh \
  .build/g007-functional-release \
  provenance/seed-evidence-sources.json

scripts/package-release-archive.sh \
  .build/g007-functional-release/PublicDocument.app \
  .omo/evidence/manual/release/PublicDocument.zip
```

`package-release-archive.sh` requires the complete `Evidence` tree beside the
input app. It strips Finder/resource-fork metadata in an isolated staging copy,
re-verifies codesign and arm64 architecture, checks provenance and runtime
hashes, normalizes timestamps, creates the ZIP, extracts it into a fresh
temporary directory, compares inventories, and only then publishes:

- `PublicDocument.zip`
- `PublicDocument.SHA256SUMS`
- `PublicDocument.verification.json`

Finder may add `com.apple.FinderInfo` after launching the workspace app. Do not
mutate the source bundle to race Finder; canonical archive staging removes the
attribute and verifies the clean copy.

## Recovery

1. Read the failing command and diagnostic in the QA or archive transcript.
2. Preserve occupied output paths. Both QA and archive commands refuse existing
   evidence or release outputs rather than overwriting them.
3. For interrupted batch exports, retain the
   `.public-document-studio-exports/<operation>/manifest.json` directory and use
   the app’s retry/recovery path; do not delete user-owned destination files.
4. For provenance drift, follow `docs/maintenance-and-recovery.md` and inspect
   the generated diff before rebuilding.
5. For launch-added metadata, rerun archive creation at a new output path. The
   staging copy is the sanitation boundary.
6. Confirm no `PublicDocumentApp`, release-builder, or archive process remains,
   and no `/tmp/public-document-release-*` directory remains.

Do not use destructive Git recovery and do not commit or push without explicit
authorization.
