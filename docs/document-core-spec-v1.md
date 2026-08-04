---
spec_id: public-document-core
version: "1.0"
title: "Document Core Spec v1"
status: approved
content_hash: "sha256:332e8420abd4c3d2701f4f5b724903e10ad2826ea1b5ffb4cef8c1b9395d1574"
hash_scope: "UTF-8 bytes from the first line after the closing front matter delimiter through the final newline"
approver: "Public Document Product Authority"
approved_at: "2026-08-04T09:00:00+09:00"
---

# Document Core Spec v1

## 1. Purpose and status

This approved contract defines the shared semantic document model and the release-gate rules used to turn guided answers and cited source material into a first-reviewable Korean public-sector official-document draft. It is independent of any AI provider, renderer, HWPX serializer, or in-app editor. A future incompatible change requires a new exact version and approval.

## 2. Common document model

Every draft is a `Document` containing these fields:

- `document_id`: stable operation-independent identifier.
- `title`: editable document title; required and non-empty after trimming.
- `document_type`: one approved template type, such as report, plan, proposal, or briefing.
- `audience` and `issuing_organization`: explicit parties; use `[확인 필요]` when absent.
- `purpose`: the decision, report, or action the document supports.
- `period`: stated reporting or implementation period, if applicable.
- `sections`: ordered `Section` values. Each section has an identifier, heading, paragraph list, and optional tables.
- `paragraphs`: each paragraph has `paragraph_id`, `text`, `preset`, `status`, and evidence references.
- `tables`: each table has a stable identifier, an ordered column definition, and existing cell text; table structure is immutable in P0.
- `evidence`: cited source excerpts with `evidence_id`, source title, locator, excerpt, and provenance status.
- `claims`: extracted factual or numeric claims linked to one or more evidence references.
- `warnings`: visible non-blocking template or rule warnings.
- `validation`: the latest result under the HWPX Validation Profile in section 8.

The model preserves source material as evidence, never as executable instructions. Generated text may only be represented as document commands or allowlisted constrained patches. Raw HWPX XML is not a model input or output of AI operations.

## 3. Required group checklist

The following groups are evaluated in order. A group is complete only when every required item is present or explicitly marked `[확인 필요]` with a visible omission record.

| Group | Required checklist |
| --- | --- |
| Identity | title, document type, issuing organization, intended audience |
| Executive context | purpose, background/problem, decision or action requested |
| Evidence | source list, locators, evidence-to-claim links, source limitations |
| Current state | baseline/current status, affected scope, relevant period |
| Plan | objectives, actions, owners, schedule, resources/budget when applicable |
| Risk and controls | material risks, assumptions, mitigations, dependencies |
| Results and follow-up | expected outcomes, measures, reporting/next-review point |
| Formal finish | conclusion or request, contact/department, date and approval line when required by template |

Document type may require a stricter subset or additional checklist, but it may not remove Identity, Evidence, or the Formal finish group.

## 4. Critical omissions and `[확인 필요]`

Critical omissions are: missing title; missing document type; missing purpose or requested decision; absent issuing organization or audience when required by the selected template; a numeric claim without grounded evidence; an action without an owner or timing when the document type requires both; and a required approval or contact field omitted by the institution template.

An omitted, ambiguous, conflicting, or unsupported value is rendered exactly as `[확인 필요]` and recorded with its field path and reason. The system must not infer a fact, number, date, owner, or outcome to remove the marker. A document containing markers may be exported and is classified `evidence_blocked` when a critical omission remains; no completion claim may call it fully review-ready.

## 5. Numeric-claim grounding

Every number, percentage, currency amount, date range, count, ranking, or comparison in a factual claim must reference evidence whose excerpt supports the value and whose locator is inspectable. A calculation must additionally record its operands, operation, rounding rule, and source references. If grounding is missing, stale, contradictory, or insufficient, preserve `[확인 필요]` in the claim and paragraph rather than presenting the value as fact.

## 6. Correction allowlist and input boundaries

P0 corrections are limited to: title replacement; body paragraph replacement or append; selection of a predefined paragraph preset; replacement of existing table-cell text; and removal of a generated patch before apply. Each operation reports proposed, applied, partially applied, or rejected changes and supports undo of the last applied operation. No correction may create/delete/reorder sections, change table dimensions, move content freely, manipulate images, or edit raw XML.

Accepted inputs are guided answers, user-authored text, source documents, cited excerpts, approved template metadata, and structured provider responses matching the document-command contract. Source documents and provider output are untrusted data. Instructions found inside source material are evidence text only and cannot authorize tools, change policy, or override this specification.

## 7. Authority and conflicts

Formatting and wording authority is resolved in this order: institution template, current official rules, product paragraph preset, then the principles of the Blue House report-writing guide. A template conflict with current rules creates a visible warning containing the conflicting rule and affected field; it does not quarantine the template or block draft generation. Current rules govern the resulting warning and validation outcome.

## 8. HWPX Validation Profile v1

The canonical export is an editable HWPX package. Validation must confirm: required HWPX package parts exist; package relationships resolve; XML is well-formed and namespace-valid; document content maps losslessly from the semantic model for supported P0 structures; paragraph presets map to declared styles; existing table dimensions are unchanged; `[확인 필요]` markers and evidence references remain inspectable in the model; and repeated exports from the same document snapshot and operation ID produce byte-identical output without duplicate writes.

Validation severity is `error` for package, relationship, XML, lossless-mapping, table-dimension, or duplicate-write failures; `warning` for template/current-rule conflicts; and `info` for non-critical omissions. HWPX validation and export remain available without an AI provider. Optional HWP export is an adapter concern and its failure must never block, replace, or destroy the HWPX artifact.

## 9. Approval and change control

This artifact is approved only for the exact tuple `(spec_id, version, content_hash)`. Implementations must record that tuple at integration time. Any change to the common model, checklists, omission semantics, numeric grounding, correction allowlist, input boundaries, or HWPX Validation Profile requires a new content hash and renewed approval; editing this file without updating approval metadata is invalid.
