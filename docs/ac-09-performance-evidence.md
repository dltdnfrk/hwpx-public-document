# AC-09 Performance Evidence

Date: 2026-08-10
Evidence root: `output/ac-09/final-inline-id-bound.UjyI5G`
Executable: final arm64 release build, `sha256:3b076294e69f3986f1755b235ffe65c9f2cc02a5038a9d2f0a75e56ff4480790`

## Verdict

AC-09 is `PASS` on the recorded Apple Silicon environment. The exact final arm64 release executable exported the separate frozen 100-page and 50 MiB app-native fixtures through HWPX, HWP, GenOffice DOCX, and Markdown. Every measured export, including structural, semantic, and authored-content validation, completed within the 30-second threshold. The HWPX and HWP observations for the 100-page fixture each independently report exactly 100 rendered pages.

The machine-readable authority is `performance-receipt.json` (`sha256:f75601716b66130d35cbacc986c03dd84077d26016958308cb308322f4e89207`). `runtime-binding.json` (`sha256:26f87ea548d2ba575ce553fabb122b9360cf0ed84a00af1db4cd29a5f3f34ac9`) binds the receipt to the exact executable, source/resource input aggregate, final inline-ID GenOffice runtime, bundled Node, and rhwp. `SHA256SUMS` (`sha256:22a7b24505f0fa20f8cb55f72087b469c21e06fcda24dbfa2bf79680c647d5a1`) binds 18 receipt, artifact, interaction, and runtime-binding files. Each export row binds its operation ID, fixture snapshot hash, authored-content hash and byte count, artifact-relative path, artifact hash and byte count, validator, duration, and independent structural, semantic, and authored-content verdicts.

## Recorded environment

| Field | Observation |
| --- | --- |
| Hardware | Mac17,9, Apple M5 Pro |
| Architecture | arm64 |
| Memory | 68,719,476,736 bytes |
| macOS | 26.5.2, build 25F84 |
| Application | Public Document Studio 0.1.0 |
| Recorded at | 2026-08-09T20:38:37Z |
| Profile | 1.0.0, `sha256:8fe858c46901af2888169d4afbda71f2d9b92100d804fafe329ce6c10ac9dc39` |

The tested executable is a 2,714,144-byte thin arm64 Mach-O. The sorted SHA-256 lines for every regular file under `Package.swift`, `Sources`, and `Resources` produced the aggregate `sha256:edcd21ecb400c061efea088750a4f97d6679c4463f1a27aafb5f15c9db31af18` both before and after the benchmark. This receipt is release-executable performance evidence; final package rebinding is handled separately by AC-10.

## Runtime binding

| Runtime | Exact identity |
| --- | --- |
| GenOffice upstream | `d8305ff2dc152593a1ec5639d77e6860c6a512bd` |
| GenOffice runtime manifest | `sha256:4b691934c27230ecb6a4c5defcc11b625f1f3f20a82ff21e6867e04641d19616` |
| GenOffice runtime input lock | `sha256:3f1db99bedabfc47e1990f9229ce73fef6ff20f5a4642a18372416a920b3af79` |
| GenOffice upstream lock | `sha256:6023b284651e8f7938f9153622f411922d4657210b8080cd86ad342135adf3bb` |
| `@genoffice/docx-engine` normalizer | `sha256:43046343861265b0c89490f427cbf00118e42531d7144ff36173b543044170bc` |
| GenOffice browser bundle | `sha256:0e171084942762e85ac30f134a82d3b6aa94904456656f156b7a07170765d33a` |
| Bundled Node | 22.17.1 arm64, `sha256:5c8cd3ab2559b530fceca01776064c56687619475a7ffc339178524af6cdaa25` |
| Bundled rhwp | `sha256:a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b` |

The earlier `final-genoffice-bound.2Mbmme` run is preserved but became provisional when the inline-ID product defect required a new GenOffice browser bundle, runtime manifest, input lock, and provenance lock. After the corrected runtime passed Chrome, WebKit, and inline-ID regression gates and its owners declared the source frozen, the retained `final-inline-id-bound.UjyI5G` benchmark ran once in a coordinated quiet window. No concurrent Swift, pytest, rhwp, GenOffice, or AC-09 benchmark process was observed during that final run. The wall-clock duration for the complete eight-export and interaction run was 82.57 seconds.

## Frozen fixtures

| Fixture | App-authored elements | Authored UTF-8 | Snapshot bytes | Authored-content hash | Snapshot hash |
| --- | ---: | ---: | ---: | --- | --- |
| 100-page | 2,041 | 90,574 | 496,011 | `sha256:0b4a3d567135b6bcc3d5bdf56d726513e0804f87e9d0f1a6ce7157d3a5f9a2d4` | `sha256:d71c2bb3a0f578db9fb5babb66a5a3755bdb53335f0c2c24fb2da0d711830c91` |
| 50-mb | 25 | 52,428,800 | 52,482,975 | `sha256:23c8d66c6615048f0417326dceabf87c05006ed006dba776220e6008ea2bcfb3` | `sha256:b392d167aafa9e2e803f1cf170cf9cadc604744add329df66f01c1a5d0ee92ed` |

