from __future__ import annotations

from pathlib import Path
from typing import Sequence
import errno

import pytest

import release
from release import (
    DeveloperIDReleaseBuilder,
    LocalCore,
    SignedUpdateManager,
    UpdateInstallResult,
    UpdateVerifier,
)


def test_developer_id_builder_runs_signed_notarized_dmg_pipeline(tmp_path: Path, monkeypatch) -> None:
    app = tmp_path / "PublicDocument.app"
    app.mkdir()
    destination = tmp_path / "PublicDocument.dmg"
    commands: list[tuple[str, ...]] = []

    def runner(command: Sequence[str]) -> None:
        commands.append(tuple(command))

    monkeypatch.setattr("release.sys.platform", "darwin")
    monkeypatch.setattr("release.platform.machine", lambda: "arm64")
    output = DeveloperIDReleaseBuilder(runner).build(
        app,
        destination,
        signing_identity="Developer ID Application: Example",
        notary_profile="public-document-notary",
    )

    assert output == destination
    assert commands[0][:2] == ("codesign", "--deep")
    assert ("xcrun", "notarytool", "submit", str(destination), "--keychain-profile", "public-document-notary", "--wait") in commands
    assert ("xcrun", "stapler", "staple", str(destination)) in commands
    assert ("spctl", "--assess", "--type", "open", str(destination)) in commands


class FixedVerifier(UpdateVerifier):
    def __init__(self, valid: bool) -> None:
        self.valid = valid

    def verify(self, candidate: Path) -> bool:
        return self.valid and (candidate / "Contents/MacOS/PublicDocument").read_text() == "signed-release"


def _app_bundle(path: Path, version: str) -> Path:
    executable = path / "Contents/MacOS/PublicDocument"
    executable.parent.mkdir(parents=True)
    executable.write_text(version)
    executable.chmod(0o755)
    (path / "Contents/Info.plist").write_text(f"<plist><string>{version}</string></plist>")
    (path / "Contents/current").symlink_to("MacOS/PublicDocument")
    return path


def test_local_core_is_usable_without_login() -> None:
    core = LocalCore()

    assert core.requires_login is False
    assert core.ready() is True


def test_failed_signed_update_preserves_installed_working_version(tmp_path: Path) -> None:
    installed = tmp_path / "PublicDocument.app"
    candidate = tmp_path / "PublicDocument-new.app"
    _app_bundle(installed, "working-version")
    _app_bundle(candidate, "invalid-release")

    result = SignedUpdateManager(FixedVerifier(False)).install(candidate, installed)

    assert result == UpdateInstallResult(False, "candidate signature or notarization verification failed")
    assert (installed / "Contents/MacOS/PublicDocument").read_text() == "working-version"
    assert candidate.exists()


def test_verified_signed_update_replaces_installed_version_atomically(tmp_path: Path) -> None:
    installed = tmp_path / "PublicDocument.app"
    candidate = tmp_path / "PublicDocument-new.app"
    _app_bundle(installed, "working-version")
    _app_bundle(candidate, "signed-release")
    candidate_inode = candidate.stat().st_ino

    result = SignedUpdateManager(FixedVerifier(True)).install(candidate, installed)

    assert result == UpdateInstallResult(True, "update installed")
    assert (installed / "Contents/MacOS/PublicDocument").read_text() == "signed-release"
    assert installed.stat().st_ino == candidate_inode
    assert (installed / "Contents/current").is_symlink()
    assert (installed / "Contents/MacOS/PublicDocument").stat().st_mode & 0o111
    assert not candidate.exists()
    assert set(tmp_path.iterdir()) == {installed}


def test_bundle_update_rolls_back_when_retiring_previous_bundle_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed = _app_bundle(tmp_path / "PublicDocument.app", "working-version")
    candidate = _app_bundle(tmp_path / "PublicDocument-new.app", "signed-release")
    old_inode, new_inode = installed.stat().st_ino, candidate.stat().st_ino
    original_replace = release.os.replace
    failure = OSError(errno.EACCES, "injected retirement failure")
    observed_swap: list[bool] = []

    def fail_retirement(source: Path, destination: Path) -> None:
        if Path(source) == candidate and Path(destination) != installed:
            # Observe the real atomic swap before failing the subsequent move.
            assert installed.stat().st_ino == new_inode
            assert candidate.stat().st_ino == old_inode
            observed_swap.append(True)
            raise failure
        original_replace(source, destination)

    monkeypatch.setattr(release.os, "replace", fail_retirement)
    with pytest.raises(OSError) as raised:
        SignedUpdateManager(FixedVerifier(True)).install(candidate, installed)
    assert raised.value is failure
    assert observed_swap == [True]
    assert installed.stat().st_ino == old_inode
    assert candidate.stat().st_ino == new_inode
    assert (installed / "Contents/current").read_text() == "working-version"
    assert (candidate / "Contents/current").read_text() == "signed-release"
    assert set(tmp_path.iterdir()) == {installed, candidate}


def test_verified_bundle_can_be_installed_without_an_existing_version(tmp_path: Path) -> None:
    candidate = _app_bundle(tmp_path / "PublicDocument-new.app", "signed-release")
    installed = tmp_path / "Applications/PublicDocument.app"
    result = SignedUpdateManager(FixedVerifier(True)).install(candidate, installed)
    assert result.installed
    assert (installed / "Contents/current").read_text() == "signed-release"
    assert not candidate.exists()
