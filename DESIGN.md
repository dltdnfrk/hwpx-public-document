# Public Document Studio Design System

## 1. Atmosphere & Identity

A quiet, trustworthy Korean public-sector writing desk with the density of a professional document editor. The signature is the teal document mark beside an inspection-oriented outline: authority and incomplete work stay visible without turning the editor into a dashboard. Design variance is 3, motion intensity is 2, and visual density is 5.

## 2. Color

| Role | Token | Value | Usage |
| --- | --- | --- | --- |
| Ink | studio-ink | #202726 | Primary text |
| Muted ink | studio-muted | #66706D | Metadata and secondary labels |
| Disabled ink | studio-disabled | #909895 | Unavailable ribbon controls |
| Accent | studio-accent | #006879 | Active controls and progress |
| Strong accent | studio-accent-strong | #005361 | Active text and brand depth |
| Soft accent | studio-accent-soft | #E8F4F5 | Selected states |
| Accent border | studio-accent-border | #AFD1D5 | Selected-control boundaries |
| Canvas | studio-canvas | #DFE4E3 | Page surround |
| Surface | studio-surface | #FFFFFF | Page and chrome |
| Panel | studio-panel | #F7F9F8 | Outline and status surfaces |
| Hover surface | studio-hover | #EDF1F0 | Outline hover state |
| Border | studio-border | #D7DDDB | Quiet separation |
| Strong border | studio-border-strong | #B7C1BE | Region boundaries |
| Document rule | studio-document-rule | #7F8986 | Authored table rules |
| Document fill | studio-document-fill | #EEF4F3 | Authored table headings |
| Warning | studio-warning | #A64B00 | Required review |
| Warning ink | studio-warning-ink | #64320C | Required-review body copy |
| Warning surface | studio-warning-soft | #FFF4E5 | Required-review callout |
| Success | studio-success | #176B4A | Local and completed states |
| Focus | studio-focus | #0B75C9 | Keyboard focus |

The layout grammar comes from the pinned GenOffice Docs editor at commit d8305ff2dc152593a1ec5639d77e6860c6a512bd; its upstream blue identity was replaced by the owned teal ramp.

## 3. Typography

| Level | Size | Weight | Line height | Usage |
| --- | --- | --- | --- | --- |
| Document title | 28px | 700 | 1.35 | Page title |
| Panel title | 18px | 700 | 1.3 | Template name |
| Document heading | 17px | 700 | 1.5 | Numbered sections |
| Document body | 15px | 400 | 1.78 | Authored content |
| UI body | 13px | 400-700 | 1.4 | Ribbon and panels |
| Caption | 11px | 400-700 | 1.4 | Status and group labels |
| Eyebrow | 10px | 700 | 1.3 | Authority label |

The interface uses the macOS system stack with Apple SD Gothic Neo and Malgun Gothic Korean fallbacks. The document surface uses the same Korean-first stack until project-owned semantic styles select a document font.

## 4. Spacing & Layout

Spacing uses a 4px base with steps at 4, 8, 12, 16, 20, and 24px. The shell has fixed title, tab, ribbon, and status rows. The workspace owns remaining height; the outline and canvas own independent vertical scrolling. The outline is 260px and the document page is 794px wide. Below 1100px the outline collapses so the paper remains fully reachable. The supported app window floor is 920 by 640.

## 5. Components

### Studio shell

- Structure: title bar, tabs, ribbon, outline plus canvas, status bar.
- States: outline shown or hidden; active tab; offline status announcement.
- Accessibility: landmark labels, stable keyboard order, visible focus.
- Motion: native scrolling only; no decorative animation.
- Layout: bounded scroll-body shell with independently scrolling outline and canvas.

### Ribbon control

- Structure: tab, grouped native button, optional icon and group label.
- States: default, hover, active, focus.
- Accessibility: actual buttons, Korean labels, aria-selected for tabs.
- Motion: immediate state change.

### Document outline

- Structure: template authority heading, ordered section list, completion checklist.
- States: current, complete, incomplete, collapsed.
- Accessibility: ordered semantics and named progress.
- Motion: reduced-motion-aware native scroll to the selected heading.

### Template governance

- Structure: signed-catalog trust state, document-pinned template identity, available entries, update, rollback, and official-rule disclosure.
- States: loading, signature verified, newer template available while the document remains pinned, rollback available, update rejected.
- Accessibility: native buttons and disclosure, visible focus, live status announcements, and no color-only trust signal.
- Motion: none; catalog changes are immediate state transitions.

### Document page

- Structure: editable A4-proportioned article, semantic headings, table, review marker.
- States: idle and focused.
- Accessibility: named editable region, readable Korean body size, focus outline.
- Motion: none.

### Batch export progress

- Structure: overall native progress indicator, document-by-format status rows, summary, and cancel action.
- States: queued, exporting, validated, published, failed, cancelled, and recovered after interruption.
- Accessibility: named progress and item list, live Korean status announcements, full keyboard operation, and text labels in addition to success or warning color.
- Motion: none; progress advances only when a durable export lifecycle transition is recorded.

## 6. Motion & Interaction

All feedback is state-bearing: tab selection, outline visibility, heading navigation, formatting, review-marker insertion, save status, and zoom. No perpetual or decorative motion is permitted. System reduced-motion and reduced-transparency preferences are respected.

## 7. Depth & Surface

The strategy is mixed: tonal separation for chrome and outline, strict borders for functional regions, and a two-layer shadow only for the physical paper page. Selected controls use the soft accent instead of elevation.

## 8. Accessibility Constraints & Accepted Debt

Target WCAG 2.2 and KWCAG AA: 4.5:1 body contrast, 3:1 large text and control boundaries, keyboard reachability, visible focus, named landmarks, and status announcements. The minimum 920px width is intentional for this desktop-only macOS authoring application.

No AC-08 accessibility debt remains accepted. Automated browser checks are
paired with packaged WKWebView accessibility-tree inspection and a recorded
VoiceOver cursor journey because browser automation alone cannot model the
native assistive-technology surface. The bound evidence is recorded in
`docs/ac-08-accessibility-evidence.md`.
