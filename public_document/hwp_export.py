from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol


_BUNDLED_RHWP: Final = Path(__file__).resolve().parent.parent / "Resources" / "Engines" / "rhwp"
_BUNDLED_RHWP_SHA256: Final = "a9fc072e61aa1cbf56fbd00943c4e4a33dd49aa7f6122f7b36e16ff476f7677b"
_HWP_CFB_SIGNATURE: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class HWPExportError(RuntimeError):
    pass


class HWPUnavailableError(HWPExportError):
    pass


class HWPCompatibilityError(HWPExportError):
    pass


class DuplicateWriteError(HWPExportError):
    pass


class PageLimitExceededError(HWPExportError):
    pass


class HWPAdapter(Protocol):
    def export(self, hwpx_path: Path, destination: Path) -> Path: ...


class BundledRhwpAdapter:
    def __init__(self, engine_path: Path = _BUNDLED_RHWP) -> None:
        self._engine_path: Path = engine_path.resolve()
        self._requires_pinned_hash = self._engine_path == _BUNDLED_RHWP.resolve()

    def export(self, hwpx_path: Path, destination: Path) -> Path:
        engine = self._engine_path
        if not engine.is_file() or not os.access(engine, os.X_OK):
            raise HWPUnavailableError(f"pinned rhwp engine is unavailable or not executable: {engine}")
        if self._requires_pinned_hash and hashlib.sha256(engine.read_bytes()).hexdigest() != _BUNDLED_RHWP_SHA256:
            raise HWPUnavailableError(f"pinned rhwp engine hash does not match the approved build: {engine}")
        destination = destination.resolve()
        if destination.exists():
            raise DuplicateWriteError(f"HWP destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".rhwp-", dir=destination.parent) as working_directory:
            staged_output = Path(working_directory) / destination.name
            try:
                completed = subprocess.run(
                    (
                        str(engine),
                        "convert",
                        str(hwpx_path.resolve()),
                        str(staged_output),
                        "--verify",
                        "--verify-pages",
                    ),
                    capture_output=True,
                    check=False,
                    text=True,
                )
            except OSError as error:
                raise HWPUnavailableError(f"pinned rhwp engine could not start at {engine}: {error}") from error
            if completed.returncode != 0:
                diagnostic = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
                raise HWPCompatibilityError(
                    f"pinned rhwp conversion failed with exit {completed.returncode}: {diagnostic}"
                )
            try:
                with staged_output.open("rb") as staged_file:
                    signature = staged_file.read(len(_HWP_CFB_SIGNATURE))
                    os.fsync(staged_file.fileno())
            except OSError as error:
                raise HWPCompatibilityError(f"pinned rhwp produced no readable HWP artifact: {error}") from error
            if signature != _HWP_CFB_SIGNATURE:
                raise HWPCompatibilityError("pinned rhwp output failed the HWP CFB signature check")
            try:
                os.link(staged_output, destination)
            except FileExistsError as error:
                raise DuplicateWriteError(f"HWP destination already exists: {destination}") from error
            except OSError as error:
                raise HWPExportError(f"validated HWP artifact could not be published atomically: {error}") from error
        return destination


@dataclass(frozen=True)
class HWPExportOutcome:
    available: bool
    output_path: Path | None
    warning: str | None
    diagnostic: str | None
