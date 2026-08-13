from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .copy_integrity import CopyIntegrityInputs, verify_copy_integrity
from .pinned_verifier import PinnedVerificationInputs, verify_with_pinning
from .verifier import VerificationInputs


@dataclass(frozen=True)
class PackageVerificationInputs:
    verification: VerificationInputs
    secondary_artifact_root: Path
    secondary_manifest_path: Path
    pin_db_path: Path


@dataclass(frozen=True)
class PackageVerificationDecision:
    accepted: bool
    integrity_pass: bool
    semantic_pass: bool
    receipt_digest: str | None
    reason_codes: tuple[str, ...]


def verify_package(inputs: PackageVerificationInputs) -> PackageVerificationDecision:
    primary = inputs.verification
    integrity = verify_copy_integrity(
        CopyIntegrityInputs(
            primary.artifact_root,
            inputs.secondary_artifact_root,
            primary.manifest_path,
            inputs.secondary_manifest_path,
        )
    )
    semantic_decisions = (
        verify_with_pinning(PinnedVerificationInputs(primary, inputs.pin_db_path)),
        verify_with_pinning(
            PinnedVerificationInputs(
                replace(
                    primary,
                    artifact_root=inputs.secondary_artifact_root,
                    manifest_path=inputs.secondary_manifest_path,
                ),
                inputs.pin_db_path,
            )
        ),
    )
    semantic_pass = all(decision.semantic_pass for decision in semantic_decisions)
    receipt_digest = next(
        (
            decision.receipt_digest
            for decision in semantic_decisions
            if decision.receipt_digest is not None
        ),
        None,
    )
    reason_codes = tuple(
        sorted(
            {
                *integrity.reason_codes,
                *(
                    reason
                    for decision in semantic_decisions
                    for reason in decision.reason_codes
                ),
            }
        )
    )
    accepted = integrity.integrity_pass and semantic_pass
    return PackageVerificationDecision(
        accepted,
        integrity.integrity_pass,
        semantic_pass,
        receipt_digest,
        reason_codes,
    )
