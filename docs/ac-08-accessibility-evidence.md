# AC-08 accessibility and interface-fidelity evidence

Recorded on macOS 26.5.2 (`25F84`), arm64. The canonical browser evidence is
`output/playwright/ac08-final-bound.UhLbrs`; the exact-package native blocker is
`output/ac-08/final-bound.R5vshb`.

## Verdict and evidence boundary

The final GenOffice Studio browser, keyboard, automated WCAG/KWCAG, supported
desktop viewport, package-binding, and dual visual-review gates **PASS**.

Full native VoiceOver remains **BLOCKED** because the active macOS console was
locked. All seven required native journeys are explicitly `NOT_RUN`; no native
focus, label, state, announcement, or transition is claimed. AC-08 therefore
remains `BLOCKED` overall and is not promoted to a complete criterion PASS.

The browser run targets `Resources/Studio` and is bound to the same files in an
exact freshly packaged application:

- Application: ephemeral `PublicDocument.app`
- Executable SHA-256:
  `ec5ed6931fbb5f3a8560515fba5506cb694a817ef45e6f34b9d3f70a660a988b`
- Architecture: arm64
- Strict deep code-signature verification: PASS
- Package manifest: 34/34 files and hashes match; zero mismatches
- Packaged Studio and GenOffice browser bundle: byte-identical to tested source

The package binding is retained in `package-binding.json`; the full path is an
ephemeral local audit path and is not a distribution or notarization claim.

## Real-browser result

Chrome 151.0.7922.108, Playwright 1.55.0, and axe Playwright 4.10.2 ran six
serialized tests with one worker. The result is **6/6 passed** in 6.0 seconds.
The focused Python AC-08 source contract also passes **4/4**.

The browser coverage includes:

1. real GenOffice/Tiptap editor initialization and stable block identities;
2. formatting, save, export, and reopen with exact ordered inline identities;
3. keyboard outline, official-rule, template, focus-transfer, and dialog flows;
4. AI consent denial, consented request, immutable proposal review, and focus
   restoration;
5. single-export consent, validated result, and element-path loss reporting;
6. batch-export progress, cancellation, disabled-close state, and text status;
7. project-inspection redaction and user-facing labels; and
8. the 375, 768, 920, and 1280 desktop viewport contract.

## Keyboard-edit and inline-identity regression

The final test explicitly restores focus to `element-summary-body`, proves the
real `[contenteditable="true"]` owns focus, moves the macOS caret to the end with
`Meta+ArrowRight`, and types the edit before inserting the review marker.

The exact text
`첫 문장 강조 문장 기울임 문장\u00a0편집 [확인 필요]` is asserted for the
saved snapshot, exported snapshot, and reopened snapshot. The ordered IDs
`inline-alpha`, `inline-bravo`, and `inline-charlie` must exactly equal the
serialized `data-inline-id` anchors at every boundary. The final
`genoffice-editor-1280.png` visibly shows the correctly placed edit and contains
no former `편집첫` artifact.

## Axe, ARIA, focus, and redaction

Axe ran WCAG 2 A/AA, WCAG 2.1 AA, and WCAG 2.2 AA rules against eight distinct
live states:

1. `genoffice-editor`
2. `main-editor`
3. `project-inspection`
4. `ai-consent`
5. `ai-proposal-review`
6. `single-export-loss-consent`
7. `single-export-result`
8. `batch-export-progress`

All eight states record zero violations. Four non-empty ARIA snapshots cover
the main editor, AI proposal, loss report, and batch progress. They expose
coherent Korean landmarks, dialogs, controls, status, progress, and table
semantics without raw element, inline, document, revision, template, proposal,
command, operation, batch, UUID, or filesystem identifiers.

Browser assertions also prove visible and programmatic focus, Korean accessible
names, outline pressed state, disclosure activation, consent focus, proposal
initial focus and opener restoration, progress semantics, cancellation state,
and color-independent status text.

## Viewports, screenshots, and Korean rendering

