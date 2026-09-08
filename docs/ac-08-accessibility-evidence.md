# AC-08 accessibility and interface-fidelity evidence

Recorded on macOS 26.5.2 (`25F84`), arm64. The current browser evidence is
`.omo/evidence/visual-r3/ac08`; the current packaged native evidence is
`.omo/evidence/native-ax-r12`; and the exact-package blocker receipt is
`.omo/evidence/visual-r3/ac08/native-voiceover-receipt.json`.

## Verdict and evidence boundary

The final GenOffice Studio browser, keyboard, automated WCAG/KWCAG, supported
desktop viewport, package-binding, and dual visual-review gates **PASS**.

Full native VoiceOver remains **BLOCKED** by
`exact-package-ax-tree-empty`. The console was unlocked and VoiceOver was
started from an initial off state, but the exact current package continued to
expose only application/menu AX roles and no AXWindow or WKWebView descendants.
All seven required native journeys are explicitly `NOT_RUN`; no native cursor
transition is claimed. VoiceOver and the owned app process were restored to
their initial off/terminated states.

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

## Current package and source binding

The machine-readable browser receipt records current source and packaged hashes
for `index.html`, `styles.css`, and `app.js`; all
`packagedStudioMatchesTestedSource` values are `true`. The native happy action
log binds the visible package window, screenshot, executable, four real export
formats, signatures, artifact hashes, process cleanup, and the attempted AX
snapshot. Hash values are intentionally read from those current receipts rather
than duplicated in this prose.

## Native VoiceOver — blocked

At evidence generation time the console was unlocked. The exact package emitted
an `opened` readiness receipt and a visible CGWindow screenshot. The native AX
walker and System Events nevertheless exposed no AXWindow or WKWebView
descendants. Starting VoiceOver did not change the exposed roles. VoiceOver was
then returned to off and the owned app process was terminated.

The exact-package blocker receipt records these seven journeys as `NOT_RUN`:

1. `guided-authoring`
2. `AI-proposal-review`
3. `AI-consent`
4. `official-rule-and-template-guidance`
5. `loss-resolution`
6. `single-export`
7. `batch-export`

Completion of these seven external journeys requires macOS to expose AXWindow
and WKWebView descendants for the exact final package; the blocker receipt
contains this rerun condition.

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
| native happy/invalid package QA | 0 | visible CGWindow, atomic invalid rejection, real exports |
| AX/VoiceOver observation | blocked | exact package exposes application/menu roles only; VoiceOver restored off |

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
