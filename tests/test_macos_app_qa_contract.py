from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "scripts" / "qa" / "macos-app-qa.py"


def test_macos_app_qa_declares_happy_and_invalid_scenarios() -> None:
    result = subprocess.run(
        ["python3", str(QA), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--build" in result.stdout
    assert "{happy,invalid-project}" in result.stdout
    assert "--evidence-dir" in result.stdout


def test_macos_app_qa_refuses_existing_evidence_directory(tmp_path: Path) -> None:
    evidence = tmp_path / "existing"
    evidence.mkdir()
    sentinel = evidence / "preserve.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(QA),
            "--scenario",
            "happy",
            "--evidence-dir",
            str(evidence),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_evidence_directory_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from public_document_web.evidence_path import create_evidence_directory

    external = tmp_path / "external"
    external.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic-link ancestor"):
        create_evidence_directory(linked / "new")
    assert not (external / "new").exists()


def test_evidence_directory_checks_symlinks_above_existing_child(
    tmp_path: Path,
) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from public_document_web.evidence_path import create_evidence_directory

    external = tmp_path / "external"
    child = external / "existing-child"
    child.mkdir(parents=True)
    linked = tmp_path / "linked"
    linked.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic-link ancestor"):
        create_evidence_directory(linked / "existing-child" / "new-output")
    assert not (child / "new-output").exists()


def test_all_qa_entrypoints_use_physical_evidence_confinement() -> None:
    for relative in (
        "scripts/qa/layout-profile-parity.py",
        "scripts/qa/export-roundtrip-matrix.py",
        "scripts/qa/fireblight-export-smoke.py",
        "scripts/qa/macos-app-qa.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "create_evidence_directory" in source, relative
    auditor = (ROOT / "scripts/qa/audit-ulw-evidence.py").read_text(encoding="utf-8")
    assert "prepare_output_file" in auditor
    verifier = (ROOT / "scripts" / "verify-production.sh").read_text(encoding="utf-8")
    assert "public_document_web.evidence_path" in verifier