Twelve fresh original PNGs are retained:

- `studio-375.png`
- `studio-768.png`
- `studio-920.png`
- `studio-1280.png`
- `genoffice-editor-1280.png`
- `template-rules-keyboard-1280.png`
- `project-inspection-1280.png`
- `ai-consent-1280.png`
- `ai-proposal-review-1280.png`
- `single-export-loss-consent-1280.png`
- `single-export-result-1280.png`
- `batch-export-progress-1280.png`

`capture-verification.json` proves valid PNG signatures and expected dimensions
for all 12. The supported floor is 920×640, where the outline is intentionally
collapsed; 1280×820 restores the full outline. The 375×720 and 768×720 captures
document fixed desktop-minimum behavior and do not claim mobile support.

Korean visual checks confirm:

- `높이고자 함.` remains grouped without a standalone `함.` orphan;
- `1. 개요 [확인 필요]` retains the marker boundary space;
- `[확인 필요] 최근` retains its boundary space; and
- the repaired keyboard edit is naturally spaced with no tofu, mojibake,
  clipped baseline, black compositor region, or missing surface.

## Frozen-reference image diffs

The four reference images are same-source capture inputs, not acceptance
verdicts. Final package identity is established independently by the browser
receipt and package binding.

| Width | Dimensions | Differing pixels | Similarity | Alpha | Hotspots |
| --- | --- | ---: | ---: | --- | ---: |
| 375 | 375×720 | 0 / 270,000 | 100 | intact | 0 |
| 768 | 768×720 | 0 / 552,960 | 100 | intact | 0 |
| 920 | 920×640 | 0 / 588,800 | 100 | intact | 0 |
| 1280 | 1280×820 | 0 / 1,049,600 | 100 | intact | 0 |

## Independent visual reviews

Two independent read-only reviews opened all 12 original captures directly.
Both returned **PASS / HIGH confidence** with no findings after the keyboard-edit
regression was repaired. They separately confirmed the real DOM/component
surface, CJK wrapping and spacing, supported-window geometry, complete dialogs,
visible focus, semantic states, zero-diff images, package identity, and honest
native blocker boundary.

Their reports are `visual-pass-a.md` and `visual-pass-b.md` in the canonical
browser evidence root.

## Exact package binding

| Artifact | SHA-256 |
| --- | --- |
| application executable | `ec5ed6931fbb5f3a8560515fba5506cb694a817ef45e6f34b9d3f70a660a988b` |
| package binding | `19dd0c93711586fca00a6595c9f5153121c2d2d49b2f8018dece069e5c48eb3c` |
| 34-file package manifest | `3ffdc842262b65830233deaa8a3112ca8ac4764d070c007a219b0d0e278bc576` |
| browser receipt | `1f9557d7938c15f7aab96884da946298bbafef9dc635deb624ef74cbaf780580` |
| run summary | `eabdd2a2ae29bb44d29e6a9732ea7799a29ac01fc4087c1d322241b4be0ea50c` |
| capture verification | `3c58eb578e6f0004bd679e6af23607d11c2255a6878e26c2a4f2d7648af72939` |
| verification receipt | `a0e46870666745a202b39a9d80d5b8f24da268132d2c16618efe4ae51e5db7d8` |
| axe results | `cdcd9055e78bfdbcd675adc73c43b4362acbb53f3a3497d08ec8b3ac152ee33f` |
| Pass A | `2c7ceb58fd36ff259c790ef836fa2f028da9602d0af2a8e0ab1640f9bcf9513f` |
| Pass B | `2344634a70f0e92916d16d64ad4f962177fed723021c35859d7e0b30a1517ec9` |
| VoiceOver blocker | `6689a46d06493ba058e35fdd01ceea5edae202f4ffb17402fc36f9fceac5b83b` |

## Bound source, runtime, and provenance

