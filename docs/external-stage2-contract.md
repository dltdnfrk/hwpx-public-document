# External Stage 2 receipt contract

The package semantic gate trusts only an external `stage2-semantic-v1` receipt.
Manifest fields such as `PASS`, `approval`, `score`, or
`independentlyProduced` remain compatibility data and have no authorization
effect.

## Validation boundary

`scripts/external-stage2/verify_receipt.py` consumes six explicit inputs:

- the closed receipt envelope;
- an orchestrator-owned immutable trust-policy snapshot;
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
cover the copy-root `manifest.json` (bound separately through
`manifest_jcs_sha256` and byte-compared by copy integrity, so it is never
double-bound into the tree), the three Stage 2 sidecars, the pin SQLite
database and journal files, and the single `external-stage2-reports` report
directory.

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

`scripts/external-stage2/verify_package.py` is the package-facing dual-gate
entrypoint. It requires explicit primary and secondary artifact roots and
manifest paths, verifies that both copies exist, compares their artifact-tree
hashes and exact manifest bytes, and runs the authenticated receipt verifier
against each copy. Matching intact copies with valid external approval return
`ACCEPTED` with exit 0. A missing copy returns `INTEGRITY_COPY_MISSING`; any
copy byte or manifest difference returns `INTEGRITY_COPY_MISMATCH`. Every
non-accepted combined outcome returns exit 2 with sorted unique v1 reason codes.
