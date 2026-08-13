from __future__ import annotations

import importlib
import json
from pathlib import Path

package_assembly = importlib.import_module("external_stage2.package_assembly")


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
