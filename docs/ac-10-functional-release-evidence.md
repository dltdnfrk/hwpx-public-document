# AC-10 Functional Release Evidence

Date: 2026-08-10
Product: 공공문서 작성기 / Public Document Studio 0.1.0
Release type: unsigned local Apple Silicon functional build

## Verdict

AC-10 is `BLOCKED`, not passed. The local evidence bundle can be assembled
reproducibly and contains the arm64 app, preceding criterion reports,
machine-readable provenance, retained runtime receipts, and a complete SHA-256
inventory. However, the Seed requires it to demonstrate all nine preceding
outcomes. AC-07 and AC-08 remain blocked, so a scoped bundle-build success is
not promoted to an AC-10 pass.

The functional Seed verdict is `EXTERNAL_VERIFICATION_BLOCKED`. The remaining
gates are an unlocked clean Polaris run, an official Hancom HWPX/HWP environment,
approval of the Markdown rendering baseline, and the full VoiceOver journeys.
Pinned GenOffice, Word document-model reopen, CommonMark, structural, semantic,
performance, and non-GUI functional checks now pass for their exact artifacts.

## Bundle contract

Run `scripts/build-ac10-functional-release.sh <new-destination>
<source-map>`. The second argument defaults to
`provenance/seed-evidence-sources.json`. Publication refuses an existing
destination. Before building, the command parses the source map through `jq`
and rejects absolute paths, traversal segments, missing paths, root escapes,
non-file/non-directory entries, and symbolic links.

Only AC-01 through AC-09 source-map leaves are consumed. Their exact confined
paths are copied under `Evidence/CanonicalSources`; no fixed `final-seed.*`,
`runtime-seed.*`, Playwright, Word, Markdown, or VoiceOver output root is part
of the script. The complete source map and every AC-10 leaf are deliberately
excluded from the functional bundle to prevent release self-reference.

The output contains `PublicDocument.app` and `Evidence`.
`Evidence/release-manifest.json` records the functional scope, and
`Evidence/SHA256SUMS` binds every app and evidence file. The newly packaged
app contains the generated GenOffice browser bundle and DOCX normalizer,
`runtime-manifest.json`, the arm64 Node runtime, and the exact GenOffice input
and Node locks under `Contents/Resources/Provenance`.

The newly packaged
binary regenerates AC-01 package integrity; AC-02 project/window recovery;
AC-03 template; AC-04 AI governance; all current AC-05 export; all six AC-06
batch/recovery; and AC-09 performance receipts under
`Evidence/Runtime/ac-10-packaged-app/ac-*`. AC-07 and AC-08 remain source-map
observations because their representative-client and assistive-technology
evidence cannot be synthesized by a local self-test.

The non-circular publication order is:

1. Freeze and validate the canonical AC-01 through AC-09 source-map entries.
2. Run `scripts/build-ac10-functional-release.sh <new-destination>
   <source-map>`.
3. Run `scripts/package-release-archive.sh
   <new-destination>/PublicDocument.app <new-output.zip>`.
4. Outside the release directory and ZIP, write the resulting release manifest,
   ZIP, ZIP verification receipt, and ZIP SHA-256 inventory paths into the
   canonical source map's four AC-10 leaves.
5. Materialize and verify the Seed from that outer source map. Never rebuild
   the archive merely to embed the resulting AC-10 projection.

### Canonical archive gate

An extracted `.app` directory is not the canonical handoff artifact. Finder or
File Provider can attach `com.apple.FinderInfo` after publication and make a
later `codesign --verify --deep --strict` recheck fail even though the sealed
file contents did not change. Run
`scripts/package-release-archive.sh <packaged-app> <new-output.zip>` immediately
after the functional bundle build. The archive command never changes the input
app and refuses to replace the ZIP or either companion file.

The canonical local handoff consists of the resource-fork-free ZIP, its
`<stem>.SHA256SUMS`, and `<stem>.verification.json`. The command copies the app
without resource forks, extended attributes, quarantine data, or ACLs; fixes
all archived mtimes to the ZIP epoch; and creates the ZIP with `ditto -c -k
--norsrc --noextattr`. It then extracts the ZIP into a fresh `/tmp` directory
and independently requires all of the following before publishing the three
files:

- `codesign --verify --deep --strict` succeeds on the extracted app.
- The executable is arm64-only and `Info.plist` is valid.
- The packaged rhwp engine and its dependency inventory match the hashes in
  the packaged upstream lock.
