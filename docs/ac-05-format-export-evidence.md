# AC-05 Safe Multi-Format Export Evidence

Date: 2026-08-10

Platform: macOS, Apple Silicon

Authoritative evidence root: `output/ac-05/final-stable-inline-bound.Fy3So4`

## Acceptance result

One immutable project snapshot can be exported to a selected subset of HWPX, HWP, DOCX, and Markdown. Each selected format receives one of three disjoint receipt dispositions: `publishedFormats`, `blockedFormats`, or `failedFormats`.

- Policy preflight blocks only the format with semantic loss or missing visual-flattening consent.
- A published artifact must pass format-specific structural and semantic validation derived from the artifact itself.
- An adapter, validation, or destination runtime failure is recorded for that format and does not stop later selected formats.
- Existing destinations are not overwritten. Publication uses a same-directory temporary file, an atomic move, and failure cleanup.
- The application-native project and its immutable revision remain authoritative; exported files are derivatives.

## Frozen inputs

| Input | Bound value | SHA-256 |
| --- | --- | --- |
| `Resources/Capabilities/authoring-capabilities-1.0.0.json` | Application `0.1.0`; manifest `1.0.0`; 15 authorable elements; 6 frozen combinations | `82f5ecb9e7455956e39773537d1c4fabfe1c2e3f04831e25a53ea719b699849a` |
| `Resources/Capabilities/format-capabilities-1.0.0.json` | Manifest `1.0.0`; 17 rows; only `lossless`, `visual-only-flattening`, and `semantic-loss` | `c8cb49c859e902ce6434b167f2b72c757a379a16a6315ab38f8ad6c7caa01e6a` |
| `Resources/Engines/rhwp` | Owned bundled arm64 engine built from upstream commit `2dced7bfe10c6597cead634264c7c1781c01f1e7` plus the recorded local compatibility patchset | `a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b` |
| `Resources/GenOffice/runtime-manifest.json` | Approved GenOffice Docs runtime at `d8305ff2dc152593a1ec5639d77e6860c6a512bd`; final stable-inline-ID freeze | `4b691934c27230ecb6a4c5defcc11b625f1f3f20a82ff21e6867e04641d19616` |
| `Resources/GenOffice/public-document-genoffice.js` | Final pinned Docs browser bundle with stable inline IDs | `0e171084942762e85ac30f134a82d3b6aa94904456656f156b7a07170765d33a` |
| `Resources/GenOffice/genoffice-docx-normalize.cjs` | Bundled `@genoffice/docx-engine` normalization CLI | `43046343861265b0c89490f427cbf00118e42531d7144ff36173b543044170bc` |
| `Resources/Engines/node` | Bundled Node `22.17.1`, arm64 | `5c8cd3ab2559b530fceca01776064c56687619475a7ffc339178524af6cdaa25` |
| `GenOfficeFork/runtime-input-lock.json` | Complete final upstream/runtime build-input lock | `3f1db99bedabfc47e1990f9229ce73fef6ff20f5a4642a18372416a920b3af79` |
| `provenance/genoffice-docs-port.json` | Owned GenOffice Docs runtime boundary and inclusion/exclusion policy | `7e0d4bd4b3124944aa67bea50c206286fa5b7fc9d51ee20432ebfd9f707fc4dd` |
| `provenance/upstream-lock.json` | Combined GenOffice/rhwp upstream lock | `6023b284651e8f7938f9153622f411922d4657210b8080cd86ad342135adf3bb` |
| `.build/debug/PublicDocumentApp` | Invoking application binary for this run | `e55d46b24bb31afbe91e4f54adb6abe17b16554338673858efb38cb263c3d14a` |

Every scenario receipt records the snapshot revision and SHA-256, `allAuthoredElementIDsPreserved`, the selected/published/blocked/failed partition, loss reports with source element paths, and the upstream rhwp commit. Published results additionally bind artifact hash, byte count, validator, and ordered element-level validation records.

## Authoritative scenario dispositions

