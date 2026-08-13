from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Final, List, Set

from .canonical_json import JsonValue, sha256_jcs
from .contract import ContractError


MAX_FILES: Final = 4096
MAX_PATH_BYTES: Final = 512
MAX_TOTAL_BYTES: Final = 2147483648
EXCLUDED_FILES: Final = frozenset(
    {
        # The established two-copy layout stores each copy's 89-key manifest
        # inside the copy root. The manifest is bound separately and
        # content-addressed through manifest_jcs_sha256 (and byte-compared by
        # copy integrity), so it is excluded here to avoid double-binding the
        # same material into artifact_tree_sha256.
        "manifest.json",
        "stage2-receipt.json",
        "stage2-request.json",
        "stage2-result.json",
        "external-stage2-pins.sqlite3",
        "external-stage2-pins.sqlite3-journal",
        "external-stage2-pins.sqlite3-shm",
        "external-stage2-pins.sqlite3-wal",
    }
)
REPORT_DIRECTORY: Final = "external-stage2-reports"


def artifact_tree_digest(root: Path) -> str:
    entries: List[JsonValue] = []
    normalized_paths: Set[str] = set()
    folded_paths: Set[str] = set()
    total_bytes = 0
    if not root.is_dir():
        raise ContractError("ARTIFACT_BINDING_MISMATCH")
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if relative in EXCLUDED_FILES or relative.startswith(REPORT_DIRECTORY + "/"):
            continue
        if path.is_symlink():
            raise ContractError("ARTIFACT_BINDING_MISMATCH")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ContractError("ARTIFACT_BINDING_MISMATCH")
        normalized = unicodedata.normalize("NFC", relative)
        components = normalized.split("/")
        path_bytes = normalized.encode("utf-8")
        if (
            relative != normalized
            or any(part in {"", ".", ".."} for part in components)
            or "\\" in normalized
            or "\0" in normalized
            or len(path_bytes) > MAX_PATH_BYTES
        ):
            raise ContractError("ARTIFACT_LIMIT_EXCEEDED")
        folded = normalized.casefold()
        if normalized in normalized_paths or folded in folded_paths:
            raise ContractError("ARTIFACT_LIMIT_EXCEEDED")
        normalized_paths.add(normalized)
        folded_paths.add(folded)
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ContractError("ARTIFACT_BINDING_MISMATCH") from error
        size = len(raw)
        total_bytes += size
        if len(entries) >= MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
            raise ContractError("ARTIFACT_LIMIT_EXCEEDED")
        entries.append(
            {
                "path": normalized,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": size,
            }
        )
    entries.sort(
        key=lambda entry: str(entry["path"]).encode("utf-8")
        if isinstance(entry, dict)
        else b""
    )
    return sha256_jcs(entries)
