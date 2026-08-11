from __future__ import annotations

from pathlib import Path
import hashlib

import pytest

from public_document import (
    BundledRhwpAdapter,
    DuplicateWriteError,
    Evidence,
    GuidedAnswers,
    HWPCompatibilityError,
    HWPUnavailableError,
    build_policy_plan_draft,
    complete_manual_draft,
    export_hwpx,
)


def _answers() -> GuidedAnswers:
    return GuidedAnswers(
        title="내보내기 계획",
        issuing_organization="기관",
        audience="담당자",
        purpose="내보내기 경로를 검증한다.",
        background="검증 배경",
        current_state="현재 상태",
        objectives="검증 목표",
        actions="검증 수행",
        owners="담당 부서",
        schedule="상반기",
        resources="기존 자원",
        risks="변환 실패",
        controls="실패 시 원본 보존",
        outcomes="안전한 산출물",
        follow_up="결과 점검",
        contact="담당팀",
        date="2026-08-10",
    )


def _hwpx(tmp_path: Path) -> Path:
    draft = build_policy_plan_draft(_answers(), ())
    return export_hwpx(draft, tmp_path / "source.hwpx", operation_id=f"seed-{tmp_path.name}")


def test_default_hwp_export_ignores_alternative_engine_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alternative = tmp_path / "alternative-rhwp"
    _ = alternative.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
    alternative.chmod(0o755)
    monkeypatch.setenv("PUBLIC_DOCUMENT_STUDIO_RHWP", str(alternative))

    result = complete_manual_draft(
        _answers(),
        (Evidence("ev-1", "자료", "p.1", "현재 상태"),),
        tmp_path / "default.hwpx",
        operation_id="seed-default-bundled-rhwp",
    )

    assert result.hwp_export.available
    assert result.hwp_export.output_path == tmp_path / "default.hwp"
    assert (tmp_path / "default.hwp").read_bytes().startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert not tuple(tmp_path.glob(".rhwp-*"))


def test_default_hwp_export_uses_the_exact_approved_bundled_engine() -> None:
    engine = Path(__file__).resolve().parents[1] / "Resources" / "Engines" / "rhwp"

    assert hashlib.sha256(engine.read_bytes()).hexdigest() == (
        "a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b"
    )


def test_bundled_adapter_reports_missing_pinned_engine(tmp_path: Path) -> None:
    source = _hwpx(tmp_path)
    missing_engine = tmp_path / "missing" / "rhwp"

    with pytest.raises(HWPUnavailableError, match=str(missing_engine)):
        _ = BundledRhwpAdapter(missing_engine).export(source, tmp_path / "missing.hwp")

    assert not (tmp_path / "missing.hwp").exists()


def test_bundled_adapter_cleans_staging_output_after_compatibility_failure(tmp_path: Path) -> None:
    source = _hwpx(tmp_path)
    failing_engine = tmp_path / "failing-rhwp"
    _ = failing_engine.write_text(
        "#!/bin/sh\nprintf partial > \"$3\"\nprintf 'unsupported table preset' >&2\nexit 3\n",
        encoding="utf-8",
    )
    failing_engine.chmod(0o755)

    with pytest.raises(HWPCompatibilityError, match="exit 3: unsupported table preset"):
        _ = BundledRhwpAdapter(failing_engine).export(source, tmp_path / "failed.hwp")

    assert not (tmp_path / "failed.hwp").exists()
    assert not tuple(tmp_path.glob(".rhwp-*"))


def test_bundled_adapter_never_overwrites_existing_destination(tmp_path: Path) -> None:
    source = _hwpx(tmp_path)
    destination = tmp_path / "existing.hwp"
    _ = destination.write_bytes(b"sentinel")

    with pytest.raises(DuplicateWriteError, match=str(destination)):
        _ = BundledRhwpAdapter().export(source, destination)

    assert destination.read_bytes() == b"sentinel"
    assert not tuple(tmp_path.glob(".rhwp-*"))
