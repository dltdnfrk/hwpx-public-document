from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PACKAGE_COPY_PATHS: Final[tuple[str, str]] = (
    "package-copy",
    "package-copy-secondary",
)
MANIFEST_FILENAME: Final = "manifest.json"


@dataclass(frozen=True)
class PackageAssembly:
    root: Path
    copy_roots: tuple[Path, Path]
    manifest_paths: tuple[Path, Path]


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
        copy_roots[0] / MANIFEST_FILENAME,
        copy_roots[1] / MANIFEST_FILENAME,
    )
    for copy_root, manifest_path in zip(copy_roots, manifest_paths):
        shutil.copytree(package_source, copy_root)
        manifest_path.write_bytes(manifest_bytes)
    return PackageAssembly(
        root=assembly_root,
        copy_roots=copy_roots,
        manifest_paths=manifest_paths,
    )
