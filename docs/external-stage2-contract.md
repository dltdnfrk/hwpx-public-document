# External Stage 2 receipt contract

The package semantic gate trusts only an external `stage2-semantic-v1` receipt.
Manifest fields such as `PASS`, `approval`, `score`, or
`independentlyProduced` remain compatibility data and have no authorization
effect.

## Validation boundary

`scripts/external-stage2/verify_receipt.py` consumes six explicit inputs:

- the closed receipt envelope;
- an orchestrator-owned immutable trust-policy snapshot;
- the orchestrator's out-of-band trust anchor (`--trust-policy-sha256`), the
  lowercase-hex SHA-256 of the exact snapshot bytes — the supplied policy must
  hash to this pin before any of its key material is trusted, so a candidate
  cannot substitute a policy carrying a self-generated signing key;
- the external Stage 2 request and result sidecars;
- the strictly parsed 89-key manifest;
- the evaluated package-copy root; and
- the orchestrator execution identifier.

The validator applies the v1 byte limits, strict UTF-8 and duplicate-key JSON
parsing, closed schemas, canonical unpadded base64url, Ed25519 verification,
payload JCS byte identity, immutable signer authorization, evaluator allowlist,
execution and freshness checks, and independently recomputed artifact,
manifest, request, and result JCS digests. The signed message is
`ouroboros-stage2-receipt-v1`, NUL, `key_id`, NUL, then the exact decoded
payload bytes.

Artifact inventory entries contain only `path`, `size_bytes`, and the SHA-256
of exact stored bytes. Paths are relative POSIX NFC strings, sorted by unsigned
UTF-8 bytes, and fail closed on symlinks, non-regular files, normalization or
case-fold collisions, and v1 count/path/byte limits. The closed v1 exclusions
cover the three Stage 2 sidecars, the pin SQLite database and journal files,
and the single `external-stage2-reports` report directory. Package manifests
live beside the copy roots (never inside them), so the manifest is bound
exactly once, through `manifest_jcs_sha256`, and byte-compared by copy
integrity.

## Decision

Semantic acceptance requires all provenance and binding stages to pass,
`final_approved` to be exactly `true`, native integer `score_ppm` to be at
least `800000`, and the bound result reason-code array to be empty. Any other
outcome is `NOT_ACCEPTED`, uses exit status 2, and emits only sorted closed v1
reason codes. A qualitative Stage 2 veto is authoritative at any score; an
approval below threshold reports both `FIELD_INCONSISTENCY` and
`SCORE_BELOW_THRESHOLD`.

This semantic result does not replace the existing two-copy gate. Final package
acceptance remains `integrity_pass AND semantic_pass`, with each package copy
independently recomputing the receipt bindings. Trust snapshots and future pin
storage are orchestrator-owned and must remain outside both package copies and
the repository.

The 89-key manifest is the brownfield format-capability matrix, not a locally
invented key list. The exact product bytes are vendored at
`tests/external_stage2/established-89-key-manifest.json` with provenance in
`tests/external_stage2/established-89-key-manifest.provenance.json`.

- Product source: `Resources/Capabilities/format-capabilities-1.0.0.json`
- Materialized second copy: `artifacts/formats/format-capability-matrix.json`,
  produced by `scripts/materialize-seed-artifacts.mjs` calling `copy()` from
  `scripts/seed-artifacts-lib.mjs`
- SHA-256: `c8cb49c859e902ce6434b167f2b72c757a379a16a6315ab38f8ad6c7caa01e6a`
- Definition count: `1 + len(classifications) + sum(len(row) for row in matrix) = 89`

`MANIFEST_KEYS_V1` is derived from those vendored bytes. Compatibility fields
`PASS`, `approval`, `score`, and `independentlyProduced` may remain as extra
untrusted data; they never authorize a package.

Two-copy assembly publishes candidate trees by invoking the product `ditto`
argv from `scripts/package-macos-app.sh` (`/usr/bin/ditto --norsrc --noextattr
--noqtn --noacl`) and raises `public_document.DuplicateWriteError` instead of
a new `shutil.copytree` packaging path. Manifest sidecars stay beside the copy
roots.

`scripts/external-stage2/verify_package.py` is the package-facing dual-gate
entrypoint. It requires explicit primary and secondary artifact roots and
manifest paths, verifies that both copies exist, compares their artifact-tree
hashes and exact manifest bytes, and runs the authenticated receipt verifier
against each copy. Matching intact copies with valid external approval return
`ACCEPTED` with exit 0. A missing copy returns `INTEGRITY_COPY_MISSING`; any
copy byte or manifest difference returns `INTEGRITY_COPY_MISMATCH`. Every
non-accepted combined outcome returns exit 2 with sorted unique v1 reason codes.
