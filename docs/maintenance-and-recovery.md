# Maintenance and recovery

## Canonical verification

Run from the repository root:

```sh
scripts/verify-production.sh .omo/evidence/manual/verify
```

The complete gate requires an unlocked, active physical macOS console and a
quiet execution window. AC-09 observes a real AppKit window, progress updates,
and cancellation on the main thread; a locked/inactive console is a blocked
environment, not a product failure. Close unrelated CPU-intensive jobs before
running the canonical command.

The command refuses an existing evidence directory. A pass requires:

- generated layout-profile and provenance checks;
- JavaScript syntax checks;
- the pinned GenOffice port verifier;
- `swift build --product PublicDocumentApp`;
- the complete pytest suite;
- layout-profile parity across native, DOCX, HWPX, preview, and macros;
- the four-format capability matrix;
- the fireblight DOCX package inspection.

Inspect `summary.json` and `transcript.txt` in the evidence directory. Tests
alone are not a release decision; use the browser and macOS QA commands in the
active release checklist as well.

## Provenance updates

After changing canonical layout JSON or a declared local runtime artifact:

```sh
node scripts/update-local-provenance.mjs
node scripts/update-local-provenance.mjs --check
node scripts/verify-genoffice-port.mjs --manifest provenance/genoffice-docs-port.json
```

The updater regenerates the Studio layout-profile object, refreshes declared
local artifact hashes, and updates the GenOffice port-manifest hash in
`upstream-lock.json`. It does not update the upstream commit, SBOM, runtime
bundle, or license notices.

Never change `format-capabilities-1.0.0.json` merely to make an export pass.
Relax a `semantic-loss` row only after the target artifact has package-level
and representative-client round-trip evidence.

## Adversarial and deterministic checks

```sh
scripts/verify-production.sh --tamper-provenance-copy .omo/evidence/manual/tamper
scripts/verify-production.sh --repeat 2 .omo/evidence/manual/repeat
```

The tamper command works on an isolated copy and must leave repository status
byte-identical. The repeat command runs the full gate twice and compares
normalized manifest and package-content hashes.

## Failure recovery

1. Read the first failing command in `transcript.txt`.
2. Re-run only that command against a new evidence directory.
3. For provenance drift, run the updater once and inspect the diff before
   running `--check`.
4. For an export failure, retain the receipt and package inspection; do not
   disable validation or weaken the capability matrix.
5. For browser failures, confirm the action log says both the Chrome context
   and local HTTP server were closed.
6. For packaging failures, remove only the newly created workspace-contained
   destination and rerun. Do not modify `~/Applications/PublicDocument.app`.

Do not use destructive Git recovery. This workspace may contain unrelated
user changes; preserve them and record a no-commit reason when commit
authorization has not been given.
