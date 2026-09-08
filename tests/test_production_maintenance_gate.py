from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "scripts" / "update-local-provenance.mjs"
VERIFY = ROOT / "scripts" / "verify-production.sh"
WORKTREE_FINGERPRINT = ROOT / "scripts" / "worktree-fingerprint.py"
FIREBLIGHT = ROOT / "scripts" / "qa" / "fireblight-export-smoke.py"


def test_generated_layout_profile_and_local_provenance_are_current() -> None:
    result = subprocess.run(
        ["node", str(PROVENANCE), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "current"
    assert receipt["profile"] == "Resources/Studio/official-layout-profile.js"
    assert receipt["manifest"] == "provenance/genoffice-docs-port.json"
    assert receipt["lock"] == "provenance/upstream-lock.json"


def test_production_verifier_rejects_tampered_provenance_copy(tmp_path: Path) -> None:
    evidence = tmp_path / "tamper"
    result = subprocess.run(
        [str(VERIFY), "--tamper-provenance-copy", str(evidence)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "pass"
    assert summary["tamperRejected"] is True
    assert summary["repositoryUnchanged"] is True
    assert summary["beforeWorktreeSHA256"] == summary["afterWorktreeSHA256"]
    assert (evidence / "transcript.txt").is_file()
    assert (evidence / "before-status.txt").read_text() == (
        evidence / "after-status.txt"
    ).read_text()
    assert (evidence / "before-worktree.sha256").read_text() == (
        evidence / "after-worktree.sha256"
    ).read_text()


def test_worktree_fingerprint_detects_content_change_with_same_git_status(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    tracked = repository / "tracked.txt"
    tracked.write_text("indexed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "tracked.txt"], check=True)
    tracked.write_text("first!!\n", encoding="utf-8")

    before_status = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    before = subprocess.run(
        ["python3", str(WORKTREE_FINGERPRINT), str(repository)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    tracked.write_text("second!\n", encoding="utf-8")
    after_status = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    after = subprocess.run(
        ["python3", str(WORKTREE_FINGERPRINT), str(repository)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert before_status == after_status
    assert len(before) == len(after) == 64
    assert before != after


def test_worktree_fingerprint_detects_executable_mode_change(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    script = repository / "scripts" / "tool.sh"
    script.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o644)

    before_status = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    before = subprocess.run(
        ["python3", str(WORKTREE_FINGERPRINT), str(repository)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    script.chmod(0o755)
    after_status = subprocess.run(
        ["git", "-C", str(repository), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    after = subprocess.run(
        ["python3", str(WORKTREE_FINGERPRINT), str(repository)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert before_status == after_status
    assert before != after


def test_worktree_fingerprint_detects_untracked_files_in_any_source_root(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    source = repository / "public_document_web" / "untracked.py"
    source.parent.mkdir()

    before = subprocess.run(
        ["python3", str(WORKTREE_FINGERPRINT), str(repository)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source.write_text("VALUE = 1\n", encoding="utf-8")
    after = subprocess.run(
        ["python3", str(WORKTREE_FINGERPRINT), str(repository)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert before != after


def test_production_verifier_declares_full_and_repeat_gates() -> None:
    script = VERIFY.read_text(encoding="utf-8")

    assert "swift build --product PublicDocumentApp" in script
    assert "python3 -m pytest" in script
    assert "node --check" in script
    assert "update-local-provenance.mjs --check" in script
    assert "layout-profile-parity.py" in script
    assert "export-roundtrip-matrix.py" in script
    assert "fireblight-export-smoke.py" in script
    assert "worktree-fingerprint.py" in script
    assert "before-worktree.sha256" in script
    assert "after-worktree.sha256" in script
    assert "--repeat" in script
    repeat_gate = script[script.index("repeat_gate()"):script.index("case \"$mode\"")]
    assert '"$root/scripts/verify-production.sh" "$child"' in repeat_gate
    assert "golden_gate" not in repeat_gate
    identity = script[script.index('"sourceIdentity"'):script.index('"cleanup"', script.index('"sourceIdentity"'))]
    assert '"headTree"' in identity
    assert '"worktreeSHA256"' in identity
    assert '"worktreeDirty"' in identity
    assert '"tree"' not in identity


def test_genoffice_port_verifier_rejects_symlinked_local_artifacts(
    tmp_path: Path,
) -> None:
    manifest = json.loads(
        (ROOT / "provenance" / "genoffice-docs-port.json").read_text(encoding="utf-8")
    )
    local_root = tmp_path / "local"
    for artifact in manifest["localArtifacts"]:
        target = local_root / artifact["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(ROOT / artifact["path"])

    result = subprocess.run(
        [
            "node",
            str(ROOT / "scripts" / "verify-genoffice-port.mjs"),
            "--manifest",
            str(ROOT / "provenance" / "genoffice-docs-port.json"),
            "--local-root",
            str(local_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "symlink" in result.stdout + result.stderr


def test_genoffice_port_verifier_rejects_symlinked_local_root(
    tmp_path: Path,
) -> None:
    linked = tmp_path / "linked-root"
    linked.symlink_to(ROOT, target_is_directory=True)

    result = subprocess.run(
        [
            "node",
            str(ROOT / "scripts" / "verify-genoffice-port.mjs"),
            "--manifest",
            str(ROOT / "provenance" / "genoffice-docs-port.json"),
            "--local-root",
            str(linked),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "symlinked local verification root" in result.stdout + result.stderr


def test_fireblight_browser_trial_uses_state_signals_not_fixed_sleeps() -> None:
    trial = (ROOT / "tests" / "fireblight_content_trial.tpl.js").read_text(
        encoding="utf-8"
    )

    assert "const sleep" not in trial
    assert "await sleep(" not in trial
    assert "waitForFunction" not in trial
    assert "requestAnimationFrame" not in trial
    assert "MutationObserver" in trial
    assert "IntersectionObserver" in trial


def test_fireblight_standalone_qa_builds_current_product(tmp_path: Path) -> None:
    evidence = tmp_path / "fireblight"
    result = subprocess.run(
        [
            "python3",
            str(FIREBLIGHT),
            "--format",
            "docx",
            "--outdir",
            str(evidence),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    transcript = (evidence / "transcript.txt").read_text(encoding="utf-8")
    assert "$ swift build --product PublicDocumentApp" in transcript
    inspection = json.loads(
        (evidence / "package-inspection.json").read_text(encoding="utf-8")
    )
    assert inspection["status"] == "pass"
