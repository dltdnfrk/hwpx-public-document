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
# Manifests are published beside the copy roots, never inside them: the
# manifest is bound exactly once through manifest_jcs_sha256 (and
# byte-compared by copy integrity), while artifact_tree_sha256 binds the copy
# root contents under the closed v1 exclusion list.
MANIFEST_PATHS: Final[tuple[str, str]] = (
    "manifest.json",
    "manifest-secondary.json",
)


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


def _refuse_existing(destination: Path) -> None:
    if destination.exists():
        raise DuplicatePackageWriteError(
            f"package destination already exists: {destination}"
        )


def _publish_copy(package_source: Path, destination: Path) -> None:
    """Publish one package copy through the established packaging path.

    Follows the same staged-then-atomic idiom as the product's export
    pipeline (see ``BundledRhwpAdapter.export``): the copy is fully staged in
    a sibling temporary directory and only a complete copy is published
    atomically. An existing destination is refused instead of overwritten.
    """
    _refuse_existing(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".package-copy-", dir=destination.parent
    ) as staging:
        staged_root = Path(staging) / destination.name
        shutil.copytree(package_source, staged_root)
        try:
            os.rename(staged_root, destination)
        except OSError as error:
            raise DuplicatePackageWriteError(
                f"package copy could not be published atomically: {destination}"
            ) from error


def _publish_manifest(manifest_bytes: bytes, destination: Path) -> None:
    """Publish one manifest sidecar through the established packaging path."""
    _refuse_existing(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".package-manifest-", dir=destination.parent
    ) as staging:
        staged_manifest = Path(staging) / destination.name
        with staged_manifest.open("wb") as manifest_file:
            manifest_file.write(manifest_bytes)
            manifest_file.flush()
            os.fsync(manifest_file.fileno())
        try:
            os.link(staged_manifest, destination)
        except FileExistsError as error:
            raise DuplicatePackageWriteError(
                f"package destination already exists: {destination}"
            ) from error
        except OSError as error:
            raise DuplicatePackageWriteError(
                f"package manifest could not be published atomically: {destination}"
            ) from error


def assemble_package_copies(
    package_source: Path,
    manifest_bytes: bytes,
    assembly_root: Path,
) -> PackageAssembly:
    copy_roots = (
        assembly_root / PACKAGE_COPY_PATHS[0],
        assembly_root / PACKAGE_COPY_PATHS[1],
    )
    manifest_paths = (
        assembly_root / MANIFEST_PATHS[0],
        assembly_root / MANIFEST_PATHS[1],
    )
    for copy_root, manifest_path in zip(copy_roots, manifest_paths):
        _publish_copy(package_source, copy_root)
        _publish_manifest(manifest_bytes, manifest_path)
    return PackageAssembly(
        root=assembly_root,
        copy_roots=copy_roots,
        manifest_paths=manifest_paths,
    )
