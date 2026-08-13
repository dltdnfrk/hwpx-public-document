from __future__ import annotations

import json
from pathlib import Path

from tests.external_stage2.receipt_fixture import build_fixture


def test_manifest_generation_preserves_all_established_keys_and_values(
    tmp_path: Path,
) -> None:
    # Given: the complete established 89-key manifest contract.
    expected_manifest: dict[str, str | bool | int | dict[str, bool]] = {
        f"manifest_key_{index:02d}": f"value-{index}" for index in range(89)
    }
    expected_manifest.update(
        {
            "manifest_key_00": "PASS",
            "manifest_key_01": True,
            "manifest_key_02": 1000000,
            "manifest_key_03": {"independentlyProduced": True},
        }
    )

    # When: the Stage 2 package fixture generates its compatibility manifest.
    fixture = build_fixture(tmp_path)
    generated_manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))

    # Then: neither the manifest key names nor any values changed.
    assert len(generated_manifest) == 89
    assert generated_manifest == expected_manifest
