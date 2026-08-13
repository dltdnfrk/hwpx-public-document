from __future__ import annotations

from pathlib import Path

import pytest

from tests.external_stage2.loader import load

package_assembly = load("external_stage2.package_assembly")


def test_package_assembly_places_exactly_two_manifests_at_established_paths(
    tmp_path: Path,
) -> None:
    # Given: one package source and the vendored product 89-key manifest bytes.
    package_source = tmp_path / "candidate"
    package_source.mkdir()
    (package_source / "document.hwpx").write_bytes(b"candidate bytes")
    manifest_bytes = (
        Path(__file__).resolve().parents[1]
        / "tests/external_stage2/established-89-key-manifest.json"
    ).read_bytes()

    # When: the candidate is assembled using the preserved two-copy layout.
    assembly = package_assembly.assemble_package_copies(
        package_source=package_source,
        manifest_bytes=manifest_bytes,
        assembly_root=tmp_path / "assembled",
    )

    # Then: both manifests sit beside the copy roots (never inside them), so
    # the manifest is bound exactly once via manifest_jcs_sha256 while the
    # artifact tree binds the copy-root contents.
    assert tuple(path.relative_to(assembly.root).as_posix() for path in assembly.manifest_paths) == (
        "manifest.json",
        "manifest-secondary.json",
    )
    assert sorted(path.name for path in assembly.root.rglob("manifest*.json")) == [
        "manifest-secondary.json",
        "manifest.json",
    ]
    assert all(path.read_bytes() == manifest_bytes for path in assembly.manifest_paths)
    assert sorted(
        path.relative_to(assembly.root).as_posix()
        for copy_root in assembly.copy_roots
        for path in copy_root.rglob("*")
    ) == [
        "package-copy-secondary/document.hwpx",
        "package-copy/document.hwpx",
    ]


def test_package_assembly_refuses_to_overwrite_published_copies(
    tmp_path: Path,
) -> None:
    # Given: a package that has already been assembled and published once.
    package_source = tmp_path / "candidate"
    package_source.mkdir()
    (package_source / "document.hwpx").write_bytes(b"candidate bytes")
    manifest_bytes = (
        Path(__file__).resolve().parents[1]
        / "tests/external_stage2/established-89-key-manifest.json"
    ).read_bytes()
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


def test_package_assembly_invokes_product_ditto_packaging_and_duplicate_write_error() -> None:
    # Given: the brownfield macOS packaging script and the assembly module.
    root = Path(__file__).resolve().parents[1]
    assembly_source = (
        root / "scripts/external-stage2/external_stage2/package_assembly.py"
    ).read_text(encoding="utf-8")
    packaging_script = (root / "scripts/package-macos-app.sh").read_text(encoding="utf-8")

    # Then: assembly calls the product ditto argv and the product duplicate-write
    # type instead of a new shutil.copytree packaging path.
    assert "from public_document import DuplicateWriteError" in assembly_source
    assert "shutil.copytree" not in assembly_source
    assert package_assembly.PRODUCT_DITTO_ARGV == (
        "/usr/bin/ditto",
        "--norsrc",
        "--noextattr",
        "--noqtn",
        "--noacl",
    )
    assert " ".join(package_assembly.PRODUCT_DITTO_ARGV) in packaging_script
    assert package_assembly.DuplicatePackageWriteError is package_assembly.DuplicateWriteError
