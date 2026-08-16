from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


RENAME_SWAP = 0x00000002


@dataclass(frozen=True)
class BundleMap:
    entries: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class InstallPaths:
    destination: Path
    next_bundle: Path
    previous_bundle: Path


@dataclass(frozen=True)
class InstallPlan:
    source: Path
    expected: BundleMap
    paths: InstallPaths


@dataclass(frozen=True)
class IneligibleBundleError(RuntimeError):
    source: Path

    def __str__(self) -> str:
        return f"bundle does not match NEW: {self.source}"


Exchange = Callable[[Path, Path], None]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_map(path: Path) -> BundleMap:
    entries = []
    for candidate in path.rglob("*"):
        if stat.S_ISREG(candidate.lstat().st_mode):
            entries.append((candidate.relative_to(path).as_posix(), _sha256(candidate)))
    return BundleMap(tuple(sorted(entries)))


def is_new(path: Path, expected: BundleMap) -> bool:
    return path.is_dir() and _bundle_map(path) == expected


def rename_exchange(left: Path, right: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renamex_np = libc.renamex_np
    renamex_np.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    renamex_np.restype = ctypes.c_int
    if renamex_np(os.fsencode(left), os.fsencode(right), RENAME_SWAP) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), str(left), str(right))


def _stage(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, copy_function=shutil.copy2)


def _delete(path: Path) -> None:
    shutil.rmtree(path)


def dispatch_install(plan: InstallPlan, exchange: Exchange = rename_exchange) -> None:
    if not is_new(plan.source, plan.expected):
        raise IneligibleBundleError(plan.source)

    paths = plan.paths
    paths.destination.parent.mkdir(parents=True, exist_ok=True)
    while True:
        destination_present = paths.destination.exists()
        next_present = paths.next_bundle.exists()
        previous_present = paths.previous_bundle.exists()

        if is_new(paths.destination, plan.expected):
            if next_present:
                _delete(paths.next_bundle)
            if previous_present:
                _delete(paths.previous_bundle)
            return

        if not next_present and not previous_present:
            _stage(plan.source, paths.next_bundle)
            continue

        if not next_present and previous_present:
            if destination_present:
                _stage(plan.source, paths.next_bundle)
            else:
                os.rename(paths.previous_bundle, paths.destination)
            continue

        next_is_new = is_new(paths.next_bundle, plan.expected)
        if not previous_present:
            if not destination_present:
                if next_is_new:
                    os.rename(paths.next_bundle, paths.destination)
                else:
                    _delete(paths.next_bundle)
            elif next_is_new:
                exchange(paths.next_bundle, paths.destination)
                _delete(paths.next_bundle)
            else:
                _delete(paths.next_bundle)
            continue

        if not destination_present:
            if next_is_new:
                os.rename(paths.next_bundle, paths.destination)
                _delete(paths.previous_bundle)
            else:
                os.rename(paths.previous_bundle, paths.destination)
                _delete(paths.next_bundle)
            continue

        if next_is_new:
            exchange(paths.next_bundle, paths.destination)
            _delete(paths.next_bundle)
            _delete(paths.previous_bundle)
        else:
            _delete(paths.next_bundle)


def write_bundle_manifest(app_path: Path, manifest_path: Path, *, source_revision: str, toolkit_sha256: str, envelope_sha256: str) -> None:
    mapping = _bundle_map(app_path)
    lines = [
        f"sourceRevision {source_revision}",
        f"toolkitSha256 {toolkit_sha256}",
        f"envelopeSha256 {envelope_sha256}",
        *(f"{digest}  {relative}" for relative, digest in mapping.entries),
    ]
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_bundle_manifest(manifest_path: Path) -> BundleMap:
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[3:]:
        digest, relative = line.split("  ", 1)
        entries.append((relative, digest))
    return BundleMap(tuple(entries))


def default_install_paths() -> InstallPaths:
    applications = Path.home() / "Applications"
    return InstallPaths(
        destination=applications / "PublicDocument.app",
        next_bundle=applications / "PublicDocument.app.next",
        previous_bundle=applications / "PublicDocument.app.prev",
    )


def main() -> None:
    root = Path(__file__).resolve().parent
    source = root / "dist" / "PublicDocument.app"
    manifest = Path(str(source) + ".manifest")
    expected = read_bundle_manifest(manifest)
    dispatch_install(
        InstallPlan(source=source, expected=expected, paths=default_install_paths())
    )


if __name__ == "__main__":
    main()
