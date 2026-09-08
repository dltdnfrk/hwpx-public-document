from __future__ import annotations

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from types import TracebackType
import subprocess
import sys
import zipfile

import pytest

from hwpx import hwpx_content_hash, validate_hwpx
from public_document import hwpx_package
from public_document.hwp_export import DuplicateWriteError
from public_document import (
    Evidence,
    GuidedAnswers,
    build_policy_plan_draft,
    export_hwpx,
)


def _draft():
    answers = GuidedAnswers(
        title="폭염 취약계층 보호 계획",
        issuing_organization="서울특별시 안전총괄과",
        audience="시민과 자치구 담당자",
        purpose="보호 조치를 시행한다.",
        background="폭염 대응을 강화한다.",
        current_state="25곳에서 점검한다.",
        objectives="접근성을 높인다.",
        actions="점검을 시행한다.",
        owners="안전총괄과",
        schedule="2026년 6월",
        resources="기존 예산",
        risks="연락 두절",
        controls="방문 확인",
        outcomes="운영 상태를 점검한다.",
        follow_up="결과를 반영한다.",
        contact="재난대응팀",
        date="2026-05-20",
    )
    return build_policy_plan_draft(
        answers,
        (Evidence("ev-1", "점검자료", "p.1", "25곳에서 점검한다."),),
    )


def test_repeated_export_has_same_normalized_hash_and_passes_validation(tmp_path: Path) -> None:
    draft = _draft()
    first = export_hwpx(draft, tmp_path / "first.hwpx", operation_id="revision-1")
    second = export_hwpx(draft, first, operation_id="revision-1")

    assert hwpx_content_hash(first) == hwpx_content_hash(second)
    result = validate_hwpx(first, draft)
    assert result.is_valid
    assert result.package_valid
    assert result.schema_profile_valid
    assert result.internal_references_valid
    assert result.metadata_valid


@pytest.mark.parametrize("identical", [False, True])
def test_export_does_not_replace_a_competing_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, identical: bool) -> None:
    draft = _draft()
    destination = tmp_path / "race.hwpx"
    operation_id = f"race-{tmp_path.name}"
    original_close = zipfile.ZipFile.close
    competitor: list[tuple[bytes, int]] = []

    def publish_competitor(package: zipfile.ZipFile) -> None:
        writing = package.mode == "w" and package.fp is not None
        original_close(package)
        if writing:
            assert package.filename is not None
            staged = Path(package.filename)
            payload = staged.read_bytes() if identical else b"competitor-owned content"
            destination.write_bytes(payload)
            competitor.append((payload, destination.stat().st_ino))

    # The close hook runs after the initial existence check and before publication.
    monkeypatch.setattr(zipfile.ZipFile, "close", publish_competitor)
    if identical:
        assert export_hwpx(draft, destination, operation_id=operation_id) == destination
    else:
        with pytest.raises(DuplicateWriteError):
            export_hwpx(draft, destination, operation_id=operation_id)
        assert operation_id not in hwpx_package._EXPORTS
    assert len(competitor) == 1
    assert destination.read_bytes() == competitor[0][0]
    assert destination.stat().st_ino == competitor[0][1]
    assert not list(tmp_path.glob(".hwpx-*"))


def test_export_ledger_retains_digest_not_payload_and_preserves_snapshot_identity(tmp_path: Path) -> None:
    draft = replace(_draft(), quality_notice="large snapshot " * 100_000)
    destination = tmp_path / "large.hwpx"
    operation_id = f"digest-{tmp_path.name}"
    export_hwpx(draft, destination, operation_id=operation_id)
    original_bytes = destination.read_bytes()
    assert export_hwpx(draft, destination, operation_id=operation_id) == destination
    with pytest.raises(DuplicateWriteError):
        export_hwpx(replace(draft, quality_notice="changed"), destination, operation_id=operation_id)
    with pytest.raises(DuplicateWriteError):
        export_hwpx(draft, tmp_path / "other.hwpx", operation_id=operation_id)
    # Even if the original artifact is moved away, the operation remains bound.
    destination.rename(tmp_path / "saved.hwpx")
    with pytest.raises(DuplicateWriteError):
        export_hwpx(replace(draft, quality_notice="changed"), destination, operation_id=operation_id)
    assert export_hwpx(draft, destination, operation_id=operation_id) == destination
    assert destination.read_bytes() == original_bytes
    recorded_path, digest = hwpx_package._EXPORTS[operation_id]
    assert recorded_path == destination
    assert isinstance(digest, bytes)
    assert len(digest) == 32
    assert len(original_bytes) > len(digest)


@pytest.mark.parametrize("member", ["mimetype", "Contents/section0.xml", "extra.xml"])
def test_validation_rejects_duplicate_zip_members(tmp_path: Path, member: str) -> None:
    draft = _draft()
    path = export_hwpx(draft, tmp_path / "duplicate.hwpx", operation_id=f"duplicate-{tmp_path.name}")
    with zipfile.ZipFile(path, "a") as package:
        if member not in package.namelist():
            package.writestr(member, b"<extra/>")
        payload = package.read(member)
        with pytest.warns(UserWarning):
            package.writestr(member, payload)
    result = validate_hwpx(path, draft)
    assert not result.package_valid
    assert not result.is_valid
    assert result.errors


