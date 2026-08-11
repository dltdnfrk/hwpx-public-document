from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests.seed_criterion_contract_support import PATH_DRIVER, ROOT, run_comparison, run_contract, run_node
from tests.seed_criterion_fixture_ac01_ac05 import write_ac01_fixture
from tests.seed_criterion_fixture_support import write_ac04_fixture, write_json


def test_source_map_dry_contract_reports_all_boundary_mismatches(tmp_path: Path) -> None:
    # Given: a source map is incomplete and one supplied path escapes the selected root.
    source_map = {
        "schemaVersion": 1,
        "criteria": {"AC-01": {"foundationRuntimeReceipt": "../outside.json"}},
    }

    # When: the source map is validated without materializing artifacts.
    issues = json.loads(run_node({"action": "source-map", "map": source_map, "root": str(tmp_path)}))

    # Then: the dry contract reports both the unsafe field and every absent criterion.
    assert any(issue["field"] == "AC-01.foundationRuntimeReceipt" for issue in issues)
    assert {issue["field"] for issue in issues} >= {f"AC-{number:02d}" for number in range(2, 11)}


def test_ac04_false_receipt_and_identity_drift_fail(tmp_path: Path) -> None:
    # Given: complete AC-04 contracts bound to one independent runtime receipt.
    write_ac04_fixture(tmp_path)
    passed = run_contract({"action": "evaluate", "criterion": "AC-04", "root": str(tmp_path)})
    assert passed["verdict"] == "pass"

    # When: a criterion-specific assertion is false.
    lifecycle = json.loads((tmp_path / "artifacts/ai/proposal-lifecycle-evidence.json").read_text())
    lifecycle["actualScopedTargetIDsEnforced"] = False
    write_json(tmp_path, "artifacts/ai/proposal-lifecycle-evidence.json", lifecycle)
    false_receipt = run_contract({"action": "evaluate", "criterion": "AC-04", "root": str(tmp_path)})

    # Then: evaluator semantics override any authored PASS projection.
    assert false_receipt["verdict"] == "fail"
    lifecycle["actualScopedTargetIDsEnforced"] = True
    write_json(tmp_path, "artifacts/ai/proposal-lifecycle-evidence.json", lifecycle)
    write_json(tmp_path, "runtime/ai.json", {"receipt": "mutated-after-materialization"})
    drift = run_contract({"action": "evaluate", "criterion": "AC-04", "root": str(tmp_path)})
    assert drift["verdict"] == "fail"
    assert any("identity" in check["id"] for check in drift["checks"] if not check["passed"])


def test_acceptance_projection_and_ac10_are_recomputed() -> None:
    # Given: a stored acceptance says PASS while canonical evaluation says FAIL.
    evaluation = {"criterion": "AC-04", "verdict": "fail", "summary": "failed", "blockers": [], "checks": []}
    mismatch = run_comparison(
        {"action": "compare", "receipt": {"criterion": "AC-04", "verdict": "pass"}, "evaluation": evaluation}
    )
    assert mismatch

    # When: the archive passes but one predecessor is externally blocked.
    preceding = [
        {"criterion": f"AC-{number:02d}", "verdict": "blocked" if number == 8 else "pass"}
        for number in range(1, 10)
    ]
    release_checks = [{"id": "archive.integrity", "passed": True, "detail": "verified"}]
    blocked = run_contract({"action": "derive-ac10", "preceding": preceding, "releaseChecks": release_checks})
    assert blocked["verdict"] == "blocked"

    # Then: archive failure overrides predecessor BLOCKED.
    release_checks[0]["passed"] = False
    failed = run_contract({"action": "derive-ac10", "preceding": preceding, "releaseChecks": release_checks})
    assert failed["verdict"] == "fail"


