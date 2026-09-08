from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence


class DistributionError(RuntimeError):
    pass


class DistributionUnavailableError(DistributionError):
    pass


@dataclass(frozen=True)
class LocalCore:
    requires_login: bool = False

    def ready(self) -> bool:
        return True


class UpdateVerifier(Protocol):
    def verify(self, candidate: Path) -> bool: ...


class MacOSArtifactVerifier:
    def verify(self, candidate: Path) -> bool:
        if sys.platform != "darwin" or platform.machine() != "arm64":
            return False
        try:
            subprocess.run(("xcrun", "stapler", "validate", str(candidate)), check=True, capture_output=True, text=True)
            subprocess.run(("spctl", "--assess", "--type", "open", str(candidate)), check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            return False
        return True


@dataclass(frozen=True)
class UpdateInstallResult:
    installed: bool
    message: str


def _swap_bundles(candidate: Path, installed: Path) -> None:
    """Exchange bundle directory entries without an absent installed path."""
    if sys.platform != "darwin":
        raise DistributionUnavailableError("atomic bundle replacement requires macOS")
    rename_swap = ctypes.CDLL(None, use_errno=True).renamex_np
    rename_swap.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    rename_swap.restype = ctypes.c_int
    if rename_swap(os.fsencode(candidate), os.fsencode(installed), 0x00000002) != 0:  # RENAME_SWAP
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(installed))


class SignedUpdateManager:
    def __init__(self, verifier: UpdateVerifier) -> None:
        self._verifier = verifier

    def install(self, candidate: Path, installed: Path) -> UpdateInstallResult:
        if not candidate.exists() or not self._verifier.verify(candidate):
            return UpdateInstallResult(
                False,
                "candidate signature or notarization verification failed",
            )
        installed.parent.mkdir(parents=True, exist_ok=True)
        if candidate.is_dir() and installed.is_dir() and not candidate.samefile(installed):
            with tempfile.TemporaryDirectory(prefix=".update-", dir=installed.parent) as temporary:
                _swap_bundles(candidate, installed)
                try:
                    os.replace(candidate, Path(temporary) / "previous.app")
                except OSError:
                    _swap_bundles(candidate, installed)
                    raise
        else:
            os.replace(candidate, installed)
        return UpdateInstallResult(True, "update installed")


CommandRunner = Callable[[Sequence[str]], None]


def _run_command(command: Sequence[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


class DeveloperIDReleaseBuilder:
    def __init__(self, runner: CommandRunner = _run_command) -> None:
        self._runner = runner

    def build(
        self,
        app_bundle: Path,
        destination: Path,
        *,
        signing_identity: str,
        notary_profile: str,
    ) -> Path:
        if sys.platform != "darwin":
            raise DistributionUnavailableError("Developer ID DMG release requires macOS")
        if platform.machine() != "arm64":
            raise DistributionUnavailableError("Apple Silicon arm64 release is required")
        if not app_bundle.is_dir() or app_bundle.suffix != ".app":
            raise DistributionError("app_bundle must be an existing .app bundle")
        if not signing_identity.strip() or not notary_profile.strip():
            raise DistributionError("signing identity and notary profile are required")

        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="public-document-release-") as temporary:
            staging = Path(temporary) / app_bundle.name
            shutil.copytree(app_bundle, staging)
            self._runner(
                (
                    "codesign",
                    "--deep",
                    "--force",
                    "--options",
                    "runtime",
                    "--sign",
                    signing_identity,
                    str(staging),
                )
            )
            self._runner(("codesign", "--verify", "--deep", "--strict", str(staging)))
            self._runner(
                (
                    "hdiutil",
                    "create",
                    "-volname",
                    "PublicDocument",
                    "-srcfolder",
                    str(Path(temporary)),
                    "-ov",
                    "-format",
                    "UDZO",
                    str(destination),
                )
            )
        self._runner(("codesign", "--force", "--sign", signing_identity, str(destination)))
        self._runner(("codesign", "--verify", "--strict", str(destination)))
        self._runner(
            (
                "xcrun",
                "notarytool",
                "submit",
                str(destination),
                "--keychain-profile",
                notary_profile,
                "--wait",
            )
        )
        self._runner(("xcrun", "stapler", "staple", str(destination)))
        self._runner(("spctl", "--assess", "--type", "open", str(destination)))
        return destination