| Scenario and receipt SHA-256 | Selected | Published | Blocked | Failed | Loss reports | Snapshot |
| --- | --- | --- | --- | --- | --- | --- |
| `all-consented/receipt.json`<br>`c8711caab3c6d0a8b1eb6178a6c134778c7f1690e580a027e1dab2b8d7169348` | HWPX, HWP, DOCX, Markdown | DOCX, Markdown | HWPX, HWP | None | 4 semantic loss + 20 consented visual flattening | `revision-ac05-001`<br>`sha256:0614a7ff98fd9dad58e187f17ef453c198b7adc055775902e53f8f8979cdb56b` |
| `basic-hwp-family/receipt.json`<br>`28e5f9ae9dc4bbfbba0c0bc00170f5b640c93f02beb31965f192d70ccdb06d0a` | HWPX, HWP | HWPX, HWP | None | None | 16 consented visual flattening | `revision-ac05-basic-hwp-family`<br>`sha256:7c010e50e1ae576c939808864d853f1c57831987f3fb5e72e0553e7cb229d2eb` |
| `markdown-unconsented/receipt.json`<br>`d5c9e601018bb07eafaa51c76574092040c5f1c9f89ddaa77fb0884100bfc06b` | Markdown | None | Markdown | None | 1 unconsented visual flattening at `elements/3/inlines/inline-summary-keep` | `revision-ac05-keep-together`<br>`sha256:7087a6b0e4126780803d72ec71549e86d48d84f3fb392e11caa0efc02e5276f8` |
| `mixed-semantic-block/receipt.json`<br>`fefc9f2ed49cc59dcf1b762ff02e5510e84e542af0693cc4956d93c1290561b1` | DOCX, Markdown | DOCX | Markdown | None | 1 formula semantic loss at `elements/14` + 4 consented visual flattening | `revision-ac05-001`<br>`sha256:31bce08cc8750e4477a9f51741064aa86bf36547cf40e8a9b61ac42ef42fc22c` |
| `adversarial-markdown/receipt.json`<br>`f9bca132b9e6d3edadc6a5485721e6278ddd5074ee2b391ce1cb1043e18dc8fb` | Markdown | Markdown | None | None | None | `revision-ac05-adversarial-markdown`<br>`sha256:16cef6c6758bcd09c332f40ddc9a5a5924d07173446402aa592632b0067f13d6` |

The `all-consented` HWPX and HWP results are blocked because the pinned HWP-family adapter cannot preserve the approval-grid rich-inline structure or the summary table semantics. Their DOCX and Markdown siblings still publish. The reduced `basic-hwp-family` fixture omits those unsupported semantic structures and therefore publishes both HWP-family formats.

## Published artifact validation

| Scenario / format | Artifact SHA-256 | Bytes | Artifact-derived validator | Ordered element records |
| --- | --- | ---: | --- | ---: |
| `all-consented` / DOCX | `414b779b8274a55202ed1495afc0b9c69b787198802747ce2921320aecb2f7f3` | 11,906 | OOXML graph + formula/table/content verification | 14 |
| `all-consented` / Markdown | `c7f176b3cc7abbcdae3dcc4f94941c1c871f9bd745113748d394333116a0a223` | 3,289 | CommonMark table + marker-bound content verification | 14 |
| `basic-hwp-family` / HWPX | `b2ae83db3cbe48aa14e77b50333cada312e8062932ab8afa78e56521c60f7990` | 6,257 | rhwp artifact reopen + ordered text verification | 12 |
| `basic-hwp-family` / HWP | `d8c73cf4813e5bd2c5e0118e2b2ee886709dd9acd178ea8afa87a46f8c979b51` | 6,656 | rhwp artifact reopen + ordered text verification | 12 |
| `mixed-semantic-block` / DOCX | `3407708c7a988cef0e70f40e4d6e34a463a7e802c1e7d6fb2a6fe13aaf0c141b` | 12,268 | OOXML graph + formula/table/content verification | 15 |
| `adversarial-markdown` / Markdown | `68b926cfdd52ade8e28cc2153eef870951c8f3a8533da1abfcdee5fb50d7eafe` | 304 | CommonMark table + marker-bound content verification | 1 |

All six published results record `structuralValid=true`, `semanticValid=true`, and `validation.evidenceSource=artifact-derived`. The aggregate artifact receipt is `artifact-validation/summary.json` (SHA-256 `9c6bfe67dd7690d29e0ee7115e2b43e4851fb76e22fea56b754aa4a00fccd200`).

- Both DOCX artifacts are ZIP/CRC clean, every required OPC XML part is well formed, the styles and custom-XML relationships resolve, and their 14/15 custom-XML stable IDs exactly match 14/15 document SDTs and the ordered validation receipt. Repeating both exports from the same immutable revision and `savedAt` produced byte-identical files.
- Both Markdown artifacts use the exact stable-marker grammar. The 14-marker rich artifact and one-marker adversarial artifact match their ordered validation records; authored script/link markup remains inert.
- The exact bundled rhwp engine reopens both HWPX and HWP as one non-empty page with 23 paragraphs and identical ordered Korean text. HWPX has `application/hwp+zip`; HWP has CFB magic `d0cf11e0a1b11ae1` and `HWP Document File` metadata.
- Each DOCX result records `engineIdentity` for `@genoffice/docx-engine`, upstream commit `d8305ff2dc152593a1ec5639d77e6860c6a512bd`, arm64 Node `22.17.1`, Node SHA-256 `5c8cd3ab...aa25`, and CLI SHA-256 `43046343...70bc`.
- `runtime-bindings.json` additionally binds the final stable-inline-ID browser bundle, runtime manifest, complete input lock, owned port manifest, and combined upstream lock. The binding receipt SHA-256 is `7ec72f9b712f61ff9d0f8952c7d9f1d30c2f5ef63024eee36cbf7c711bb29efb`.