- All required Studio, GenOffice, Legal, Templates, Capabilities,
  Compatibility, Performance, Engines, and Provenance resource trees exist and
  have receipt hashes.
- Every GenOffice manifest output exists with its exact declared SHA-256 and
  byte count; the packaged input and Node locks match the manifest.
- The packaged Node binary matches its manifest SHA-256 and byte count, is
  arm64-only, and links only system libraries. The browser and DOCX runtimes
  independently pass the forbidden Genspark, network, updater, dynamic-code,
  and unrelated GenOffice surface scan.
- Every regular app file matches the complete sorted SHA-256 inventory after
  extraction, and `__MACOSX`, `com.apple.FinderInfo`, and
  `com.apple.ResourceFork` are absent.

The receipt binds the ZIP hash and size, bundle identity and versions,
executable and plist hashes, every packaged provenance and engine artifact,
per-resource tree hashes, and the full inventory hash. Repeated runs over the
same packaged app produce byte-identical ZIPs. A final AC-10 evidence bundle
must be regenerated only after all source, resource, provenance, and preceding
criterion evidence is frozen.

## Packaged-app verification

Bundle assembly exercises the packaged executable through the real native
launch path and every local AC-01 through AC-06 and AC-09 evidence CLI. The
retained AC-10 receipts show one visible app
window; stable project persistence and migration; signed template bootstrap,
offline reload, rejection, pinning, and rollback; offline AI governance; HWPX
and HWP publication on the compatible fixture; loss-aware DOCX and Markdown
publication; batch completion with an injected partial failure; a structural
compatibility source boundary with visual and client verdicts still external;
and eight performance exports. The fresh receipts, rather than a historical
test count or ephemeral output directory name, are the evidence authority.

The packaged executable is a thin arm64 Mach-O. Its exact hash is recorded in
the current release bundle's `Evidence/SHA256SUMS` rather than repeated here.
`Evidence/Runtime/ac-10-packaged-app` contains the receipts, produced artifacts,
architecture observation, and local signature description used for this gate.

The local app is ad-hoc signed only so macOS can execute the assembled bundle.
No Developer ID certificate or distribution service participates, and the
bundle makes no signing, notarization, updater, DMG, Gatekeeper, or clean-Mac
claim. Those distribution concerns remain explicitly deferred.

## Final canonical handoff

The final functional bundle was assembled and verified under `/tmp` before
publication. This is required on the current Documents-backed workspace because
File Provider can attach Finder metadata to a visible `.app` after it is moved
there. The canonical handoff remains the freshly extracted and reverified ZIP,
not the mutable directory view.

- Archive: `output/ac-10/final-inline-id-handoff/PublicDocumentStudio-Functional-0.1.0.zip`
  - SHA-256: `b24f5eb590618dac2ac5468ad7e8637872c01166fb084d6eebde025581105ea6`
  - Size: 42,734,713 bytes
- Verification receipt: `output/ac-10/final-inline-id-handoff/PublicDocumentStudio-Functional-0.1.0.verification.json`
  - SHA-256: `5ab0ad44c4ba65e7f26380c924ec148c776e8b208aea4ed8ccac47a8dcfe0c55`
- Complete app inventory: `output/ac-10/final-inline-id-handoff/PublicDocumentStudio-Functional-0.1.0.SHA256SUMS`
  - SHA-256: `8c08cbb96a2431ae4be38dd3cf7c13ded7f5cb54fa364a1e995eacd0f6cc8d03`
  - Entries: 34/34 verified after fresh extraction
- Release manifest: `output/ac-10/final-inline-id-handoff/release-manifest.json`
  - SHA-256: `1a99a0a6e84ce0615f6032b4b40174150d557d9af6dc17e19a10e32174c81926`
- Extracted executable:
  - Architecture: arm64
  - Strict codesign: pass
  - SHA-256: `ec5ed6931fbb5f3a8560515fba5506cb694a817ef45e6f34b9d3f70a660a988b`

An independent final smoke extracted this ZIP into a new temporary directory,
rechecked the complete inventory and strict signature, and ran the packaged
binary. HWPX/HWP and DOCX/Markdown were all published with no failed format and
with artifact-derived structural and semantic validation.

The non-circular Seed projection is AC-01 through AC-06 and AC-09 `PASS`, with
AC-07 and AC-08 `BLOCKED` only by their recorded external observations. AC-10
therefore remains `BLOCKED` solely because those two predecessor criteria are
externally blocked; every local archive, package, provenance, identity, and
four-format smoke check passes.