The 50 MiB corpus is not revision metadata padding. It consists of 25 deterministic 2 MiB `DocumentElement.text` chunks containing explicit canonical-decomposed Korean lines. Both the authored UTF-8 threshold and the independently encoded project-snapshot threshold are `PASS` in the receipt. The profile freezes 30,000 ms per export, 100 ms main-thread heartbeat, 250 ms first progress, 5,000 ms maximum progress gap, 100 ms cancellation request, and 1,000 ms cancellation completion.

## Export observations

| Fixture | Format | Duration | Artifact bytes | Artifact SHA-256 | Rendered pages | Result |
| --- | --- | ---: | ---: | --- | ---: | --- |
| 100-page | HWPX | 0.603 s | 27,366 | `c00206ef513aafb2748f5202ea9b354d594c1cc9ef1b1c19e3783bd682026c2d` | 100 | PASS |
| 100-page | HWP | 0.710 s | 22,528 | `02563d83db14a27a7117c2aaaa305c5a66471adf04f4c53ca1f87e8645b7ff51` | 100 | PASS |
| 100-page | DOCX | 0.389 s | 801,907 | `67b7a247e5654c85e1f17540d490cdf7be5672c29dc0f2cba52abfe1ab65793f` | n/a | PASS |
| 100-page | Markdown | 0.253 s | 465,814 | `8abf3b03ed78968698d6b0989535a326664602bd67cb83895d76771669a86b7e` | n/a | PASS |
| 50-mb | HWPX | 24.684 s | 415,904 | `e21c4c0af67b42a6415e9adb3563d27ea6e0387cfc59259c0458517c12ea23c5` | n/a | PASS |
| 50-mb | HWP | 25.274 s | 251,392 | `281d205e14dc9eb81bff9e85cb668cd4dad52dbb48b4c4b271e9a0b1b9c4e49d` | n/a | PASS |
| 50-mb | DOCX | 5.220 s | 52,442,401 | `cdd66dd2c6dffec3f7cf9a02f7621f94ffe415721cb67e6c03974ac26975fda4` | n/a | PASS |
| 50-mb | Markdown | 24.619 s | 52,674,025 | `f3de3fdffbe516b14ad5e1629919835370ed15cec70cb11e4843c82c1ec1b68a` | n/a | PASS |

The slowest bound observation was the 50 MiB HWP export at 25.274 seconds, leaving 4.726 seconds of margin. HWPX and HWP reopen through `rhwp export-text`; DOCX is normalized by the pinned GenOffice DOCX engine and validates the actual `word/document.xml` authored body; Markdown validates the UTF-8 projection after reversing only its specified `<br />` line-break representation. All eight rows report `authoredContentValidated: true`.

## Interaction thresholds

| Observation | Measured | Threshold | Result |
| --- | ---: | ---: | --- |
| Maximum main-thread heartbeat gap | 14.972 ms | 100 ms | PASS |
| First progress event | 0.938 ms | 250 ms | PASS |
| Maximum progress gap | 294.558 ms | 5,000 ms | PASS |
| Cancellation request | 0.000417 ms | 100 ms | PASS |
| Cancellation completion | 0.252 ms | 1,000 ms | PASS |

The runner observed 7,995 main-thread heartbeats and 14 native batch-progress events. Cancellation was requested through `BatchExportCancellation` and the coordinator returned a cancelled manifest within the frozen completion bound.

## Reproduction and validation

Run `swift build --configuration release`, then invoke `.build/release/PublicDocumentApp --performance-self-test <new-empty-evidence-directory>`. The retained final run deliberately executes this expensive command once. The frozen profile test is `uv run pytest -q tests/test_ac09_performance.py::test_benchmark_profile_is_frozen_and_executable`.

The focused frozen-profile pytest passed. A separate retained-evidence check verified all eight unique fixture/format pairs, every artifact hash and byte count, HWPX/DOCX ZIP integrity, HWP signatures, exact 100-page counts through rhwp, all authored-content verdicts, the arm64 hardware and executable, and all runtime-binding hashes. `shasum -a 256 -c SHA256SUMS` passes for all 18 evidence files. The fixture implementation builds fixed-size chunks directly and never repeatedly re-encodes a growing project, avoiding the former quadratic construction path.

External Polaris, Hancom, Word, and GenOffice interoperability claims remain governed by AC-07 and are not inferred from this performance pass.
