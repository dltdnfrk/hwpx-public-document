from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from public_document import DuplicateWriteError

# Tests and callers keep the assembly-facing name; the exception is the
# product export type, not a newly invented duplicate-write class.
DuplicatePackageWriteError = DuplicateWriteError

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

# Established tree-copy packaging command from scripts/package-macos-app.sh
# (and the same argv in scripts/package-release-archive.sh). Assembly invokes
# this product command; it does not reimplement copytree.
PRODUCT_DITTO_ARGV: Final[tuple[str, ...]] = (
    "/usr/bin/ditto",
    "--norsrc",
    "--noextattr",
    "--noqtn",
    "--noacl",
)
PRODUCT_PACKAGING_SCRIPT: Final[str] = "scripts/package-macos-app.sh"
PRODUCT_PACKAGING_SCRIPT_SHA256: Final[str] = (
    "f48cddcd1504a55d8b5f6cf5e095948ae2c8c51cc8507713f27968d26680303d"
)


@dataclass(frozen=True)
class PackageAssembly:
    root: Path
    copy_roots: tuple[Path, Path]
    manifest_paths: tuple[Path, Path]


def _require_product_packaging_script() -> None:
    script = _REPO_ROOT / PRODUCT_PACKAGING_SCRIPT
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    if digest != PRODUCT_PACKAGING_SCRIPT_SHA256:
        raise RuntimeError(
            f"product packaging script sha256 mismatch: {digest}"
        )
    if " ".join(PRODUCT_DITTO_ARGV) not in script.read_text(encoding="utf-8"):
        raise RuntimeError(
            "product packaging script no longer contains the established ditto copy"
        )


def _ditto_publish(source: Path, destination: Path) -> None:
    """Publish one path by calling the product ditto packaging command."""
    if destination.exists():
        raise DuplicateWriteError(f"package destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["COPYFILE_DISABLE"] = "1"
    completed = subprocess.run(
        [*PRODUCT_DITTO_ARGV, str(source), str(destination)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        if destination.exists():
            raise DuplicateWriteError(
                f"package destination already exists: {destination}"
            )
        raise OSError(completed.stderr.strip() or completed.stdout.strip() or "ditto failed")


def _publish_manifest(manifest_bytes: bytes, destination: Path) -> None:
    """Publish one manifest sidecar through the product ditto packaging path."""
    if destination.exists():
        raise DuplicateWriteError(f"package destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".package-manifest-", dir=destination.parent
    ) as staging:
        staged_manifest = Path(staging) / destination.name
        staged_manifest.write_bytes(manifest_bytes)
        _ditto_publish(staged_manifest, destination)


def assemble_package_copies(
    package_source: Path,
    manifest_bytes: bytes,
    assembly_root: Path,
) -> PackageAssembly:
    _require_product_packaging_script()
    copy_roots = (
        assembly_root / PACKAGE_COPY_PATHS[0],
        assembly_root / PACKAGE_COPY_PATHS[1],
    )
    manifest_paths = (
        assembly_root / MANIFEST_PATHS[0],
        assembly_root / MANIFEST_PATHS[1],
    )
    for copy_root, manifest_path in zip(copy_roots, manifest_paths):
        _ditto_publish(package_source, copy_root)
        _publish_manifest(manifest_bytes, manifest_path)
    return PackageAssembly(
        root=assembly_root,
        copy_roots=copy_roots,
        manifest_paths=manifest_paths,
    )
