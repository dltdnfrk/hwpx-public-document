# AC-01 foundation evidence

The final AC-01 run was recorded at `2026-08-09T20:31:33Z`. Its canonical,
project-relative evidence root is `output/ac-01/final-bound.LkMdWr`;
`foundation-runtime.json` is the machine-readable receipt.

The run host was macOS 26.5.2 (`25F84`) on Apple Silicon `arm64` (Mac17,9),
Xcode 26.6 (`17F113`), Apple Swift 6.3.3 targeting
`arm64-apple-macosx26.0`, and Node 22.17.1.

## Result

AC-01 is `PASS` for the final frozen local release. A real release app was
built and packaged at
`/private/tmp/public-document-ac01-final.1pBkGJ/PublicDocument.app`, outside
the Documents File Provider. The exact executable and rhwp engine that were
observed are retained as:

- `output/ac-01/final-bound.LkMdWr/artifacts/PublicDocumentApp`
- `output/ac-01/final-bound.LkMdWr/artifacts/rhwp`

The app is a thin arm64 Mach-O with bundle identifier
`com.muni.public-document`, an ad-hoc signature, hardened runtime, and CDHash
`f506d21a028055d815ea2c0ad0093280efccaba5`. `codesign --verify --deep
--strict --verbose=2` passed. The app, bundled Node, and bundled rhwp
executables all report only `arm64`.

The executable hash is the same `ec5ed693…988b` independently reviewed by the
final browser/package visual gate. All 34 files in that gate's package manifest
were rechecked against this AC-01 package for both byte count and SHA-256; all
34 matched.

## Pinned runtime boundary

- GenOffice Docs is pinned to
  `d8305ff2dc152593a1ec5639d77e6860c6a512bd` under Apache-2.0.
- rhwp is pinned to `2dced7bfe10c6597cead634264c7c1781c01f1e7`
  under MIT.
- GenOffice is shipped as a `pinned-adapter-runtime-fork`, not a manual
  visual-only port. `directPackageRuntimeLinkage` and
  `upstreamRuntimeFilesBundled` are both `true`.
- The runtime contains the pinned Docs editor extensions and NavPane,
  `@genoffice/ui`, React/Tiptap, `@genoffice/docx-engine`, and the stable
  inline-identity extension used across editing, saving, export, and reopen.
- The reviewed boundary is limited to `apps/docs/src/renderer`,
  `packages/ui/src`, and `packages/docx-engine/src`. Genspark providers,
  accounts, endpoints, services, telemetry, `ee`, Sheets, Slides, PDF, the
  Electron shell, and unused office engines are excluded.

The runtime input lock binds 200 sorted source/dependency inputs and 42
JavaScript packages. The runtime manifest binds nine shipped outputs plus the
arm64 Node engine. The root SPDX inventory contains 250 packages and 250
relationships, including GenOffice, rhwp and its complete Cargo inventory,
the JavaScript closure, and Node. Complete license texts and notices ship
inside the app.

## Executed verification

```sh
PUBLIC_DOCUMENT_PACKAGE_PARENT=/private/tmp/public-document-ac01-final.1pBkGJ \
  scripts/package-macos-app.sh \
  /private/tmp/public-document-ac01-final.1pBkGJ/PublicDocument.app
# exit 0; release arm64 build, packaged resources, hardened ad-hoc signature

codesign --verify --deep --strict --verbose=2 \
  /private/tmp/public-document-ac01-final.1pBkGJ/PublicDocument.app
# exit 0

node scripts/verify-genoffice-port.mjs \
  --upstream-root /private/tmp/public-document-upstream-audit.YfDSXU/genoffice
# exit 0; upstreamVerified=true; 10 upstream sources; 5 local artifacts;
# directPackageRuntimeLinkage=true; upstreamRuntimeFilesBundled=true

node --test tests/genoffice-runtime.test.mjs
# 4 passed, 0 failed

.venv/bin/python -m pytest -q \
  tests/test_ac01_app_foundation.py tests/test_studio_host_security.py
# 9 passed, 0 failed
```

The packaged executable also ran `--studio-host-security-self-test` against a
live localhost HTTP/WebSocket probe. The sibling GenOffice resource loaded,
the native content-rule list was installed, HTTP/HTTPS/WS/WSS were blocked,
escaped file navigation was blocked, and the probe server observed zero
requests. The receipt is
`output/ac-01/final-bound.LkMdWr/host-security-selftest.json`.