The root inventory is `output/ac-05/final-stable-inline-bound.Fy3So4/SHA256SUMS` (SHA-256 `5476618f6984703c7e9720525f02fc6ec61cb2b012c820362ad66780cf6ae8bf`). It binds all 28 evidence files: six artifacts, five policy receipts, four runtime-failure receipts, direct format probes, runtime identities, and verification summaries. Verification command:

```sh
(cd output/ac-05/final-stable-inline-bound.Fy3So4 && shasum -a 256 -c SHA256SUMS)
```

Result: all 28 listed files returned `OK`.

## Per-format runtime failure isolation

`DocumentExportEngine` performs authorable-element identity preflight once, then evaluates and exports each selected format inside its own failure boundary. Runtime failures are serialized as `{format, stage, errorCode, userDiagnostic}` where `stage` is `adapter`, `validation`, or `destination`. A failure appends that format to `failedFormats`, preserves already published siblings, and continues with later formats.

The focused isolation harness covers five independent boundaries. Its aggregate receipt is `runtime-failure-isolation/summary.json` (SHA-256 `9c7fe381eb4615dad5ed9615070616f2771c638eca019e4cfaf7c172d9db19e7`):

1. A missing or unapproved rhwp engine produces an HWPX `adapter` failure with `errorCode=rhwp-failed`; DOCX and Markdown still publish, and rhwp/temporary files are absent afterward.
2. A pre-existing HWPX destination produces a `destination` failure with `errorCode=destination-exists`; its original SHA-256 is unchanged, DOCX and Markdown still publish, and no temporary file remains.
3. A missing GenOffice runtime produces a DOCX `adapter` failure with `errorCode=missing-genoffice-docx-engine`; HWPX, HWP, and Markdown still publish.
4. A byte-modified GenOffice CLI is rejected by the same integrity boundary; HWPX, HWP, and Markdown still publish and no GenOffice temporary files remain.
5. Duplicate authored element IDs fail global preflight before the destination directory or any artifact is created.

Exact focused verification command:

```sh
.venv/bin/python -m pytest -q \
  tests/test_ac05_format_export.py \
  tests/test_ac05_export_hardening.py \
  tests/test_ac05_export_failure_isolation.py \
  tests/test_hwp_export_seed_contract.py \
  tests/test_genoffice_docx_adapter.py
```

Result on 2026-08-10: 27 passed. This command also regenerates artifacts in isolated pytest temporary directories, exercises the native `--export-self-test` entry point, rejects mutated artifact content, verifies HWP compound-file metadata and HWP 5.1 records, checks the bundled rhwp hash contract, and binds the GenOffice normalizer identity.

The five policy scenarios are clean policy/serialization cases, so every one records `failedFormats=[]` and `failures=[]`. Deliberately induced runtime failures are separately retained under `runtime-failure-isolation/`; they are never merged into clean policy receipts.

## Evidence boundary and remaining limitations

- AC-05 proves format selection, policy disposition, serialization, artifact-derived validation, and failure isolation. It does not by itself prove that Polaris Office, Hancom, Microsoft Word, or an approved Markdown client opens the files without a warning; exact-client observations belong to AC-07.
- The rich `all-consented` fixture does not currently publish HWPX or HWP. Only the reduced 12-element HWP-family fixture is inside the adapter's current loss-aware publishable capability.
- Within each request, every selected format is evaluated against the same immutable `snapshotRevisionID` and `snapshotHash`. The rich all-format request intentionally blocks HWPX/HWP for semantic loss; the real HWPX/HWP artifacts therefore come from the separately identified reduced HWP-family snapshot.
- The evidence root binds the invoking debug application hash. Packaged-app signing, GUI interaction, accessibility, and named-client reopen claims remain assigned to their package, AC-07, and AC-08 criteria.
- Receipt field `rhwpCommit` binds the upstream source revision, while `runtime-bindings.json` binds the exact rhwp executable and complete final GenOffice runtime identity, including the stable-inline-ID browser bundle and its build-input/provenance locks.
