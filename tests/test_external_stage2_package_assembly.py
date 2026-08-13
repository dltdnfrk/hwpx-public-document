from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.external_stage2.loader import load

package_assembly = load("external_stage2.package_assembly")


def test_package_assembly_places_exactly_two_manifests_at_established_paths(
    tmp_path: Path,
) -> None:
    # Given: one package source and its established 89-key manifest bytes.
    package_source = tmp_path / "candidate"
    package_source.mkdir()
    (package_source / "document.hwpx").write_bytes(b"candidate bytes")
    manifest = {
        f"manifest_key_{index:02d}": f"value-{index}" for index in range(89)
    }
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    # When: the candidate is assembled using the preserved two-copy layout.
    assembly = package_assembly.assemble_package_copies(
        package_source=package_source,
        manifest_bytes=manifest_bytes,
        assembly_root=tmp_path / "assembled",
    )

    # Then: the only manifests are at the two established package paths.
    assert tuple(path.relative_to(assembly.root).as_posix() for path in assembly.manifest_paths) == (
        "package-copy/manifest.json",
        "package-copy-secondary/manifest.json",
    )
    assert sorted(path.relative_to(assembly.root).as_posix() for path in assembly.root.rglob("manifest.json")) == [
        "package-copy-secondary/manifest.json",
        "package-copy/manifest.json",
    ]
    assert all(path.read_bytes() == manifest_bytes for path in assembly.manifest_paths)


def test_package_assembly_refuses_to_overwrite_published_copies(
    tmp_path: Path,
) -> None:
    # Given: a package that has already been assembled and published once.
    package_source = tmp_path / "candidate"
    package_source.mkdir()
    (package_source / "document.hwpx").write_bytes(b"candidate bytes")
    manifest_bytes = b'{"manifest_key_00":"value-0"}'
    assembly_root = tmp_path / "assembled"
    package_assembly.assemble_package_copies(
        package_source=package_source,
        manifest_bytes=manifest_bytes,
        assembly_root=assembly_root,
    )

    # When / Then: republishing over existing copies is refused, mirroring the
    # product export path's duplicate-write refusal.
    with pytest.raises(package_assembly.DuplicatePackageWriteError):
        package_assembly.assemble_package_copies(
            package_source=package_source,
            manifest_bytes=manifest_bytes,
            assembly_root=assembly_root,
        )
