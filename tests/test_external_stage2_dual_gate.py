from __future__ import annotations

import hashlib
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
                trust_policy_sha256=fixture.policy_sha256_pin,
            ),
            secondary_artifact_root=assembly.copy_roots[1],
            secondary_manifest_path=assembly.manifest_paths[1],
            pin_db_path=pin_db,
        )
    )


def test_established_89_key_manifest_is_the_product_format_capability_artifact() -> None:
    # Given: the vendored product artifact and its independent provenance record.
    root = Path(__file__).resolve().parents[1]
    vendored = root / "tests/external_stage2/established-89-key-manifest.json"
    provenance = json.loads(
        (root / "tests/external_stage2/established-89-key-manifest.provenance.json").read_text(
            encoding="utf-8"
        )
    )
    product_source = root / "Resources/Capabilities/format-capabilities-1.0.0.json"
    materialized = root / "artifacts/formats/format-capability-matrix.json"
    schemas = load("external_stage2.schemas")

    # When: the independent product bytes and derived definition-path set are hashed.
    vendored_bytes = vendored.read_bytes()
    product_bytes = product_source.read_bytes()
    materialized_bytes = materialized.read_bytes()
    vendored_manifest = json.loads(vendored_bytes.decode("utf-8"))
    derived_keys = schemas.definition_keys(vendored_manifest)

    # Then: the schema is derived from the product artifact, the two established
    # copies remain byte-identical, and the definition count is exactly 89.
    assert hashlib.sha256(vendored_bytes).hexdigest() == provenance["source_sha256"]
    assert hashlib.sha256(product_bytes).hexdigest() == provenance["source_sha256"]
    assert hashlib.sha256(materialized_bytes).hexdigest() == provenance["source_sha256"]
    assert vendored_bytes == product_bytes == materialized_bytes
    assert len(derived_keys) == 89
    assert schemas.MANIFEST_KEYS_V1 == derived_keys
    assert schemas.ESTABLISHED_MANIFEST_SHA256 == provenance["source_sha256"]


def test_materializer_still_emits_the_established_two_manifest_copies() -> None:
    # Given: the existing brownfield materializer and the product 89-key source.
    root = Path(__file__).resolve().parents[1]
    materializer = (root / "scripts/materialize-seed-artifacts.mjs").read_text(encoding="utf-8")
    source = "Resources/Capabilities/format-capabilities-1.0.0.json"
    target = "artifacts/formats/format-capability-matrix.json"

    # When: its copy() declaration for the format-capability matrix is read.
    assert 'copy("{source}", "{target}");'.format(source=source, target=target) in materializer

    # Then: both established copies still exist as the product two-copy packaging.
    assert (root / source).read_bytes() == (root / target).read_bytes()


def test_manifest_generation_preserves_all_established_keys_and_values(
    tmp_path: Path,
) -> None:
    # Given: the vendored product 89-key format-capability matrix — an
    # independent brownfield artifact, not a locally invented key list.
    root = Path(__file__).resolve().parents[1]
    vendored = json.loads(
        (root / "tests/external_stage2/established-89-key-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    schemas = load("external_stage2.schemas")
    assert len(schemas.MANIFEST_KEYS_V1) == 89
    assert schemas.MANIFEST_KEYS_V1 == schemas.definition_keys(vendored)

    # When: the Stage 2 package fixture generates its compatibility manifest.
    fixture = build_fixture(tmp_path)
    generated_manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))

    # Then: the product 89-definition core is preserved, and candidate-authored
    # semantic values survive only as untrusted compatibility extras.
    core = {field: generated_manifest[field] for field in schemas.CORE_MANIFEST_FIELDS_V1}
    assert core == vendored
    assert generated_manifest["PASS"] == "PASS"
    assert generated_manifest["approval"] is True
    assert generated_manifest["score"] == 1000000
    assert generated_manifest["independentlyProduced"] == {"independentlyProduced": True}


def test_package_assembly_calls_product_ditto_instead_of_a_new_copytree_path() -> None:
    # Given: the existing macOS packaging script that publishes trees with ditto.
    root = Path(__file__).resolve().parents[1]
    assembly_source = (
        root / "scripts/external-stage2/external_stage2/package_assembly.py"
    ).read_text(encoding="utf-8")
    packaging_script = (root / "scripts/package-macos-app.sh").read_bytes()

    # Then: two-copy assembly invokes that product command and DuplicateWriteError.
    assert "from public_document import DuplicateWriteError" in assembly_source
    assert "shutil.copytree" not in assembly_source
    assert hashlib.sha256(packaging_script).hexdigest() == package_assembly.PRODUCT_PACKAGING_SCRIPT_SHA256
    assert " ".join(package_assembly.PRODUCT_DITTO_ARGV) in packaging_script.decode("utf-8")


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
