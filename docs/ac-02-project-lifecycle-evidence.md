# AC-02 app-native project lifecycle evidence

Recorded: 2026-08-09 (Asia/Seoul)

## Implemented authority boundary

`DocumentProject` is the persisted source of truth. It records schema and document identity, locale, title, the current revision, ordered stable-ID elements, sanitized rich structure, stable inline IDs, assets, styles, pinned template metadata and checklist state, evidence-to-claim links, immutable revisions, history events, and AI proposal history. The WKWebView document is rehydrated from this project and remains a projection.

The native store writes the canonical `project.json` atomically. Autosave writes an independent `recovery.json`; a successful explicit save atomically publishes the project and removes recovery state. Startup prefers the recovery snapshot after interruption. Reopen loads the last canonical save, while Recover explicitly loads the recovery snapshot. Project inspection exposes counts and binding identities without replacing the authoritative project.

Legacy schema version 0 is decoded, migrated to version 1, given a `schema-migrated` history event, and atomically persisted without changing document, element, or revision identities.

Rich project content is sanitized both when captured and when rehydrated. Only the editor's supported structural tags and safe attributes survive. Persisted markup is parsed in an inert contextual container before sanitized cloned nodes replace the projection; it is never assigned directly to the live document.

## Automated receipts

Command:

```text
node --check Resources/Studio/app.js
swift build -c release
python3 -m pytest -q
```

Result: JavaScript syntax passed, the Apple Silicon release build exited 0, and all 48 tests passed.

Native lifecycle receipt:

```json
{"assetsPreserved":true,"derivedExportDidNotMutateProject":true,"evidenceLinksPreserved":true,"recoveredAutosave":true,"recoveryFileRemovedAfterCommit":true,"revisionHistoryPreserved":true,"richStructurePreserved":true,"schemaVersion":1,"stableElementIDs":true,"stylesPreserved":true,"templateBindingPreserved":true}
```

Migration receipt:

```json
{"documentID":"document-legacy-001","elementIDs":["element-legacy-heading","element-legacy-body"],"fromSchemaVersion":0,"historyEvent":"schema-migrated","revisionCount":1,"toSchemaVersion":1}
```

Native launch receipt:

```json
{"visibleWindowCount":1}
```

Release executable SHA-256: `8f7a4238597022b49ecfc6096a36ab27cfd89c0267a22a346b6ac797fde08dfd`.

## Browser and native manual QA

A headed Playwright session used the shipped editor DOM and bridge message contract. It applied `<strong>굵게 보존</strong>` to a paragraph, changed a table cell to `표 수정 보존`, saved, fully reloaded, and rehydrated the captured project. It then prefixed hostile persisted image/script markup before rehydration. The observed result was:

```json
{"strongText":"굵게 보존","tableText":"표 수정 보존","stableInlineIDCount":6,"unsafeNodeCount":0,"injectedValue":null}
```

The packaged native app was launched with an isolated project root. The title field received a no-op edit, autosave produced a recovery snapshot containing rich content for all 14 elements and 55 stable inline IDs, and the process was forcibly interrupted. Relaunch restored the exact title `2026년 생활안전 추진계획` and announced `중단 전 자동저장 상태를 복구했습니다.` through the visible status surface and accessibility tree.

The project inspector visibly reported schema version, stable document and revision IDs, 14 elements, six styles, one evidence link, revision/history counts, and template ID/version. At the supported 920 × 640 minimum window, all five project controls remained available, the outline collapsed, and the document canvas remained scrollable.

## Visual evidence

| State | SHA-256 |
| --- | --- |
| `.omo/evidence/ac02/studio-initial.png` | `c6bbdcc9d74988738b6739cb874b445081bce4adfc922f4de419d3786b83686f` |
| `.omo/evidence/ac02/studio-inspector.png` | `cd40979e1a7ead665c31698d13f48b739496725dc5aed5c8cf8e90068cfa16ba` |
| `.omo/evidence/ac02/studio-recovered.png` | `e85eaf762580fac5035ce640fab50935c3c144712a8360b9812efa967ca83cbd` |
| `.omo/evidence/ac02/studio-minimum.png` | `908884e3590bf2aaa9cf8cc0394d7303c22d071ff75f4c35e5c02d3685d1908e` |

Each image is a fresh 3024 × 1964 RGBA PNG captured after the final rendered-source change. The final independent design-system/functional and visual/CJK reviews inspected the complete four-state set.

## Scope note

HWPX, HWP, DOCX, and Markdown remain derived projections. The lifecycle self-test writes a derived Markdown preview and proves the canonical project bytes are unchanged. Format-adapter behavior and compatibility evidence belong to later acceptance criteria.
