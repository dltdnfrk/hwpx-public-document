from __future__ import annotations

import json
from pathlib import Path

from tests.external_stage2.loader import load
from tests.external_stage2.receipt_fixture import (
    EXECUTION_ID,
    NOW,
    ReceiptFixture,
    build_fixture,
)

contract = load("external_stage2.contract")
copy_integrity = load("external_stage2.copy_integrity")
package_assembly = load("external_stage2.package_assembly")
package_verifier = load("external_stage2.package_verifier")
verifier = load("external_stage2.verifier")


def _assemble(fixture: ReceiptFixture, assembly_root: Path):
    """Assemble the candidate through the established two-copy packaging path."""
    return package_assembly.assemble_package_copies(
        package_source=fixture.artifact_root,
        manifest_bytes=fixture.manifest_path.read_bytes(),
        assembly_root=assembly_root,
    )


def _verify_assembled_package(fixture: ReceiptFixture, assembly, pin_db: Path):
    """Run the package evaluator's dual gate directly over assembled copies."""
    return package_verifier.verify_package(
        package_verifier.PackageVerificationInputs(
            verification=verifier.VerificationInputs(
                receipt_path=fixture.receipt_path,
                policy_path=fixture.policy_path,
                request_path=fixture.request_path,
                result_path=fixture.result_path,
                manifest_path=assembly.manifest_paths[0],
                artifact_root=assembly.copy_roots[0],
                execution_id=EXECUTION_ID,
                now=contract.parse_timestamp(NOW, "INTERNAL_VERIFIER_ERROR"),
            ),
            secondary_artifact_root=assembly.copy_roots[1],
            secondary_manifest_path=assembly.manifest_paths[1],
            pin_db_path=pin_db,
        )
    )


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


def test_final_acceptance_requires_both_gates_and_holds_when_both_pass(
    tmp_path: Path,
) -> None:
    # Given: an approved authenticated receipt and an untampered assembly.
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = build_fixture(fixture_root)
    assembly = _assemble(fixture, tmp_path / "assembled")

    # When: the copy-integrity gate and the semantic-approval gate both run
    # directly over the assembled two-copy package.
    integrity = copy_integrity.verify_copy_integrity(
        copy_integrity.CopyIntegrityInputs(
            assembly.copy_roots[0],
            assembly.copy_roots[1],
            assembly.manifest_paths[0],
            assembly.manifest_paths[1],
        )
    )
    decision = _verify_assembled_package(fixture, assembly, tmp_path / "pins.sqlite3")

    # Then: each independent gate passes and only their conjunction accepts.
    assert integrity.integrity_pass is True
    assert integrity.reason_codes == ()
    assert decision.integrity_pass is True
    assert decision.semantic_pass is True
    assert decision.accepted is True
    assert decision.reason_codes == ()
    assert decision.receipt_digest == fixture.receipt_digest


def test_copy_integrity_failure_blocks_acceptance_despite_semantic_approval(
    tmp_path: Path,
) -> None:
    # Given: an approved authenticated receipt, but byte-distinct manifest
    # copies whose canonical 89-key content stays bound to the receipt.
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = build_fixture(fixture_root)
    assembly = _assemble(fixture, tmp_path / "assembled")
    manifest = json.loads(assembly.manifest_paths[1].read_text(encoding="utf-8"))
    assembly.manifest_paths[1].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # When: the dual gate runs over the assembled package.
    decision = _verify_assembled_package(fixture, assembly, tmp_path / "pins.sqlite3")

    # Then: the independently successful semantic gate cannot override the
    # failed copy-integrity gate.
    assert decision.integrity_pass is False
    assert decision.semantic_pass is True
    assert decision.accepted is False
    assert decision.reason_codes == ("INTEGRITY_COPY_MISMATCH",)
    assert decision.receipt_digest == fixture.receipt_digest


def test_semantic_veto_blocks_acceptance_despite_intact_copy_integrity(
    tmp_path: Path,
) -> None:
    # Given: byte-identical copies but an authenticated external Stage 2 veto.
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = build_fixture(fixture_root, final_approved=False, score_ppm=1000000)
    assembly = _assemble(fixture, tmp_path / "assembled")

    # When: the dual gate runs over the assembled package.
    decision = _verify_assembled_package(fixture, assembly, tmp_path / "pins.sqlite3")

    # Then: the independently successful copy-integrity gate cannot override
    # the authenticated semantic veto.
    assert decision.integrity_pass is True
    assert decision.semantic_pass is False
    assert decision.accepted is False
    assert decision.reason_codes == ("FINAL_APPROVAL_FALSE",)
    assert decision.receipt_digest == fixture.receipt_digest
