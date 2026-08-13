from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PACKAGE_COPY_PATHS: Final[tuple[str, str]] = (
    "package-copy",
    "package-copy-secondary",
)
MANIFEST_FILENAME: Final = "manifest.json"


class DuplicatePackageWriteError(Exception):
    """A package copy destination already exists.

    Mirrors the product's established duplicate-write refusal
    (``DuplicateWriteError`` on the HWP export path): assembly never
    overwrites previously published package material.
    """


@dataclass(frozen=True)
class PackageAssembly:
    root: Path
    copy_roots: tuple[Path, Path]
    manifest_paths: tuple[Path, Path]


def _publish_copy(
    package_source: Path,
    manifest_bytes: bytes,
    destination: Path,
) -> Path:
    """Publish one package copy through the established packaging path.

    Follows the same staged-then-atomic idiom as the product's export
    pipeline (see ``BundledRhwpAdapter.export``): the copy is fully staged
    in a sibling temporary directory, the manifest is written and fsynced
    while staged, and only a complete copy is published atomically. An
    existing destination is refused instead of being overwritten.
    """
    if destination.exists():
        raise DuplicatePackageWriteError(
            f"package copy destination already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".package-copy-", dir=destination.parent
    ) as staging:
        staged_root = Path(staging) / destination.name
        shutil.copytree(package_source, staged_root)
        staged_manifest = staged_root / MANIFEST_FILENAME
        with staged_manifest.open("wb") as manifest_file:
            manifest_file.write(manifest_bytes)
            manifest_file.flush()
            os.fsync(manifest_file.fileno())
        try:
            os.rename(staged_root, destination)
        except OSError as error:
            raise DuplicatePackageWriteError(
                f"package copy could not be published atomically: {destination}"
            ) from error
    return destination / MANIFEST_FILENAME


def assemble_package_copies(
    package_source: Path,
    manifest_bytes: bytes,
    assembly_root: Path,
) -> PackageAssembly:
    copy_roots = (
        assembly_root / PACKAGE_COPY_PATHS[0],
        assembly_root / PACKAGE_COPY_PATHS[1],
    )
    manifest_paths = tuple(
        _publish_copy(package_source, manifest_bytes, copy_root)
        for copy_root in copy_roots
    )
    return PackageAssembly(
        root=assembly_root,
        copy_roots=copy_roots,
        manifest_paths=(manifest_paths[0], manifest_paths[1]),
    )