| Artifact | SHA-256 |
| --- | --- |
| `Resources/Studio/index.html` | `2c3de4829b1f617bb20d38997f6ae849b38d7965024613c28094c7878f632fcc` |
| `Resources/Studio/styles.css` | `b905fba51298ac582eb2103dea6a0163d493cccc1f12613c662716f679c831d7` |
| `Resources/Studio/app.js` | `baf94d4df0b25cef654fc1f7eadbaf8a27b880794deb44d3ecfc0bff1c735e42` |
| GenOffice browser bundle | `0e171084942762e85ac30f134a82d3b6aa94904456656f156b7a07170765d33a` |
| `GenOfficeFork/browser.tsx` | `d02b63666c6064e524a788609db8521469e1754bfc87eed74256a93d7d327673` |
| inline-identity extension | `8049a3e3c80590ffa7f954ab393301187614826cf86d69a02c262694ae28de68` |
| AC-08 browser test | `916ebe4eadfea780c6cae1b3eeaa4fd4e6fb6e911cf534f4647026f31c85ac51` |
| focused Python test | `b8d15174d541a9e602da1ba17cba6d46c2989cf0a131b9747f50a26ab1ec273b` |
| `DESIGN.md` | `59752824f6d27ac8bf045d07c9de8ca1da96b6051c2266a89efb56ceef295ceb` |
| runtime input lock | `3f1db99bedabfc47e1990f9229ce73fef6ff20f5a4642a18372416a920b3af79` |
| runtime manifest | `4b691934c27230ecb6a4c5defcc11b625f1f3f20a82ff21e6867e04641d19616` |
| GenOffice port provenance | `7e0d4bd4b3124944aa67bea50c206286fa5b7fc9d51ee20432ebfd9f707fc4dd` |
| upstream lock | `6023b284651e8f7938f9153622f411922d4657210b8080cd86ad342135adf3bb` |

## Native VoiceOver — blocked

At evidence generation time, `ioreg` reported
`CGSSessionScreenIsLocked=Yes`. VoiceOver was not running before or after the
observation, and no VoiceOver toggle, key, cursor, or application action was
sent because it would have targeted the lock/login surface.

The exact-package blocker receipt records these seven journeys as `NOT_RUN`:

1. `guided-authoring`
2. `AI-proposal-review`
3. `AI-consent`
4. `official-rule-and-template-guidance`
5. `loss-resolution`
6. `single-export`
7. `batch-export`

Completion requires an unlocked interactive console and end-to-end VoiceOver
recording of all seven journeys against the exact final package.

## Verification commands

| Command family | Exit | Result |
| --- | ---: | --- |
| canonical boundary checks | 0 | cwd, Git top-level, and origin match `PROJECTS.md` |
| exact temporary application package | 0 | arm64, strict codesign, 34/34 manifest |
| serialized Playwright suite | 0 | 6/6 passed |
| `node --check Resources/Studio/app.js` | 0 | syntax valid |
| focused AC-08 pytest | 0 | 4/4 passed |
| axe aggregation | 0 | 8 states, 0 violations |
| PNG signature/dimension validation | 0 | 12/12 valid |
| four image diffs | 0 | all dimensions/alpha pass, similarity 100 |
| two independent visual reviews | 0 | PASS / PASS |
| console and VoiceOver observation | 0 | locked; VoiceOver absent; no action sent |

The complete command strings, exit codes, hashes, freshness checks, and evidence
leaves are in `verification-receipt.json` and `SHA256SUMS`.

## Noncanonical audit history

Earlier roots are retained only for audit history and must not be referenced by
the final source map:

- `jzs6z6` / `fH4RJi`: CJK orphan and boundary-spacing defects;
- `TYiAp3` / `XOyXfp`: inline IDs detached from serialized anchors;
- `tmrzDB` / `I7iHfA`: runtime/package identity drift;
- `AMcHEx` / `cAYR4u`: keyboard edit inserted at the wrong visible boundary;
- `LP1eDy` / `JIDTRZ`: failed post-fix browser attempt.

Only `UhLbrs` and `R5vshb` are canonical for this AC-08 refresh.