Every packaged GenOffice output was checked against the manifest for both
SHA-256 and byte count. Packaged runtime, lock, port, upstream, SBOM, Node,
rhwp, and Studio copies were byte-identical to the frozen project sources.
`otool -L` confirmed that Node links only Apple system libraries. No packaged
source file changed after the app was built.

## User-visible surface observation

The exact package is bound to
`output/playwright/ac08-final-bound.UhLbrs`. The final browser suite passed
6/6 scenarios, captured 12/12 required product states, audited eight axe states
with zero violations, and recorded zero external requests. Independent visual
Pass A and Pass B both returned `PASS` with no product findings.

The final captures confirm natural Korean composition, the corrected
`첫 문장 강조 문장 기울임 문장 편집 [확인 필요]` keyboard-edit result,
stable block and inline IDs across save/export/reopen, the Docs-style
ribbon/outline/page geometry, responsive desktop states, keyboard focus,
dialogs, and owned branding. The four frozen-reference diffs contain zero
differing pixels.

Native VoiceOver is not included in this pass claim. Its exact-package receipt
at `output/ac-08/final-bound.R5vshb/voiceover-blocker.json` records the locked
console and all seven journeys as `NOT_RUN`.

## Bound artifact hashes

| Artifact | SHA-256 |
| --- | --- |
| evidence-bound `PublicDocumentApp` | `ec5ed6931fbb5f3a8560515fba5506cb694a817ef45e6f34b9d3f70a660a988b` |
| evidence-bound `rhwp` | `a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b` |
| packaged arm64 Node | `5c8cd3ab2559b530fceca01776064c56687619475a7ffc339178524af6cdaa25` |
| `Resources/GenOffice/runtime-manifest.json` | `4b691934c27230ecb6a4c5defcc11b625f1f3f20a82ff21e6867e04641d19616` |
| `Resources/GenOffice/public-document-genoffice.js` | `0e171084942762e85ac30f134a82d3b6aa94904456656f156b7a07170765d33a` |
| `GenOfficeFork/browser.tsx` | `d02b63666c6064e524a788609db8521469e1754bfc87eed74256a93d7d327673` |
| `GenOfficeFork/project-inline-identity.ts` | `8049a3e3c80590ffa7f954ab393301187614826cf86d69a02c262694ae28de68` |
| `Resources/GenOffice/genoffice-docx-normalize.cjs` | `43046343861265b0c89490f427cbf00118e42531d7144ff36173b543044170bc` |
| `GenOfficeFork/runtime-input-lock.json` | `3f1db99bedabfc47e1990f9229ce73fef6ff20f5a4642a18372416a920b3af79` |
| `GenOfficeFork/node-runtime-lock.json` | `18c95dc70ff877dc189d1e176f9cf7f8ee543aeb97d50d3290ca0092a2d56f95` |
| `provenance/upstream-lock.json` | `6023b284651e8f7938f9153622f411922d4657210b8080cd86ad342135adf3bb` |
| `provenance/genoffice-docs-port.json` | `7e0d4bd4b3124944aa67bea50c206286fa5b7fc9d51ee20432ebfd9f707fc4dd` |
| `provenance/sbom.spdx.json` | `48733531c3243d5e8ffc136288a1ae6664e6458d50ca9bc4380fc647e247d033` |
| packaged Studio `index.html` | `2c3de4829b1f617bb20d38997f6ae849b38d7965024613c28094c7878f632fcc` |
| packaged Studio `styles.css` | `b905fba51298ac582eb2103dea6a0163d493cccc1f12613c662716f679c831d7` |
| packaged Studio `app.js` | `baf94d4df0b25cef654fc1f7eadbaf8a27b880794deb44d3ecfc0bff1c735e42` |

## Scope of this verdict

This record does not promote external compatibility or accessibility blockers
to a pass. Microsoft Word, Polaris Office, official Hancom, and the approved
Markdown rendering authority remain under AC-07; the seven native VoiceOver
journeys remain under AC-08. Those blockers are preserved in
`foundation-runtime.json` and do not weaken this narrower AC-01 runtime,
provenance, licensing, and owned-interface verdict.