def test_evidence_path_cannot_escape_project_root(tmp_path: Path) -> None:
    # Given: otherwise valid AC-04 evidence points outside the selected project root.
    write_ac04_fixture(tmp_path)
    provider_path = tmp_path / "artifacts/privacy/provider-boundary-evidence.json"
    provider = json.loads(provider_path.read_text())
    provider["sourceEvidence"] = [{"path": "../outside.json", "sha256": "sha256:" + "0" * 64}]
    write_json(tmp_path, "artifacts/privacy/provider-boundary-evidence.json", provider)

    # When: the criterion is evaluated.
    result = run_contract({"action": "evaluate", "criterion": "AC-04", "root": str(tmp_path)})

    # Then: traversal is a local FAIL, never an external blocker.
    assert result["verdict"] == "fail"
    assert any("identity" in check["id"] for check in result["checks"] if not check["passed"])


def test_seed_artifact_path_helper_rejects_traversal_absolute_and_symlink(tmp_path: Path) -> None:
    # Given: one in-root file and a symlink targeting a sibling directory.
    inside = tmp_path / "inside.json"
    inside.write_text("{}", encoding="utf-8")
    outside = tmp_path.parent / "outside-seed-evidence.json"
    outside.write_text("{}", encoding="utf-8")
    (tmp_path / "outside-link.json").symlink_to(outside)

    # When: the path helper resolves the normal project-relative file.
    accepted = subprocess.run(
        ["node", "--input-type=module", "-e", PATH_DRIVER, str(tmp_path), "inside.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    # Then: only the in-root file succeeds; every escape form is rejected.
    assert accepted.returncode == 0
    for unsafe in ["../outside-seed-evidence.json", str(outside), "outside-link.json"]:
        rejected = subprocess.run(
            ["node", "--input-type=module", "-e", PATH_DRIVER, str(tmp_path), unsafe],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert rejected.returncode != 0


def test_packaged_genoffice_runtime_recomputes_output_identity(tmp_path: Path) -> None:
    # Given: a package-shaped Resources tree contains the AC-01 runtime and copied input lock.
    write_ac01_fixture(tmp_path)
    manifest = json.loads((tmp_path / "artifacts/provenance/genoffice-runtime-manifest.json").read_text())
    input_lock = json.loads((tmp_path / "GenOfficeFork/runtime-input-lock.json").read_text())
    write_json(tmp_path, "Resources/Provenance/genoffice-runtime-input-lock.json", input_lock)
    passed = json.loads(run_node({"action": "packaged-genoffice", "root": str(tmp_path), "manifest": manifest, "inputLock": input_lock}))
    assert all(check["passed"] for check in passed)

    # When: the packaged browser output changes after the manifest was fixed.
    (tmp_path / "Resources/GenOffice/public-document-genoffice.js").write_text("tampered", encoding="utf-8")
    failed = json.loads(run_node({"action": "packaged-genoffice", "root": str(tmp_path), "manifest": manifest, "inputLock": input_lock}))

    # Then: AC-10's package contract rejects the current bytes.
    assert any(check["id"] == "release.genoffice-outputs" and not check["passed"] for check in failed)


def test_ac01_accepts_the_canonical_apache_license_name(tmp_path: Path) -> None:
    # Given: the notices name the same approved license in its canonical human-readable form.
    write_ac01_fixture(tmp_path)
    notices = tmp_path / "artifacts/provenance/THIRD_PARTY_NOTICES.md"
    notices.write_text("GenOffice Apache License 2.0\nrhwp MIT\n", encoding="utf-8")

    # When: AC-01 is recomputed from the raw notices.
    result = run_contract({"action": "evaluate", "criterion": "AC-01", "root": str(tmp_path)})

    # Then: spelling the exact Apache 2.0 license name does not create a false failure.
    assert result["verdict"] == "pass"


def test_ac10_projection_is_deterministic_and_ignores_archive_internal_paths() -> None:
    # Given: the final archive receipt contains package-internal Contents/... identities.
    first = run_contract({"action": "evaluate", "criterion": "AC-10", "root": str(ROOT)})

    # When: the same immutable archive is independently extracted and evaluated again.
    second = run_contract({"action": "evaluate", "criterion": "AC-10", "root": str(ROOT)})

    # Then: temporary extraction paths never enter the projection or masquerade as project evidence.
    assert first == second
    identity = next(check for check in first["checks"] if check["id"] == "evidence.identity")
    assert identity["passed"] is True
