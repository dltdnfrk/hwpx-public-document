# AC-01 provenance evidence

Public Document Studio is built against these immutable upstream boundaries:

- GenOffice Docs: `d8305ff2dc152593a1ec5639d77e6860c6a512bd` (Apache-2.0)
- rhwp: `2dced7bfe10c6597cead634264c7c1781c01f1e7` (MIT)

`upstream-lock.json` records the approved source scope and review verdicts.
`sbom.spdx.json` records the same revisions and licenses as SPDX 2.3 packages,
plus all 204 packages in the exact pinned rhwp Cargo.lock. The matching
`rhwp-dependency-lock.json` binds names, versions, source/checksum data, and
package-manifest license declarations to Cargo.lock SHA-256
`64ff4041c1874c01c7a901b28df2639082836ced44df392cd37b3227d4772279`.
Complete license texts and third-party notices live in `Resources/Legal`.
The rhwp entry additionally binds the reproducible local compatibility patchset,
patched-source hashes, build script hash, and bundled arm64 binary hash while
retaining the approved upstream commit as its only source base.

From the repository root, reproduce and verify the unsigned Apple Silicon app:

```sh
uv run --with pytest python -m pytest -q
scripts/package-macos-app.sh
codesign --verify --deep --strict dist/PublicDocument.app
test "$(lipo -archs dist/PublicDocument.app/Contents/MacOS/PublicDocumentApp)" = "arm64"
jq empty \
  dist/PublicDocument.app/Contents/Resources/Provenance/upstream-lock.json \
  dist/PublicDocument.app/Contents/Resources/Provenance/sbom.spdx.json \
  dist/PublicDocument.app/Contents/Resources/Provenance/rhwp-dependency-lock.json
```

The packaging scripts clear extended attributes before signing and again at the
final publication boundary, then record the strict verification instant and
binary hashes. This repository lives on a File Provider volume, which can
asynchronously reattach Finder metadata afterward; clear the app's extended
attributes immediately before any later strict recheck or copy it to a normal
local volume.

The app bundle is ad-hoc signed for local execution. Distribution signing,
notarization, updater, DMG, and Gatekeeper evidence belong to a later Seed.
