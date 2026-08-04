from __future__ import annotations

from pathlib import Path

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

    def runner(command: tuple[str, ...] | list[str]) -> None:
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
        return self.valid and candidate.read_text() == "signed-release"


def test_local_core_is_usable_without_login() -> None:
    core = LocalCore()

    assert core.requires_login is False
    assert core.ready() is True


def test_failed_signed_update_preserves_installed_working_version(tmp_path: Path) -> None:
    installed = tmp_path / "PublicDocument.app"
    candidate = tmp_path / "PublicDocument-new.app"
    installed.write_text("working-version")
    candidate.write_text("invalid-release")

    result = SignedUpdateManager(FixedVerifier(False)).install(candidate, installed)

    assert result == UpdateInstallResult(False, "candidate signature or notarization verification failed")
    assert installed.read_text() == "working-version"
    assert candidate.exists()


def test_verified_signed_update_replaces_installed_version_atomically(tmp_path: Path) -> None:
    installed = tmp_path / "PublicDocument.app"
    candidate = tmp_path / "PublicDocument-new.app"
    installed.write_text("working-version")
    candidate.write_text("signed-release")

    result = SignedUpdateManager(FixedVerifier(True)).install(candidate, installed)

    assert result == UpdateInstallResult(True, "update installed")
    assert installed.read_text() == "signed-release"
    assert not candidate.exists()
