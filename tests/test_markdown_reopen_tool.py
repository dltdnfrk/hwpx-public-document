from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify-markdown-reopen.mjs"
ARTIFACT = ROOT / "output" / "ac-07" / "markdown-final.4PwLOw" / "input.md"
FIXTURE = (
    ROOT
    / "Resources"
    / "Compatibility"
    / "Fixtures"
    / "basic-text-project.json"
)
EXPECTED_TEXT = [
    "2026년 생활안전 추진계획",
    "지역 생활안전 취약요인을 점검한다.",
    "[확인 필요] 통계 기준일",
]


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _run(artifact: Path, fixture: Path, output_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "node",
            str(SCRIPT),
            "--artifact",
            str(artifact),
            "--fixture",
            str(fixture),
            "--output-root",
            str(output_root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_markdown_reopen_binds_pristine_inputs_and_raw_render_evidence() -> None:
    # Given: the canonical Markdown artifact and its frozen authored fixture.
    artifact_hash = _sha256(ARTIFACT)
    fixture_hash = _sha256(FIXTURE)

    with tempfile.TemporaryDirectory(prefix="markdown-reopen-test-", dir=ROOT / "output") as temporary:
        output_root = Path(temporary) / "evidence"

        # When: the artifact is reopened by the pinned CommonMark reader and browser renderer.
        result = _run(ARTIFACT, FIXTURE, output_root)

        # Then: raw evidence is bound to unchanged inputs and external approval stays blocked.
        assert result.returncode == 0, result.stderr
        receipt = json.loads((output_root / "receipt.json").read_text(encoding="utf-8"))
        assert receipt["schemaVersion"] == 1
        assert receipt["overallVerdict"] == "blocked"
        assert receipt["localVerdict"] == "pass"
        assert receipt["inputs"]["artifact"] == {
            "path": str(ARTIFACT.relative_to(ROOT)),
            "pristineBeforeSha256": artifact_hash,
            "pristineAfterSha256": artifact_hash,
            "inputCopyPath": "input.md",
            "inputCopySha256": artifact_hash,
        }
        assert receipt["inputs"]["fixture"] == {
            "path": str(FIXTURE.relative_to(ROOT)),
            "pristineBeforeSha256": fixture_hash,
            "pristineAfterSha256": fixture_hash,
        }
        commonmark = receipt["commonMarkObservation"]
        assert commonmark["operation"] == "commonmark-validate"
        assert commonmark["clientVersion"] == "3.9.0.2"
        assert commonmark["opened"] is True
        assert commonmark["extensionDialogCapable"] is False
        assert commonmark["extensionWarningCount"] == 0
        assert commonmark["expectedTextCount"] == len(EXPECTED_TEXT)
        assert commonmark["observedTextCount"] == len(EXPECTED_TEXT)
        assert commonmark["expectedTextOrder"] == EXPECTED_TEXT
        assert commonmark["observedTextOrder"] == EXPECTED_TEXT
        assert receipt["renderCandidate"]["screenshotPath"] == "commonmark-render.png"
        assert receipt["renderCandidate"]["missingAuthoredElementIDs"] == []
        assert receipt["renderCandidate"]["verdict"] == "candidate"
        assert receipt["externalBlockers"] == [
            {
                "operation": "approved-rendering",
                "status": "pending-external-authority",
                "verdict": "blocked",
                "evidencePath": "approved-rendering-blocker.json",
                "evidenceSha256": _sha256(output_root / "approved-rendering-blocker.json"),
            }
        ]
        blocker = json.loads(
            (output_root / "approved-rendering-blocker.json").read_text(encoding="utf-8")
        )
        assert blocker["selfApprovalPermitted"] is False
        assert blocker["approval"]["authorityReceipt"] is None
        assert blocker["approval"]["status"] == "pending-external-authority"
        for evidence in receipt["evidence"]:
            evidence_path = output_root / evidence["path"]
            assert evidence_path.is_file()
            assert evidence["sha256"] == _sha256(evidence_path)
            assert evidence["sizeBytes"] == evidence_path.stat().st_size
        assert ARTIFACT.read_bytes() == (output_root / "input.md").read_bytes()


def test_markdown_reopen_refuses_an_existing_output_without_touching_it() -> None:
    # Given: an occupied output root containing evidence that must be preserved.
    with tempfile.TemporaryDirectory(prefix="markdown-reopen-test-", dir=ROOT / "output") as temporary:
        output_root = Path(temporary) / "evidence"
        output_root.mkdir()
        sentinel = output_root / "preserve.txt"
        sentinel.write_text("preserve", encoding="utf-8")

        # When: a new verification run targets the occupied root.
        result = _run(ARTIFACT, FIXTURE, output_root)

        # Then: the run fails before replacing or extending the prior evidence.
        assert result.returncode != 0
        assert "output root already exists" in result.stderr
        assert list(output_root.iterdir()) == [sentinel]
        assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_markdown_reopen_rejects_missing_authored_text_and_cleans_staging() -> None:
    # Given: a project-confined Markdown copy missing one authored Korean string.
    with tempfile.TemporaryDirectory(prefix="markdown-reopen-test-", dir=ROOT / "output") as temporary:
        temporary_root = Path(temporary)
        artifact = temporary_root / "tampered.md"
        shutil.copyfile(ARTIFACT, artifact)
        artifact.write_text(
            artifact.read_text(encoding="utf-8").replace(
                r"**\[확인 필요\] 통계 기준일**",
                "**누락**",
            ),
            encoding="utf-8",
        )
        output_root = temporary_root / "evidence"

        # When: the CommonMark result is checked against the frozen fixture.
        result = _run(artifact, FIXTURE, output_root)

        # Then: no publishable or staged evidence survives the failed validation.
        assert result.returncode != 0
        assert "expected Korean text" in result.stderr
        assert not output_root.exists()
        assert list(temporary_root.glob(".markdown-reopen-*")) == []
