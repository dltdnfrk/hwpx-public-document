from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .artifact_tree import artifact_tree_digest
from .contract import ContractError


@dataclass(frozen=True)
class CopyIntegrityDecision:
    integrity_pass: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CopyIntegrityInputs:
    primary_root: Path
    secondary_root: Path
    primary_manifest: Path
    secondary_manifest: Path


def verify_copy_integrity(inputs: CopyIntegrityInputs) -> CopyIntegrityDecision:
    if not inputs.primary_root.is_dir() or not inputs.secondary_root.is_dir():
        return CopyIntegrityDecision(False, ("INTEGRITY_COPY_MISSING",))
    if not inputs.primary_manifest.is_file() or not inputs.secondary_manifest.is_file():
        return CopyIntegrityDecision(False, ("INTEGRITY_COPY_MISSING",))
    try:
        roots_match = artifact_tree_digest(inputs.primary_root) == artifact_tree_digest(
            inputs.secondary_root
        )
        manifests_match = (
            inputs.primary_manifest.read_bytes()
            == inputs.secondary_manifest.read_bytes()
        )
    except ContractError as error:
        return CopyIntegrityDecision(False, (error.reason_code,))
    except (OSError, UnicodeError):
        return CopyIntegrityDecision(False, ("INTEGRITY_COPY_MISMATCH",))
    if not roots_match or not manifests_match:
        return CopyIntegrityDecision(False, ("INTEGRITY_COPY_MISMATCH",))
    return CopyIntegrityDecision(True, ())
