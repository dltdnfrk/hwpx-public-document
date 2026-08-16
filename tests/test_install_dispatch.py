from __future__ import annotations

import hashlib
from itertools import product
from pathlib import Path

import pytest

import public_document_install
from public_document_install import (
    BundleMap,
    InstallPlan,
    InstallPaths,
    dispatch_install,
    is_new,
    rename_exchange,
)


ABSENT = "absent"
OLD = "old"
NEW = "new"
INSTALL_STATES = tuple(
    pytest.param(*states, id="-".join(states))
    for states in product((ABSENT, OLD, NEW), repeat=3)
)


@pytest.mark.parametrize(
    "candidate_name",
    ("PublicDocument.app", "PublicDocument.app.next", "PublicDocument.app.prev"),
)
def test_is_new_classifies_every_absent_candidate_as_false(
    tmp_path: Path,
    candidate_name: str,
) -> None:
    # Given: an expected bundle map and an absent DEST, NEXT, or PREV candidate.
    expected = BundleMap(())
    candidate = tmp_path / candidate_name

    # When: the candidate is classified against NEW.
    result = is_new(candidate, expected)

    # Then: absence is always classified as not new.
    assert result is False


def _write_bundle(path: Path, content: str) -> None:
    path.mkdir(parents=True)
    (path / "Contents.txt").write_text(content, encoding="utf-8")


@pytest.mark.parametrize(
    ("dest_state", "next_state", "prev_state"),
    INSTALL_STATES,
)
def test_dispatch_converges_from_every_presence_and_freshness_state(
    tmp_path: Path,
    dest_state: str,
    next_state: str,
    prev_state: str,
) -> None:
    # Given: an eligible staged source and every absent/old/new combination for DEST/NEXT/PREV.
    source = tmp_path / "dist" / "PublicDocument.app"
    _write_bundle(source, NEW)
    expected = BundleMap(
        (("Contents.txt", hashlib.sha256(NEW.encode("utf-8")).hexdigest()),)
    )

    case_root = tmp_path / f"{dest_state}-{next_state}-{prev_state}"
    case_root.mkdir()
    paths = InstallPaths(
        destination=case_root / "PublicDocument.app",
        next_bundle=case_root / "PublicDocument.app.next",
        previous_bundle=case_root / "PublicDocument.app.prev",
    )
    for path, state in (
        (paths.destination, dest_state),
        (paths.next_bundle, next_state),
        (paths.previous_bundle, prev_state),
    ):
        if state != ABSENT:
            _write_bundle(path, state)

    # When: the same dispatcher is run from the observed state.
    dispatch_install(InstallPlan(source=source, expected=expected, paths=paths))

    # Then: DEST is exactly NEW and both recovery names are absent.
    assert (paths.destination / "Contents.txt").read_text(encoding="utf-8") == NEW
    assert not paths.next_bundle.exists()
    assert not paths.previous_bundle.exists()


def test_existing_destination_stays_present_during_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "dist" / "PublicDocument.app"
    _write_bundle(source, NEW)
    expected = BundleMap(
        (("Contents.txt", hashlib.sha256(NEW.encode("utf-8")).hexdigest()),)
    )
    paths = InstallPaths(
        destination=tmp_path / "PublicDocument.app",
        next_bundle=tmp_path / "PublicDocument.app.next",
        previous_bundle=tmp_path / "PublicDocument.app.prev",
    )
    _write_bundle(paths.destination, OLD)
    seen_present: list[bool] = [paths.destination.exists()]

    def record() -> None:
        seen_present.append(paths.destination.exists())

    original_stage = public_document_install._stage
    original_delete = public_document_install._delete

    def stage(source_path: Path, destination: Path) -> None:
        record()
        original_stage(source_path, destination)
        record()

    def delete(path: Path) -> None:
        record()
        original_delete(path)
        record()

    def exchange(left: Path, right: Path) -> None:
        record()
        rename_exchange(left, right)
        record()

    monkeypatch.setattr(public_document_install, "_stage", stage)
    monkeypatch.setattr(public_document_install, "_delete", delete)

    dispatch_install(
        InstallPlan(source=source, expected=expected, paths=paths),
        exchange=exchange,
    )

    assert all(seen_present)
    assert (paths.destination / "Contents.txt").read_text(encoding="utf-8") == NEW
    assert not paths.next_bundle.exists()
    assert not paths.previous_bundle.exists()