def test_export_does_not_accept_duplicate_members_as_an_idempotent_retry(tmp_path: Path) -> None:
    draft = _draft()
    operation_id = f"duplicate-retry-{tmp_path.name}"
    path = export_hwpx(draft, tmp_path / "duplicate.hwpx", operation_id=operation_id)
    with zipfile.ZipFile(path, "a") as package:
        with pytest.warns(UserWarning):
            package.writestr("mimetype", package.read("mimetype"))
    original_bytes = path.read_bytes()
    with pytest.raises(DuplicateWriteError):
        export_hwpx(draft, path, operation_id=operation_id)
    assert path.read_bytes() == original_bytes


@pytest.mark.parametrize("conflict", ["destination", "snapshot", "identical"])
def test_concurrent_operation_id_has_one_destination_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conflict: str,
) -> None:
    draft = _draft()
    contender_draft = replace(draft, quality_notice="changed snapshot") if conflict == "snapshot" else draft
    destination = tmp_path / "first.hwpx"
    contender_destination = destination if conflict == "identical" else tmp_path / "second.hwpx"
    operation_id = f"concurrent-{tmp_path}"
    first_at_publication = Event()
    contender_ready = Event()
    lock = Lock()
    original_link = hwpx_package.os.link

    class ObservedLock:
        def __enter__(self) -> None:
            if first_at_publication.is_set():
                contender_ready.set()
            lock.acquire()

        def __exit__(
            self, exc_type: type[BaseException] | None,
            exc_value: BaseException | None, traceback: TracebackType | None,
        ) -> None:
            lock.release()

    def coordinate_publication(source: Path, target: Path) -> None:
        if not first_at_publication.is_set():
            first_at_publication.set()
            assert contender_ready.wait(timeout=5), "contender never reached publication or lock acquisition"
        else:
            # Without synchronization, the contender has already passed the ledger check.
            contender_ready.set()
        original_link(source, target)

    # The wrapper still acquires a real lock. It signals BEFORE a contender blocks,
    # so the same schedule works both without the repair and with serialization.
    monkeypatch.setattr(hwpx_package, "_EXPORT_LOCK", ObservedLock(), raising=False)
    monkeypatch.setattr(hwpx_package.os, "link", coordinate_publication)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(export_hwpx, draft, destination, operation_id=operation_id)
        assert first_at_publication.wait(timeout=5), "first writer never reached publication"
        contender = executor.submit(export_hwpx, contender_draft, contender_destination, operation_id=operation_id)
        if conflict == "identical":
            assert contender.result(timeout=5) == destination
        else:
            with pytest.raises(DuplicateWriteError):
                contender.result(timeout=5)
        assert first.result(timeout=5) == destination

    assert validate_hwpx(destination, draft).is_valid
    assert set(tmp_path.iterdir()) == {destination}
    assert hwpx_package._EXPORTS[operation_id][0] == destination
    assert export_hwpx(draft, destination, operation_id=operation_id) == destination


def test_failed_publication_releases_operation_id_and_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    draft = _draft()
    operation_id = f"failed-publication-{tmp_path}"
    failure = PermissionError("injected publication failure")

    def fail_publication(source: Path, target: Path) -> None:
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(hwpx_package.os, "link", fail_publication)
        with pytest.raises(PermissionError) as raised:
            export_hwpx(draft, tmp_path / "failed.hwpx", operation_id=operation_id)
    assert raised.value is failure
    assert operation_id not in hwpx_package._EXPORTS
    assert not list(tmp_path.iterdir())
    changed = replace(draft, quality_notice="retry after failed publication")
    with ThreadPoolExecutor(max_workers=1) as executor:
        retry = executor.submit(export_hwpx, changed, tmp_path / "retry.hwpx", operation_id=operation_id)
        assert validate_hwpx(retry.result(timeout=5), changed).is_valid


@pytest.mark.parametrize("first_module", ["hwpx", "public_document"])
def test_fresh_import_orders_preserve_validation_api_identity(tmp_path: Path, first_module: str) -> None:
    script = """
import importlib, json, pickle, runpy, sys
from dataclasses import FrozenInstanceError, asdict
importlib.import_module(sys.argv[1])
import hwpx
import public_document
from public_document import draft_builder
assert public_document.HWPXValidation is hwpx.HWPXValidation
assert public_document.validate_hwpx is hwpx.validate_hwpx
assert public_document.hwpx_content_hash is hwpx.hwpx_content_hash
assert public_document.validate_draft is draft_builder.validate_draft
draft = runpy.run_path('tests/test_hwpx_validation.py')['_draft']()
assert draft.validation == public_document.validate_draft(draft)
from pathlib import Path
path = public_document.export_hwpx(draft, Path(sys.argv[2]), operation_id='cycle-characterization')
result = public_document.validate_hwpx(path, draft)
assert type(result) is hwpx.HWPXValidation and result.is_valid
assert pickle.loads(pickle.dumps(result)) == result
try:
    result.package_valid = False
except FrozenInstanceError:
    pass
else:
    raise AssertionError('validation result became mutable')
assert not hwpx.HWPXValidation(False, True, True, True, '').is_valid
print(json.dumps(asdict(result), sort_keys=True))
"""
    run = subprocess.run(
        [sys.executable, "-c", script, first_module, str(tmp_path / "import-order.hwpx")],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    print(first_module, run.stdout.strip())
